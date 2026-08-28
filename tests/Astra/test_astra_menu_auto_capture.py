"""UI-тест окна «Настройки Автосъемки» Altami Studio на Astra Linux.

Парный тест к TC-95 для Windows: тот же сценарий, свои координаты.

Стартовое состояние — конечное состояние TC-97: приложение уже запущено,
окно «Настройки быстрой съемки» закрыто, на экране главное окно. Состояние тест НЕ готовит:
первым шагом он сверяет экран с эталоном стартового состояния и при
расхождении падает, ничего не нажимая.

Сценарий:

1. Наводим курсор на пункт «Настройки» в строке меню главного окна.
2. В выпадающем меню наводим на «Настройки автосъемки» и кликаем.
3. Открывается окно «Настройки Автосъемки». Проверяем, что название
   окна отображается полностью, а также кнопки «ОК» и «Отмена».
4. Проверяем все параметры окна согласно шагам:
   - Путь
   - Формат
   - Качество
   - Сохранять фигуры
   - Префикс
   - Использовать текущую дату (Год, Месяц, День)
   - В имени
   - Файла
   - Папка
   - Разделять
5. Нажимаем кнопку ОК — окно закрывается, тест завершён.

Приложение НАМЕРЕННО остаётся открытым в конце — как в TC-84, TC-87, TC-93 и TC-97:
на нём строятся следующие сценарии.

Имя файла и порядок в прогоне. Тесты с маркером `app` идут в конце прогона, а
между собой — в порядке сбора, то есть по алфавиту имён файлов (сортировка в
tests/conftest.py стабильна). «menu_auto_capture» стоит после «menu_quick_settings»,
поэтому цепочка складывается правильно: запуск (TC-84) -> активация (TC-87) ->
окно «О программе» (TC-93) -> настройки быстрой съемки (TC-97) -> этот тест.
Переименование файла порядок сломает.

Координаты и области сняты на живой ВМ 28.08.2026 в видеорежиме 1920x1200
Altami Studio 4.1 (лицензированная версия, Astra Linux 1.8) с помощью OCR.
"""

import asyncio
import logging

import pytest

from tests.base_tests import BaseVMTest

logger = logging.getLogger(__name__)

# --- Координаты кликов (пиксели гостя, режим 1920x1200) ----------------------
# Координаты получены через OCR и ручную корректировку
SETTINGS_MENU = (475, 40)          # пункт «Настройки» в строке меню главного окна (OCR: 444-507, 34-47 -> центр 475, 40)
AUTO_CAPTURE_ITEM = (571, 196)     # «Настройки автосъемки» в меню «Настройки» (OCR: 537-606, 193-200 -> центр 571, 196)
OK_BUTTON = (1090, 745)            # середина кнопки ОК окна настроек (из TC-97)
CANCEL_BUTTON = (1195, 745)        # середина кнопки Отмена окна настроек (из TC-97)
MOUSE_PARK = (1750, 250)           # нейтральная точка: увести курсор из кадра

# --- Области для сравнения с эталоном (left, top, right, bottom) -------------
# Заголовок окна «Настройки Автосъемки» — текст на красной строке заголовка.
# Ориентировочно, как в TC-97, но проверено по скриншоту
AUTO_CAPTURE_TITLE_BOX = (680, 314, 1080, 326)
# Панель инструментов главного окна — по ней сверяется стартовое состояние.
APP_TOOLBAR_BOX = (0, 54, 1132, 96)

# Параметры окна «Настройки Автосъемки». Каждый — область вокруг своей
# текстовой метки. Координаты сняты на живой ВМ 28.08.2026 с помощью OCR
# и уточнены вручную для недостающих элементов.

# Путь — поле с путём к каталогу сохранения (OCR: 705, 345, 741, 381)
SETTING_PATH_BOX = (705, 345, 741, 381)
# Формат — выпадающий список с форматами файлов (ориентировочно между Путь и Качество)
SETTING_FORMAT_BOX = (705, 380, 741, 416)
# Качество — ползунок или числовое поле (ориентировочно между Формат и Сохранять фигуры)
SETTING_QUALITY_BOX = (705, 415, 741, 451)
# Сохранять фигуры — чекбокс с текстом (OCR: 724, 525, 795, 547)
SETTING_SAVE_SHAPES_BOX = (724, 525, 795, 547)
# Префикс — текстовое поле (OCR: 707, 553, 767, 576)
SETTING_PREFIX_BOX = (707, 553, 767, 576)
# Использовать текущую дату (год, месяц, день) — чекбокс с текстом (ориентировочно)
SETTING_USE_DATE_BOX = (705, 580, 920, 600)
# Год — чекбокс под текущей датой (OCR: 736, 652, 764, 673)
SETTING_DATE_YEAR_BOX = (736, 652, 764, 673)
# Месяц — чекбокс под текущей датой (OCR: 785, 652, 832, 673)
SETTING_DATE_MONTH_BOX = (785, 652, 832, 673)
# День — чекбокс под текущей датой (OCR: 853, 652, 892, 673)
SETTING_DATE_DAY_BOX = (853, 652, 892, 673)
# В имени — чекбокс (OCR: 906, 616, 954, 633)
SETTING_IN_NAME_BOX = (906, 616, 954, 633)
# Файла — поле с именем файла (OCR: 927, 647, 974, 667)
SETTING_FILENAME_BOX = (927, 647, 974, 667)
# Папка — поле с путём к папке (ориентировочно после Файла)
SETTING_FOLDER_BOX = (705, 680, 741, 716)
# Разделять — чекбокс (ориентировочно после Папка)
SETTING_SEPARATOR_BOX = (705, 715, 870, 731)

# Кнопки ОК и Отмена в нижней части окна (из TC-97)
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
class TestAstraMenuAutoCapture(BaseVMTest):
    """Окно «Настройки Автосъемки»: открытие, параметры, закрытие по OK."""

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

        Стартовое состояние — конечное состояние TC-97: Altami Studio открыт,
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
            "(конечное состояние TC-97).",
            f"  Сейчас: панель инструментов не совпала с эталоном, "
            f"SSIM={toolbar.score:.6f} (нужно > {toolbar.threshold}).",
            f"    текущий: {toolbar.current_path}",
            f"    эталон:  {toolbar.baseline_path}",
        ]
        if toolbar.diff_path:
            message.append(f"    различия: {toolbar.diff_path}")
        message.append(
            "  Подготовьте состояние вручную (или прогоном TC-84, TC-87, TC-93 и TC-97) "
            "и запустите снова."
        )
        pytest.fail("\n".join(message))

    async def test_auto_capture_settings(self):
        """Настройки -> Настройки автосъемки: открытие, параметры, OK."""
        # 0. Стартовое состояние TC-97: главное окно Altami Studio открыто.
        await self._require_start_state()

        # 1. Навести на пункт «Настройки» в строке меню и кликнуть.
        logger.info("Навожу на пункт «Настройки» в строке меню")
        await self.glide_click(*SETTINGS_MENU)
        await asyncio.sleep(MENU_SETTLE)

        # 2. Навести на «Настройки автосъемки» и кликнуть.
        logger.info("Навожу на «Настройки автосъемки» и кликаю")
        await self.glide(*AUTO_CAPTURE_ITEM)
        await asyncio.sleep(SUBMENU_SETTLE)
        await self.click(*AUTO_CAPTURE_ITEM)

        # 3. Дождаться окна «Настройки Автосъемки».
        logger.info("Жду появления окна «Настройки Автосъемки»")
        opened = await self._wait_region(
            "altami_auto_capture_title", AUTO_CAPTURE_TITLE_BOX,
            want=True, timeout=DIALOG_TIMEOUT, shift=DIALOG_SHIFT,
        )
        assert opened and opened.passed, (
            "Окно «Настройки Автосъемки» не открылось: "
            f"SSIM={opened.score:.6f}" if opened
            else "не удалось снять кадр после клика по «Настройки автосъемки»"
        )

        # 4. Проверить, что заголовок окна отображается полностью.
        logger.info("Проверяю заголовок окна")
        await self._park_mouse()
        await self.assert_region(
            "altami_auto_capture_title", AUTO_CAPTURE_TITLE_BOX,
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

        logger.info("Проверяю параметр «В имени»")
        await self._park_mouse()
        await self.assert_region("altami_setting_in_name", SETTING_IN_NAME_BOX)

        logger.info("Проверяю параметр «Файла»")
        await self._park_mouse()
        await self.assert_region("altami_setting_filename", SETTING_FILENAME_BOX)

        logger.info("Проверяю параметр «Папка»")
        await self._park_mouse()
        await self.assert_region("altami_setting_folder", SETTING_FOLDER_BOX)

        logger.info("Проверяю параметр «Разделять»")
        await self._park_mouse()
        await self.assert_region("altami_setting_separator", SETTING_SEPARATOR_BOX)

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
            "altami_auto_capture_title", AUTO_CAPTURE_TITLE_BOX,
            want=False, timeout=DISMISS_TIMEOUT, shift=DIALOG_SHIFT,
        )
        assert gone and not gone.passed, (
            "Окно «Настройки Автосъемки» не закрылось после ОК: заголовок "
            f"всё ещё совпадает с эталоном (SSIM={gone.score:.6f})"
            if gone else "не удалось снять кадр после клика по ОК"
        )

        logger.info("Сценарий завершён — Altami Studio остаётся открытым")
