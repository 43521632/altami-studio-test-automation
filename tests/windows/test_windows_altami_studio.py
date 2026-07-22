"""UI-тест запуска Altami Studio на Windows (двойной клик по ярлыку).

Сценарий (один непрерывный поток, состояние переходит по шагам):

1. На рабочем столе есть ярлык «Altami Studio 4.1 x64». Проверяем, что он есть,
   сверяя ТОЛЬКО значок (логотип) — версия «4.1 x64» в подписи игнорируется,
   чтобы тест не падал при обновлении версии.
2. Двойной клик по ярлыку — запуск приложения.
3. Во время запуска показывается баннер-заставка «ALTAMI STUDIO v.4.1» с
   надписью «Демо-версия». ГЛАВНАЯ проверка теста — что надпись есть.
4. Всплывает окно «Altami Studio Демо версия» с кнопкой «Закрыть» — нажимаем её.
5. Открывается окно «Altami Studio: Восстановить состояние приложения».
   Проверяем, что окно есть и что UI приложения не поломался.
6. Нажимаем «Пропустить» — окно исчезает, тест завершён.

Приложение НАМЕРЕННО остаётся открытым в конце — как и в кейсе для Astra:
тест продолжат расширять с этой точки, поэтому шага закрытия здесь нет.

Скорость и надёжность. ВМ на Windows подтормаживает неравномерно, поэтому вместо
слепых пауз тест ЖДЁТ появления каждого окна опросом (adaptive polling) и идёт
дальше в тот же миг, как окно готово. Это и быстрее (обычный прогон близок к
измеренному минимуму), и надёжнее (клик по «Закрыть» не промахивается мимо ещё
не появившегося окна). Замерянные минимумы переходов (живая ВМ 21.07.2026):
баннер ~3.7с, окно «Демо» ~0.8с после баннера, окно восстановления ~3.1с,
исчезновение ~0.6с. Таймауты опроса взяты с запасом над «минимум × 1.38»,
т.к. на «подтормозивших» прогонах переходы доходили до ~2× минимума — тесного
таймаута хватило бы не всегда.

Проверка надписей и окон — не OCR, а сравнение статичной области кадра с
эталоном (SSIM), см. base_tests.assert_region. Координаты и области сняты на
живой ВМ 21.07.2026 в видеорежиме 1920x1200.
"""

import asyncio
import logging

import pytest

from tests.base_tests import BaseVMTest

logger = logging.getLogger(__name__)

# --- Координаты кликов (пиксели гостя, режим 1920x1200) ----------------------
ALTAMI_SHORTCUT = (113, 120)   # значок ярлыка «Altami Studio 4.1 x64» на столе
DEMO_CLOSE_BTN = (1148, 593)   # кнопка «Закрыть» в окне «Altami Studio Демо версия»
RESTORE_SKIP_BTN = (1104, 666)  # кнопка «Пропустить» в окне восстановления
MOUSE_PARK = (1750, 300)       # нейтральная точка: увести курсор из кадра

# --- Области для сравнения с эталоном (left, top, right, bottom) -------------
# Только значок ярлыка (логотип Altami). Подпись «Altami Studio 4.1 x64» — ниже
# и в область НЕ входит, поэтому версия на проверку не влияет.
SHORTCUT_ICON_BOX = (86, 98, 140, 144)
# Порог для значка мягче 0.99: это проверка НАЛИЧИЯ ярлыка, а значок бывает
# выделен/в фокусе (полупрозрачная подсветка) — логотип тот же, но SSIM ~0.96.
# Чужой значок (Edge и т.п.) дал бы SSIM ~0.3-0.5, так что 0.90 их различает.
SHORTCUT_THRESHOLD = 0.90
# Баннер-заставка: полоса с текстом «ALTAMI STUDIO / Демо-версия / v.4.1».
# Окно «Демо версия» перекрывает логотип сверху, но НЕ эту полосу.
DEMO_BANNER_BOX = (690, 730, 1260, 895)
# Титульная строка окна «Altami Studio Демо версия» — ждём его перед «Закрыть».
DEMO_DIALOG_BOX = (705, 490, 1195, 515)
# Заголовок окна «Восстановить состояние приложения» — доказывает, что окно
# есть. Список сессий с датами намеренно вне области.
RESTORE_TITLE_BOX = (752, 420, 1135, 442)
# Панель инструментов главного окна — доказывает, что UI не поломался.
APP_TOOLBAR_BOX = (0, 50, 1130, 85)

# --- Таймауты опроса (секунды) -----------------------------------------------
# Это ПРЕДЕЛ ожидания, а не фиксированная пауза: обычно окно появляется гораздо
# раньше, и тест сразу идёт дальше. Значения с запасом над «минимум × 1.38».
LAUNCH_TIMEOUT = 12.0    # баннер после двойного клика (min 3.7с)
DIALOG_TIMEOUT = 8.0     # окно «Демо версия» после баннера (min 0.8с)
RESTORE_TIMEOUT = 10.0   # окно восстановления после «Закрыть» (min 3.1с)
DISMISS_TIMEOUT = 6.0    # исчезновение окна после «Пропустить» (min 0.6с)
POLL_INTERVAL = 0.4      # как часто опрашивать экран


@pytest.mark.windows
@pytest.mark.ui
class TestWindowsAltamiStudio(BaseVMTest):
    """Запуск Altami Studio с рабочего стола и проверка стартовых окон."""

    vm_id = "windows"

    # Вход в систему уже выполнен фикстурой guest_login — на рабочем столе.

    async def _park_mouse(self) -> None:
        """Увести курсор в нейтральную точку, чтобы он не попал в кадр."""
        await self.qmp.mouse_move(*MOUSE_PARK)
        self._ptr = MOUSE_PARK
        await asyncio.sleep(0.2)

    async def _wait_region(self, name, box, want=True, timeout=10.0):
        """Опрашивать область, пока она (не) совпадёт с эталоном.

        want=True  — ждём появления (SSIM > порога);
        want=False — ждём исчезновения (SSIM <= порога).
        Возвращает последний ComparisonResult (по нему видно, дождались ли).
        """
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        result = None
        while loop.time() < deadline:
            await self._park_mouse()
            result = await self.compare_region(name, box)
            if result.passed == want:
                return result
            await asyncio.sleep(POLL_INTERVAL)
        return result

    async def _launch_altami(self, attempts: int = 2) -> None:
        """Двойным кликом по ярлыку запустить приложение и дождаться баннера.

        Успех подтверждается появлением баннера. Если за таймаут баннер не
        появился — двойной клик не сработал, повторяем. Проверка ПОСЛЕ таймаута,
        а не сразу: иначе повторный клик открыл бы второй экземпляр.
        """
        for attempt in range(1, attempts + 1):
            await self.glide(*ALTAMI_SHORTCUT)
            await asyncio.sleep(0.4)
            await self.double_click(*ALTAMI_SHORTCUT)
            result = await self._wait_region(
                "altami_demo_banner", DEMO_BANNER_BOX, want=True,
                timeout=LAUNCH_TIMEOUT,
            )
            if result and result.passed:
                logger.info("Altami Studio запущен (попытка %d)", attempt)
                return
            logger.warning(
                "Баннер не появился за %.0fс (попытка %d) — повторяю двойной клик",
                LAUNCH_TIMEOUT, attempt,
            )
        pytest.fail(
            f"Не удалось запустить Altami Studio двойным кликом по ярлыку "
            f"{ALTAMI_SHORTCUT}"
        )

    async def test_altami_studio_demo_launch(self):
        """Полный сценарий: ярлык → запуск → баннер → окна → «Пропустить»."""
        # 1. Ярлык на рабочем столе есть (сверяем значок, игнорируя версию).
        logger.info("Проверяю, что ярлык «Altami Studio» есть на рабочем столе")
        await self._park_mouse()
        await self.assert_region(
            "altami_shortcut", SHORTCUT_ICON_BOX, threshold=SHORTCUT_THRESHOLD
        )

        # 2-3. Запуск двойным кликом и проверка надписи «Демо-версия».
        logger.info("Запускаю Altami Studio двойным кликом по ярлыку")
        await self._launch_altami()
        logger.info("Проверяю надпись «Демо-версия» на баннере")
        await self._park_mouse()
        await self.assert_region("altami_demo_banner", DEMO_BANNER_BOX)

        # 4. Дождаться окна «Демо версия» и закрыть его.
        logger.info("Жду окно «Демо версия» и нажимаю «Закрыть»")
        dialog = await self._wait_region(
            "altami_demo_dialog", DEMO_DIALOG_BOX, want=True, timeout=DIALOG_TIMEOUT
        )
        assert dialog and dialog.passed, "Окно «Altami Studio Демо версия» не появилось"
        await self.glide_click(*DEMO_CLOSE_BTN)

        # 5. Дождаться окна восстановления: есть окно и UI не поломался.
        logger.info("Жду окно «Восстановить состояние» и проверяю UI")
        restore = await self._wait_region(
            "altami_restore_title", RESTORE_TITLE_BOX, want=True,
            timeout=RESTORE_TIMEOUT,
        )
        assert restore and restore.passed, (
            "Окно «Восстановить состояние приложения» не появилось после «Закрыть»"
        )
        await self._park_mouse()
        await self.assert_region("altami_app_toolbar", APP_TOOLBAR_BOX)

        # 6. «Пропустить» — окно должно исчезнуть.
        logger.info("Нажимаю «Пропустить» и жду исчезновения окна")
        await self.glide_click(*RESTORE_SKIP_BTN)
        gone = await self._wait_region(
            "altami_restore_title", RESTORE_TITLE_BOX, want=False,
            timeout=DISMISS_TIMEOUT,
        )
        assert gone and not gone.passed, (
            "Окно «Восстановить состояние» не исчезло после «Пропустить»: "
            f"область всё ещё совпадает с эталоном заголовка (SSIM={gone.score:.6f})"
            if gone else "не удалось снять кадр после «Пропустить»"
        )
        logger.info("Окно восстановления закрыто — сценарий завершён, "
                    "Altami Studio остаётся открытым")
