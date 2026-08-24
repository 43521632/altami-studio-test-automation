"""UI-тест окна «Настройки быстрой съемки» Altami Studio на Windows.

Стартовое состояние — конечное состояние TC-92: приложение уже запущено,
лицензия активирована, окно «О программе» закрыто, на экране главное окно.
Состояние тест НЕ готовит: первым шагом он сверяет экран с эталоном стартового
состояния и при расхождении падает, ничего не нажимая.

Сценарий:

1. Наводим курсор на пункт «Настройки» в строке меню главного окна.
2. В выпадающем меню наводим на «Настройки быстрой съемки» и кликаем.
3. Открывается окно «Настройки быстрой съемки». Проверяем, что название
   окна отображается полностью, а также кнопки «ОК» и «Отмена».
4. Проверяем все параметры окна: Путь, Формат, Качество, Сохранять фигуры,
   Префикс, Использовать текущую дату (год, месяц, день), Имя файла, Папка,
   Разделять в имени, Открывать сохранённый документ в приложении.
5. Нажимаем кнопку ОК — окно закрывается, тест завершён.

Приложение НАМЕРЕННО остаётся открытым в конце — как в TC-85, TC-86 и TC-92:
на нём строятся следующие сценарии.

Имя файла и порядок в прогоне. Тесты с маркером `app` идут в конце прогона, а
между собой — в порядке сбора, то есть по алфавиту имён файлов (сортировка в
tests/conftest.py стабильна). «menu_quick_settings» стоит после «menu_about»,
поэтому цепочка складывается правильно: запуск (TC-85) -> активация (TC-86) ->
окно «О программе» (TC-92) -> этот тест. Переименование файла порядок сломает.

ПРОВЕРКА ПАРАМЕТРОВ — СРАВНЕНИЕ С ЭТАЛОНОМ. Все пункты проверяются сравнением
статичной области кадра с эталоном (SSIM), см. base_tests.assert_region. Каждый
параметр сверяется своей областью, чтобы изолировать изменения: сдвиг одного
элемента не завалит все проверки сразу.

ЭТАЛОНЫ СНИМАТЬ ТОЛЬКО С УСТОЯВШЕГОСЯ ОКНА. Если эталона нет, он создаётся
из первого же снятого кадра (правило бутстрапа, см. screenshot_compare).
Поэтому, если эталоны удалили, создавать их надо с ЗАВЕДОМО устоявшегося
кадра: открыть окно руками, выждать пару секунд и вырезать области.

Координаты и области сняты на живой ВМ 24.08.2026 в видеорежиме 1920x1200
Altami Studio 4.1 (лицензированная версия).
"""

import asyncio
import logging

import pytest

from tests.base_tests import BaseVMTest

logger = logging.getLogger(__name__)

# --- Координаты кликов (пиксели гостя, режим 1920x1200) ----------------------
SETTINGS_MENU = (476, 34)         # пункт «Настройки» в строке меню главного окна
QUICK_CAPTURE_ITEM = (476, 159)   # «Настройки быстрой съемки» в меню «Настройки»
OK_BUTTON = (1045, 775)           # середина кнопки ОК окна настроек (текст на y=763-786, x=1000-1090)
CANCEL_BUTTON = (1184, 775)       # середина кнопки Отмена окна настроек
MOUSE_PARK = (1750, 250)          # нейтральная точка: увести курсор из кадра

# --- Области для сравнения с эталоном (left, top, right, bottom) -------------
# Заголовок окна «Настройки быстрой съемки». Доказывает, что окно открылось, и
# по нему же видно, что оно закрылось после OK.
QUICK_CAPTURE_TITLE_BOX = (720, 340, 1140, 352)
# Панель инструментов главного окна — по ней сверяется стартовое состояние.
APP_TOOLBAR_BOX = (0, 50, 1130, 85)

# Параметры окна «Настройки быстрой съемки». Каждый — область вокруг своей
# текстовой метки. Все области сняты на живой ВМ 24.08.2026.

# Путь — поле с путём к каталогу сохранения
SETTING_PATH_BOX = (715, 387, 770, 397)
# Формат — выпадающий список с форматами файлов
SETTING_FORMAT_BOX = (715, 417, 790, 427)
# Качество — ползунок или числовое поле
SETTING_QUALITY_BOX = (710, 479, 790, 488)
# Сохранять фигуры — чекбокс с текстом
SETTING_SAVE_SHAPES_BOX = (705, 540, 870, 548)
# Префикс — текстовое поле
SETTING_PREFIX_BOX = (705, 565, 790, 578)
# Использовать текущую дату (год, месяц, день) — чекбокс с текстом
SETTING_USE_DATE_BOX = (705, 595, 910, 605)
# Год — чекбокс под текущей датой
SETTING_DATE_YEAR_BOX = (705, 623, 745, 633)
# Месяц — чекбокс под текущей датой
SETTING_DATE_MONTH_BOX = (926, 623, 972, 633)
# День — чекбокс под текущей датой
SETTING_DATE_DAY_BOX = (1172, 623, 1200, 633)
# Имя файла — поле с именем
SETTING_FILENAME_BOX = (705, 657, 795, 672)
# Папка — поле с путём к папке
SETTING_FOLDER_BOX = (705, 683, 755, 693)
# Разделять в имени — чекбокс
SETTING_SEPARATOR_BOX = (705, 683, 870, 693)
# Открывать сохранённый документ в приложении — чекбокс
SETTING_OPEN_AFTER_BOX = (705, 734, 1060, 747)

# Кнопки ОК и Отмена в нижней части окна
OK_BUTTON_BOX = (1000, 775, 1090, 795)
CANCEL_BUTTON_BOX = (1148, 775, 1210, 795)

# --- Таймауты опроса (секунды) -----------------------------------------------
DIALOG_TIMEOUT = 8.0      # появление окна настроек после клика по пункту меню
DISMISS_TIMEOUT = 6.0     # исчезновение окна после OK
MENU_SETTLE = 0.8         # раскрытие выпадающего меню «Настройки»
SUBMENU_SETTLE = 0.6      # ожидание подсветки пункта подменю
POLL_INTERVAL = 0.4       # как часто опрашивать экран


@pytest.mark.windows
@pytest.mark.ui
# app: приложение остаётся открытым после теста, поэтому прогон идёт последним —
# иначе окно Altami перекрывает рабочий стол тестам, которые сверяют его с
# эталоном (сортировка — в tests/conftest.py).
@pytest.mark.app
class TestWindowsMenuQuickSettings(BaseVMTest):
    """Окно «Настройки быстрой съемки»: открытие, параметры, закрытие по OK."""

    vm_id = "windows"

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

    async def _require_start_state(self) -> None:
        """Сверить экран со стартовым состоянием теста. Не совпало — падение.

        Стартовое состояние — конечное состояние TC-92: Altami Studio открыт,
        на экране главное окно с панелью инструментов. Тест ничего не нажимает
        до этой проверки и не пытается состояние подготовить: несовпадение —
        это сообщение, а не повод что-то открыть.
        """
        await self._park_mouse()
        toolbar = await self.compare_region("altami_app_toolbar", APP_TOOLBAR_BOX)
        if toolbar.passed:
            logger.info("Стартовое состояние подтверждено: Altami Studio открыт")
            return

        message = [
            "ВМ не в стартовом состоянии — тест не запускался.",
            "  Нужно: Altami Studio открыт, на экране главное окно "
            "(конечное состояние TC-92).",
            f"  Сейчас: панель инструментов не совпала с эталоном, "
            f"SSIM={toolbar.score:.6f} (нужно > {toolbar.threshold}).",
            f"    текущий: {toolbar.current_path}",
            f"    эталон:  {toolbar.baseline_path}",
        ]
        if toolbar.diff_path:
            message.append(f"    различия: {toolbar.diff_path}")
        message.append(
            "  Подготовьте состояние вручную (или прогоном TC-85, TC-86 и TC-92) "
            "и запустите снова."
        )
        pytest.fail("\n".join(message))

    async def test_quick_capture_settings(self):
        """Настройки -> Настройки быстрой съемки: открытие, параметры, OK."""
        # 0. Стартовое состояние TC-92: главное окно Altami Studio открыто.
        await self._require_start_state()

        # 1. Навести на пункт «Настройки» в строке меню и кликнуть.
        logger.info("Навожу на пункт «Настройки» в строке меню")
        await self.glide_click(*SETTINGS_MENU)
        await asyncio.sleep(MENU_SETTLE)

        # 2. Навести на «Настройки быстрой съемки» и кликнуть.
        logger.info("Навожу на «Настройки быстрой съемки» и кликаю")
        await self.glide(*QUICK_CAPTURE_ITEM)
        await asyncio.sleep(SUBMENU_SETTLE)
        await self.click(*QUICK_CAPTURE_ITEM)

        # 3. Дождаться окна «Настройки быстрой съемки».
        logger.info("Жду появления окна «Настройки быстрой съемки»")
        opened = await self._wait_region(
            "altami_quick_capture_title", QUICK_CAPTURE_TITLE_BOX,
            want=True, timeout=DIALOG_TIMEOUT,
        )
        assert opened and opened.passed, (
            "Окно «Настройки быстрой съемки» не открылось: "
            f"SSIM={opened.score:.6f}" if opened
            else "не удалось снять кадр после клика по «Настройки быстрой съемки»"
        )

        # 4. Проверить, что заголовок окна отображается полностью.
        logger.info("Проверяю заголовок окна")
        await self._park_mouse()
        await self.assert_region("altami_quick_capture_title", QUICK_CAPTURE_TITLE_BOX)

        # 5. Проверить все параметры в окне.
        logger.info("Проверяю параметр «Путь»")
        await self._park_mouse()
        await self.assert_region("altami_setting_path", SETTING_PATH_BOX)

        logger.info("Проверяю параметр «Формат»")
        await self._park_mouse()
        await self.assert_region("altami_setting_format", SETTING_FORMAT_BOX)

        logger.info("Проверяю параметр «Качество»")
        await self._park_mouse()
        await self.assert_region("altami_setting_quality", SETTING_QUALITY_BOX)

        logger.info("Проверяю параметр «Сохранять фигуры»")
        await self._park_mouse()
        await self.assert_region("altami_setting_save_shapes", SETTING_SAVE_SHAPES_BOX)

        logger.info("Проверяю параметр «Префикс»")
        await self._park_mouse()
        await self.assert_region("altami_setting_prefix", SETTING_PREFIX_BOX)

        logger.info("Проверяю параметр «Использовать текущую дату»")
        await self._park_mouse()
        await self.assert_region("altami_setting_use_date", SETTING_USE_DATE_BOX)

        logger.info("Проверяю чекбокс «Год»")
        await self._park_mouse()
        await self.assert_region("altami_setting_date_year", SETTING_DATE_YEAR_BOX)

        logger.info("Проверяю чекбокс «Месяц»")
        await self._park_mouse()
        await self.assert_region("altami_setting_date_month", SETTING_DATE_MONTH_BOX)

        logger.info("Проверяю чекбокс «День»")
        await self._park_mouse()
        await self.assert_region("altami_setting_date_day", SETTING_DATE_DAY_BOX)

        logger.info("Проверяю параметр «Имя файла»")
        await self._park_mouse()
        await self.assert_region("altami_setting_filename", SETTING_FILENAME_BOX)

        logger.info("Проверяю параметр «Папка»")
        await self._park_mouse()
        await self.assert_region("altami_setting_folder", SETTING_FOLDER_BOX)

        logger.info("Проверяю параметр «Разделять в имени»")
        await self._park_mouse()
        await self.assert_region("altami_setting_separator", SETTING_SEPARATOR_BOX)

        logger.info("Проверяю параметр «Открывать сохранённый документ в приложении»")
        await self._park_mouse()
        await self.assert_region("altami_setting_open_after", SETTING_OPEN_AFTER_BOX)

        # 6. Проверить, что кнопки ОК и Отмена отображаются.
        logger.info("Проверяю кнопку ОК")
        await self._park_mouse()
        await self.assert_region("altami_ok_button", OK_BUTTON_BOX)

        logger.info("Проверяю кнопку Отмена")
        await self._park_mouse()
        await self.assert_region("altami_cancel_button", CANCEL_BUTTON_BOX)

        # 7. Нажать ОК — окно должно закрыться.
        logger.info("Нажимаю ОК и жду закрытия окна")
        await self.glide_click(*OK_BUTTON)
        gone = await self._wait_region(
            "altami_quick_capture_title", QUICK_CAPTURE_TITLE_BOX,
            want=False, timeout=DISMISS_TIMEOUT,
        )
        assert gone and not gone.passed, (
            "Окно «Настройки быстрой съемки» не закрылось после ОК: заголовок "
            f"всё ещё совпадает с эталоном (SSIM={gone.score:.6f})"
            if gone else "не удалось снять кадр после клика по ОК"
        )

        logger.info("Сценарий завершён — Altami Studio остаётся открытым")