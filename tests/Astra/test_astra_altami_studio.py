"""UI-тест запуска Altami Studio из меню «Пуск» на Astra Linux.

Сценарий (один непрерывный поток, состояние переходит по шагам):

1. Открыть меню «Пуск» (звезда в углу панели задач).
2. Навести на категорию «Научные» — раскрывается подменю.
3. Навести на ярлык «Altami Studio» и кликнуть — запуск приложения.
4. Во время запуска показывается баннер-заставка «ALTAMI STUDIO v.4.1»
   с надписью «Демо-версия». ГЛАВНАЯ проверка теста — что надпись есть.
5. Одновременно всплывает окно «Altami Studio Демо версия» с кнопкой
   «Закрыть» — после ~8 с нажимаем её.
6. Через ~4 с открывается окно «Altami Studio: Восстановить состояние
   приложения». Проверяем, что окно есть и что UI приложения не поломался.
7. Нажимаем «Пропустить» — окно исчезает, тест завершён.

Приложение НАМЕРЕННО остаётся открытым в конце: тест продолжат расширять
с этой точки, поэтому здесь нет шага закрытия Altami Studio.

Проверка надписей — не OCR, а сравнение статичной области кадра с эталоном
(SSIM), см. base_tests.assert_region. Координаты и области сняты на живой ВМ
21.07.2026 в видеорежиме рабочего стола 1920x1200.
"""

import asyncio
import logging

import pytest

from tests.base_tests import BaseVMTest

logger = logging.getLogger(__name__)

# --- Координаты кликов (пиксели гостя, режим рабочего стола 1920x1200) -------
START_STAR = (22, 1174)      # звезда «Пуск» в левом углу панели задач
NAUCHNYE_TAB = (250, 873)    # категория «Научные» (наводим — раскрывается подменю)
ALTAMI_ITEM = (560, 715)     # ярлык «Altami Studio» в подменю «Научные»
DEMO_CLOSE_BTN = (1147, 563)  # кнопка «Закрыть» в окне «Altami Studio Демо версия»
RESTORE_SKIP_BTN = (1101, 634)  # кнопка «Пропустить» в окне восстановления
MOUSE_PARK = (1750, 250)     # нейтральная точка: увести курсор из кадра

# --- Области для сравнения с эталоном (left, top, right, bottom) -------------
# Баннер-заставка: полоса с текстом «ALTAMI STUDIO / Демо-версия / v.4.1».
# Окно «Демо версия» перекрывает логотип сверху, но НЕ эту полосу.
DEMO_BANNER_BOX = (668, 712, 1256, 878)
# Колонка категорий открытого меню «Пуск» — проверяем, что меню раскрылось.
MENU_OPEN_BOX = (100, 690, 440, 935)
# Правая колонка подменю «Научные» с ярлыками — проверяем, что оно раскрылось.
NAUCHNYE_SUBMENU_BOX = (466, 696, 772, 778)
# Красная строка заголовка окна «Восстановить состояние приложения» —
# доказывает, что окно есть. Список сессий с датами намеренно вне области.
RESTORE_TITLE_BOX = (744, 386, 1162, 416)
# Панель инструментов главного окна Altami Studio — доказывает, что UI не
# поломался (иконки отрисовались на своих местах).
APP_TOOLBAR_BOX = (0, 54, 1132, 96)

# --- Тайминги (секунды) ------------------------------------------------------
MENU_OPEN_WAIT = 1.5     # меню «Пуск» раскрывается
SUBMENU_WAIT = 2.0       # подменю «Научные» выезжает по наведению
SPLASH_WAIT = 8.0        # запуск приложения и появление баннера/окна «Демо»
RESTORE_WAIT = 4.0       # окно восстановления состояния появляется
DISMISS_WAIT = 1.5       # окно закрывается после клика


@pytest.mark.astra
@pytest.mark.ui
# app: приложение остаётся открытым после теста, поэтому прогон идёт последним —
# иначе окно Altami перекрывает рабочий стол тестам, которые сверяют его с
# эталоном (сортировка — в tests/conftest.py).
@pytest.mark.app
class TestAstraAltamiStudio(BaseVMTest):
    """Запуск Altami Studio из меню «Научные» и проверка стартовых окон."""

    vm_id = "astra"

    # Вход в систему уже выполнен фикстурой guest_login — на рабочем столе.

    async def _park_mouse(self) -> None:
        """Увести курсор в нейтральную точку, чтобы он не попал в кадр."""
        await self.qmp.mouse_move(*MOUSE_PARK)
        self._ptr = MOUSE_PARK
        await asyncio.sleep(0.3)

    async def _open_start_menu(self, attempts: int = 3) -> None:
        """Кликнуть по звезде «Пуск» и убедиться, что меню раскрылось.

        Первое событие ввода в свежей QMP-сессии иногда теряется, и клик по
        звезде не срабатывает. Тогда весь сценарий шёл бы вслепую по рабочему
        столу. Поэтому проверяем, что колонка категорий появилась, и при
        необходимости повторяем клик.
        """
        for attempt in range(1, attempts + 1):
            await self.glide_click(*START_STAR)
            await asyncio.sleep(MENU_OPEN_WAIT)
            await self._park_mouse()
            result = await self.compare_region("altami_menu_open", MENU_OPEN_BOX)
            if result.passed:
                logger.info("Меню «Пуск» открыто (попытка %d)", attempt)
                return
            logger.warning(
                "Меню «Пуск» не открылось (попытка %d, SSIM=%.4f) — повторяю",
                attempt, result.score,
            )
        pytest.fail(
            f"Меню «Пуск» не открылось за {attempts} попыток — "
            f"клик по звезде {START_STAR} не срабатывает"
        )

    async def _open_nauchnye_submenu(self, attempts: int = 3) -> None:
        """Навести на «Научные» и убедиться, что подменю с ярлыками раскрылось.

        Подменю fly раскрывается по таймеру наведения, а одиночный «телепорт»
        курсора QMP-планшетом Qt как движение не распознаёт — заходим в строку
        плавным перемещением (glide). Курсор при проверке остаётся в строке
        «Научные» в левой колонке и в область подменю не попадает.
        """
        for attempt in range(1, attempts + 1):
            await self.glide(*NAUCHNYE_TAB)
            await asyncio.sleep(SUBMENU_WAIT)
            result = await self.compare_region(
                "altami_nauchnye_submenu", NAUCHNYE_SUBMENU_BOX
            )
            if result.passed:
                logger.info("Подменю «Научные» раскрыто (попытка %d)", attempt)
                return
            logger.warning(
                "Подменю «Научные» не раскрылось (попытка %d, SSIM=%.4f) — повторяю",
                attempt, result.score,
            )
        pytest.fail(
            f"Подменю «Научные» не раскрылось за {attempts} попыток — "
            f"наведение на {NAUCHNYE_TAB} не разворачивает список ярлыков"
        )

    async def _launch_altami(self, attempts: int = 3) -> None:
        """Навести на ярлык «Altami Studio» в подменю и кликнуть — запустить.

        Ярлык должен сначала подсветиться под курсором (glide), затем клик его
        запускает и меню закрывается. Если клик «холодный» и не сработал —
        меню остаётся открытым, тогда повторяем наведение и клик.
        """
        for attempt in range(1, attempts + 1):
            await self.glide(*ALTAMI_ITEM)
            await asyncio.sleep(0.6)
            await self.click(*ALTAMI_ITEM)
            await asyncio.sleep(1.0)
            menu = await self.compare_region("altami_menu_open", MENU_OPEN_BOX)
            if not menu.passed:
                logger.info("Altami Studio запущен (попытка %d)", attempt)
                return
            logger.warning(
                "Ярлык «Altami Studio» не запустился (попытка %d) — меню ещё "
                "открыто, повторяю", attempt,
            )
        pytest.fail(
            f"Не удалось запустить Altami Studio за {attempts} попыток — "
            f"клик по ярлыку {ALTAMI_ITEM} не срабатывает"
        )

    async def test_altami_studio_demo_launch(self):
        """Полный сценарий: меню → запуск → баннер → окна → «Пропустить»."""
        # 1. Открыть меню «Пуск» (с проверкой и повтором клика).
        logger.info("Открываю меню «Пуск»")
        await self._open_start_menu()

        # 2. Навести на «Научные» — подменю раскрывается (с проверкой и повтором).
        logger.info("Навожу на категорию «Научные»")
        await self._open_nauchnye_submenu()

        # 3. Навести на «Altami Studio» и запустить.
        logger.info("Запускаю Altami Studio")
        await self._launch_altami()

        # 4. Баннер-заставка с надписью «Демо-версия» — главная проверка.
        logger.info("Жду баннер и проверяю надпись «Демо-версия»")
        await asyncio.sleep(SPLASH_WAIT)
        await self._park_mouse()
        await self.assert_region("altami_demo_banner", DEMO_BANNER_BOX)

        # 5. Закрыть окно «Altami Studio Демо версия».
        logger.info("Нажимаю «Закрыть» в окне «Демо версия»")
        await self.glide_click(*DEMO_CLOSE_BTN)
        await asyncio.sleep(RESTORE_WAIT)

        # 6. Окно восстановления состояния: есть окно и UI не поломался.
        logger.info("Проверяю окно «Восстановить состояние» и UI приложения")
        await self._park_mouse()
        await self.assert_region("altami_restore_title", RESTORE_TITLE_BOX)
        await self.assert_region("altami_app_toolbar", APP_TOOLBAR_BOX)

        # 7. «Пропустить» — окно должно исчезнуть.
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
