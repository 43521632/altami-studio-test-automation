"""UI-тест запуска Altami Studio на Windows (двойной клик по ярлыку).

Сценарий (один непрерывный поток, состояние переходит по шагам):

1. На рабочем столе есть ярлык «Altami Studio 4.1 x64». Проверяем, что он есть,
   сверяя ТОЛЬКО значок (логотип) — версия «4.1 x64» в подписи игнорируется,
   чтобы тест не падал при обновлении версии.
2. Двойной клик по ярлыку — запуск приложения.
3. Во время запуска показывается баннер-заставка «ALTAMI STUDIO v.4.1» с
   надписью «Демо-версия». ГЛАВНАЯ проверка теста — что надпись есть.
4. Одновременно всплывает окно «Altami Studio Демо версия» с кнопкой «Закрыть» —
   нажимаем её.
5. Открывается окно «Altami Studio: Восстановить состояние приложения».
   Проверяем, что окно есть и что UI приложения не поломался.
6. Нажимаем «Пропустить» — окно исчезает, тест завершён.

Приложение НАМЕРЕННО остаётся открытым в конце — как и в кейсе для Astra:
тест продолжат расширять с этой точки, поэтому шага закрытия здесь нет.

Отличия от Astra:
* запуск не из меню «Пуск», а двойным кликом по ярлыку рабочего стола;
* ярлык опознаётся по значку, а не по подписи с версией;
* задержки увеличены — ВМ на Windows работает медленнее.

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
# Заголовок окна «Восстановить состояние приложения» — доказывает, что окно
# есть. Список сессий с датами намеренно вне области.
RESTORE_TITLE_BOX = (752, 420, 1135, 442)
# Панель инструментов главного окна — доказывает, что UI не поломался.
APP_TOOLBAR_BOX = (0, 50, 1130, 85)

# --- Тайминги (секунды), увеличены под медленную Windows-ВМ -------------------
LAUNCH_TIMEOUT = 18.0    # ждать появления баннера после двойного клика
POLL_INTERVAL = 2.0      # как часто проверять, появился ли баннер
RESTORE_WAIT = 10.0      # окно восстановления состояния появляется
DISMISS_WAIT = 4.0       # окно закрывается после клика


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
        await asyncio.sleep(0.3)

    async def _launch_altami(self, attempts: int = 2) -> None:
        """Двойным кликом по ярлыку запустить приложение и дождаться баннера.

        Успех подтверждается появлением баннера-заставки. Если за отведённое
        время баннер не появился — двойной клик не сработал, повторяем.
        Проверка ПОСЛЕ таймаута, а не сразу: на Windows запуск не мгновенный,
        иначе повторный клик открыл бы второй экземпляр.
        """
        loop = asyncio.get_event_loop()
        for attempt in range(1, attempts + 1):
            await self.glide(*ALTAMI_SHORTCUT)
            await asyncio.sleep(0.4)
            await self.double_click(*ALTAMI_SHORTCUT)

            deadline = loop.time() + LAUNCH_TIMEOUT
            while loop.time() < deadline:
                await asyncio.sleep(POLL_INTERVAL)
                await self._park_mouse()
                if (await self.compare_region(
                    "altami_demo_banner", DEMO_BANNER_BOX
                )).passed:
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

        # 4. Закрыть окно «Altami Studio Демо версия».
        logger.info("Нажимаю «Закрыть» в окне «Демо версия»")
        await self.glide_click(*DEMO_CLOSE_BTN)
        await asyncio.sleep(RESTORE_WAIT)

        # 5. Окно восстановления состояния: есть окно и UI не поломался.
        logger.info("Проверяю окно «Восстановить состояние» и UI приложения")
        await self._park_mouse()
        await self.assert_region("altami_restore_title", RESTORE_TITLE_BOX)
        await self.assert_region("altami_app_toolbar", APP_TOOLBAR_BOX)

        # 6. «Пропустить» — окно должно исчезнуть.
        logger.info("Нажимаю «Пропустить»")
        await self.glide_click(*RESTORE_SKIP_BTN)
        await asyncio.sleep(DISMISS_WAIT)

        await self._park_mouse()
        gone = await self.compare_region("altami_restore_title", RESTORE_TITLE_BOX)
        assert not gone.passed, (
            "Окно «Восстановить состояние» не исчезло после «Пропустить»: "
            f"область всё ещё совпадает с эталоном заголовка (SSIM={gone.score:.6f})"
        )
        logger.info("Окно восстановления закрыто — сценарий завершён, "
                    "Altami Studio остаётся открытым")
