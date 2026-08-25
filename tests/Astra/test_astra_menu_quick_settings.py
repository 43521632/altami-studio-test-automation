"""UI-тест окна «Настройки быстрой съемки» Altami Studio на Astra Linux.

Парный тест к TC-94 для Windows: тот же сценарий, свои координаты.

Стартовое состояние — конечное состояние TC-93: приложение уже запущено,
окно «О программе» закрыто, на экране главное окно. Состояние тест НЕ готовит:
первым шагом он сверяет экран с эталоном стартового состояния и при
расхождении падает, ничего не нажимая.

Сценарий:

1. Наводим курсор на пункт «Настройки» в строке меню главного окна.
2. В выпадающем меню наводим на «Настройки быстрой съемки» и кликаем.
3. Открывается окно «Настройки быстрой съемки». Проверяем, что название
   окна отображается полностью, а также кнопки «ОК» и «Отмена».
4. Проверяем все параметры окна: Путь, Формат, Качество, Сохранять фигуры,
   Префикс, Использовать текущую дату (год, месяц, день), Имя файла, Папка,
   Разделять в имени, Открывать сохранённый документ в приложении.
5. Нажимаем кнопку ОК — окно закрывается, тест завершён.

Приложение НАМЕРЕННО остаётся открытым в конце — как в TC-84, TC-87 и TC-93:
на нём строятся следующие сценарии.

Имя файла и порядок в прогоне. Тесты с маркером `app` идут в конце прогона, а
между собой — в порядке сбора, то есть по алфавиту имён файлов (сортировка в
tests/conftest.py стабильна). «menu_quick_settings» стоит после «menu_about»,
поэтому цепочка складывается правильно: запуск (TC-84) -> активация (TC-87) ->
окно «О программе» (TC-93) -> этот тест. Переименование файла порядок сломает.

Координаты и области сняты на живой ВМ 24.08.2026 в видеорежиме 1920x1200
Altami Studio 4.1 (лицензированная версия, Astra Linux 1.8).
"""

import asyncio
import logging

import pytest

from tests.base_tests import BaseVMTest

logger = logging.getLogger(__name__)

# --- Координаты кликов (пиксели гостя, режим 1920x1200) ----------------------
SETTINGS_MENU = (440, 38)         # пункт «Настройки» в строке меню главного окна
QUICK_CAPTURE_ITEM = (440, 170)   # «Настройки быстрой съемки» в меню «Настройки»
OK_BUTTON = (1090, 745)           # середина кнопки ОК окна настроек
CANCEL_BUTTON = (1195, 745)       # середина кнопки Отмена окна настроек
MOUSE_PARK = (1750, 250)          # нейтральная точка: увести курсор из кадра

# --- Области для сравнения с эталоном (left, top, right, bottom) -------------
# Заголовок окна «Настройки быстрой съемки» — текст на красной строке заголовка.
QUICK_CAPTURE_TITLE_BOX = (700, 314, 1060, 326)
# Панель инструментов главного окна — по ней сверяется стартовое состояние.
APP_TOOLBAR_BOX = (0, 54, 1132, 96)

# Параметры окна «Настройки быстрой съемки». Каждый — область вокруг своей
# текстовой метки. Координаты сняты на живой ВМ 24.08.2026.

# Путь — поле с путём к каталогу сохранения
SETTING_PATH_BOX = (708, 352, 780, 372)
# Формат — выпадающий список с форматами файлов
SETTING_FORMAT_BOX = (708, 383, 800, 403)
# Качество — ползунок или числовое поле
SETTING_QUALITY_BOX = (708, 407, 820, 418)
# Сохранять фигуры — чекбокс с текстом
SETTING_SAVE_SHAPES_BOX = (708, 447, 870, 457)
# Префикс — текстовое поле
SETTING_PREFIX_BOX = (708, 504, 840, 514)
# Использовать текущую дату (год, месяц, день) — чекбокс с текстом
SETTING_USE_DATE_BOX = (708, 531, 900, 541)
# Год — чекбокс под текущей датой
SETTING_DATE_YEAR_BOX = (708, 561, 760, 569)
# Месяц — чекбокс под текущей датой
SETTING_DATE_MONTH_BOX = (830, 561, 890, 569)
# День — чекбокс под текущей датой
SETTING_DATE_DAY_BOX = (950, 561, 1000, 569)
# Имя файла — поле с именем
SETTING_FILENAME_BOX = (708, 593, 810, 603)
# Папка — поле с путём к папке
SETTING_FOLDER_BOX = (708, 626, 770, 640)
# Разделять в имени — чекбокс
SETTING_SEPARATOR_BOX = (708, 626, 870, 640)
# Открывать сохранённый документ в приложении — чекбокс
SETTING_OPEN_AFTER_BOX = (708, 707, 1050, 717)

# Кнопки ОК и Отмена в нижней части окна
OK_BUTTON_BOX = (1036, 735, 1142, 755)
CANCEL_BUTTON_BOX = (1150, 735, 1200, 755)

# --- Таймауты опроса (секунды) -----------------------------------------------
DIALOG_TIMEOUT = 8.0      # появление окна настроек после клика по пункту меню
DISMISS_TIMEOUT = 6.0     # исчезновение окна после OK
MENU_SETTLE = 0.8         # раскрытие выпадающего меню «Настройки»
SUBMENU_SETTLE = 0.6      # ожидание подсветки пункта подменю
POLL_INTERVAL = 0.4       # как часто опрашивать экран

# --- Допуск на смещение окна -------------------------------------------------
# Дочерние окна на Astra встают от запуска к запуску с точностью до пары
# пикселей. Главное окно развёрнуто и не смещается.
DIALOG_SHIFT = 2


@pytest.mark.astra
@pytest.mark.ui
# app: приложение остаётся открытым после теста, поэтому прогон идёт последним —
# иначе окно Altami перекрывает рабочий стол тестам, которые сверяют его с
# эталоном (сортировка — в tests/conftest.py).
@pytest.mark.app
class TestAstraMenuQuickSettings(BaseVMTest):
    """Окно «Настройки быстрой съемки»: открытие, параметры, закрытие по OK."""

    vm_id = "astra"

    async def _park_mouse(self) -> None:
        """Увести курсор в нейтральную точку, чтобы он не попал в кадр."""
        await self.qmp.mouse_move(*MOUSE_PARK)
        self._ptr = MOUSE_PARK
        await asyncio.sleep(0.3)

    async def _wait_region(self, name, box, want=True, timeout=10.0, shift=0):
        """Опрашивать область, пока она (не) совпадёт с эталоном.

        want=True  — ждём появления (SSIM > порога);
        want=False — ждём исчезновения (SSIM <= порога).
        Возвращает последний ComparisonResult (по нему видно, дождались ли).

        shift — допуск на смещение окна (см. DIALOG_SHIFT).
        """
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        result = None
        while loop.time() < deadline:
            await self._park_mouse()
            result = await self.compare_region(name, box, shift=shift)
            if result.passed == want:
                return result
            await asyncio.sleep(POLL_INTERVAL)
        return result

    async def _require_start_state(self) -> None:
        """Сверить экран со стартовым состоянием теста. Не совпало — падение.

        Стартовое состояние — конечное состояние TC-93: Altami Studio открыт,
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
            "(конечное состояние TC-93).",
            f"  Сейчас: панель инструментов не совпала с эталоном, "
            f"SSIM={toolbar.score:.6f} (нужно > {toolbar.threshold}).",
            f"    текущий: {toolbar.current_path}",
            f"    эталон:  {toolbar.baseline_path}",
        ]
        if toolbar.diff_path:
            message.append(f"    различия: {toolbar.diff_path}")
        message.append(
            "  Подготовьте состояние вручную (или прогоном TC-84, TC-87 и TC-93) "
            "и запустите снова."
        )
        pytest.fail("\n".join(message))

    async def test_quick_capture_settings(self):
        """Настройки -> Настройки быстрой съемки: открытие, параметры, OK."""
        # 0. Стартовое состояние TC-93: главное окно Altami Studio открыто.
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
            want=True, timeout=DIALOG_TIMEOUT, shift=DIALOG_SHIFT,
        )
        assert opened and opened.passed, (
            "Окно «Настройки быстрой съемки» не открылось: "
            f"SSIM={opened.score:.6f}" if opened
            else "не удалось снять кадр после клика по «Настройки быстрой съемки»"
        )

        # 4. Проверить, что заголовок окна отображается полностью.
        logger.info("Проверяю заголовок окна")
        await self._park_mouse()
        await self.assert_region(
            "altami_quick_capture_title", QUICK_CAPTURE_TITLE_BOX,
            shift=DIALOG_SHIFT,
        )

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
        await self.assert_region("altami_ok_button", OK_BUTTON_BOX, shift=DIALOG_SHIFT)

        logger.info("Проверяю кнопку Отмена")
        await self._park_mouse()
        await self.assert_region("altami_cancel_button", CANCEL_BUTTON_BOX, shift=DIALOG_SHIFT)

        # 7. Нажать ОК — окно должно закрыться.
        logger.info("Нажимаю ОК и жду закрытия окна")
        await self.glide_click(*OK_BUTTON)
        gone = await self._wait_region(
            "altami_quick_capture_title", QUICK_CAPTURE_TITLE_BOX,
            want=False, timeout=DISMISS_TIMEOUT, shift=DIALOG_SHIFT,
        )
        assert gone and not gone.passed, (
            "Окно «Настройки быстрой съемки» не закрылось после ОК: заголовок "
            f"всё ещё совпадает с эталоном (SSIM={gone.score:.6f})"
            if gone else "не удалось снять кадр после клика по ОК"
        )

        logger.info("Сценарий завершён — Altami Studio остаётся открытым")