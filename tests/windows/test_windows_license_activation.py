"""UI-тест активации лицензии Altami Studio на Windows (файл Astra.alic).

Стартовое состояние — конечное состояние TC-85: приложение уже запущено в
демо-режиме, окно восстановления пропущено, открыто главное окно.

Состояние тест НЕ готовит. Первым шагом он строго сверяет экран с эталоном
стартового состояния и при расхождении падает, ничего не нажимая. Готовит
состояние человек — снапшотом или руками (в регрессии его оставляет
предыдущий тест цепочки). Так сделано намеренно: тест, который сам доводит
машину до нужного состояния, прячет расхождение вместо того, чтобы о нём
сообщить, и тем более не должен этого делать в режиме разработки, где за
состояние отвечает тот, кто его готовил (см. src/dev_run.py).

Сценарий:

1. Помощь -> Лицензия -> Активировать: открывается «Активация лицензии».
2. Выбираем «Указать существующий лицензионный файл» — открывается диалог
   выбора файла.
3. В дереве слева прокручиваем ВВЕРХ и выбираем «Рабочий стол», в списке
   справа прокручиваем ВНИЗ до Astra.alic, кликаем по файлу и жмём «Открыть».
4. «Далее» -> «Завершить»: активация проходит, в правом нижнем углу всплывает
   уведомление «Активация завершена».
5. Закрываем Altami Studio крестиком и запускаем заново с ярлыка.
6. ГЛАВНАЯ проверка: на баннере-заставке больше НЕТ надписи «Демо-версия»
   (область сверяется с эталоном лицензированного баннера, а он отличается от
   демо-эталона: SSIM между ними 0.957 при пороге 0.99).
7. Окно восстановления состояния -> «Пропустить».
8. Помощь -> Лицензия -> Информация: проверяем, что заполнены электронная
   почта и регистрационный номер лицензии. Закрываем окно крестиком.

Приложение НАМЕРЕННО остаётся открытым в конце — как и в TC-85.

ВАЖНО, состояние ВМ. Активация необратима: после прогона приложение больше не
демо, и TC-85 (его главная проверка — надпись «Демо-версия») упадёт. Снапшот
ВМ откатывается ВРУЧНУЮ перед каждым прогоном — автоматики отката в проекте
нет. По этой же причине тест помечен `app` и идёт в конце.

Демо-напоминание. Пока лицензия не активирована, поверх любого окна примерно
раз в три минуты всплывает «Altami Studio Демо версия ... осталось N минут» с
кнопкой «Закрыть». Оно перекрывает кнопки мастера активации, поэтому перед
кликами первой половины сценария вызывается `_dismiss_demo_reminder`. Полный
демо-лимит — 15 минут до принудительного закрытия приложения, в них тест
укладывается с большим запасом (замер живого прогона — около 4 минут).

Проверка надписей и окон — не OCR, а сравнение статичной области кадра с
эталоном (SSIM), см. base_tests.assert_region. Координаты и области сняты на
живой ВМ 22.07.2026 в видеорежиме 1920x1200.
"""

import asyncio
import logging

import pytest

from tests.base_tests import BaseVMTest

logger = logging.getLogger(__name__)

# --- Координаты кликов (пиксели гостя, режим 1920x1200) ----------------------
ALTAMI_SHORTCUT = (113, 120)    # ярлык «Altami Studio 4.1 x64» на рабочем столе
APP_CLOSE_BTN = (1895, 11)      # крестик главного окна Altami Studio
HELP_MENU = (514, 34)           # пункт «Помощь» в строке меню
LICENSE_ITEM = (538, 133)       # «Лицензия» в меню «Помощь» (раскрывает подменю)
ACTIVATE_ITEM = (772, 134)      # «Активировать...» в подменю «Лицензия»
INFO_ITEM = (772, 158)          # «Информация...» в подменю «Лицензия»
EXISTING_FILE_OPTION = (649, 704)  # «Указать существующий лицензионный файл»
TREE_SCROLL_POINT = (550, 600)  # точка наведения для прокрутки дерева слева
DESKTOP_TREE_ITEM = (565, 457)  # «Рабочий стол» — верхний узел дерева
LIST_SCROLL_POINT = (1000, 650)  # точка наведения для прокрутки списка справа
ASTRA_ALIC_FILE = (975, 786)    # файл Astra.alic в списке (после прокрутки вниз)
FILE_OPEN_BTN = (1251, 879)     # кнопка «Открыть» диалога выбора файла
WIZARD_NEXT_BTN = (1388, 815)   # «Далее >» мастера активации
WIZARD_FINISH_BTN = (1388, 815) # «Завершить» — там же, где «Далее»
DEMO_CLOSE_BTN = (1148, 593)    # «Закрыть» в напоминании демо-режима
RESTORE_SKIP_BTN = (1104, 666)  # «Пропустить» в окне восстановления
INFO_CLOSE_BTN = (1176, 422)    # крестик окна «Информация о лицензии»
MOUSE_PARK = (1750, 250)        # нейтральная точка: увести курсор из кадра

# --- Прокрутка (щелчков колеса) ----------------------------------------------
# С запасом: дерево и список короткие, лишние щелчки упираются в край и не
# сдвигают содержимое дальше — позиция получается детерминированной.
TREE_SCROLL_UP = 10
LIST_SCROLL_DOWN = 10

# --- Области для сравнения с эталоном (left, top, right, bottom) -------------
DEMO_DIALOG_BOX = (705, 490, 1195, 515)          # титул напоминания демо-режима
ACTIVATION_TITLE_BOX = (466, 292, 780, 314)      # титул «Активация лицензии»
ACTIVATION_METHODS_BOX = (484, 328, 1240, 366)   # шапка «Метод активации»
FILE_DIALOG_TITLE_BOX = (476, 322, 780, 346)     # титул «Выберите лицензионный файл»
FILE_NAME_FIELD_BOX = (672, 840, 900, 862)       # поле «Имя файла» со значением Astra.alic
ACTIVATION_DONE_BOX = (484, 328, 900, 378)       # «Процесс успешно завершен»
# Уведомление в правом нижнем углу. Заголовок панели «Информация: (N)» содержит
# счётчик сообщений и в область НЕ входит — только текст «Активация завершена».
ACTIVATION_TOAST_BOX = (1715, 1055, 1870, 1092)
# Баннер-заставка. Та же область, что и DEMO_BANNER_BOX в TC-85, но эталон
# другой: без красной надписи «Демо-версия».
LICENSED_BANNER_BOX = (690, 730, 1260, 895)
# Титул главного окна: после активации это «Altami Studio», без «Демо версия».
LICENSED_TITLE_BOX = (24, 2, 200, 22)
RESTORE_TITLE_BOX = (752, 420, 1135, 442)        # титул окна восстановления
APP_TOOLBAR_BOX = (0, 50, 1130, 85)              # панель инструментов главного окна
LICENSE_INFO_TITLE_BOX = (737, 412, 900, 434)    # титул «Информация о лицензии»
LICENSE_EMAIL_BOX = (971, 462, 1170, 484)        # поле «Электронная почта»
LICENSE_REGNUM_BOX = (971, 492, 1170, 514)       # поле «Регистрационный номер лицензии»

# --- Таймауты опроса (секунды) -----------------------------------------------
# Это ПРЕДЕЛ ожидания, а не фиксированная пауза: обычно окно появляется гораздо
# раньше, и тест сразу идёт дальше. Замеры живого прогона 22.07.2026.
LAUNCH_TIMEOUT = 20.0      # баннер после двойного клика (min ~1.0с c лицензией)
DIALOG_TIMEOUT = 8.0       # окно мастера / диалог выбора файла (min ~1.5с)
FILE_LOAD_TIMEOUT = 10.0   # возврат в мастер после «Открыть» (min ~2с)
ACTIVATION_TIMEOUT = 15.0  # экран «Процесс успешно завершен» после «Далее»
TOAST_TIMEOUT = 10.0       # уведомление об активации после «Завершить»
RESTORE_TIMEOUT = 30.0     # окно восстановления после перезапуска в шаге 8
DISMISS_TIMEOUT = 6.0      # исчезновение окна после «Пропустить» / крестика
CLOSE_TIMEOUT = 15.0       # закрытие приложения по крестику
POLL_INTERVAL = 0.4        # как часто опрашивать экран
# Баннер лицензированной версии живёт всего ~1.0-1.5с (в демо-режиме дольше:
# там показ растягивает диалог «Демо версия»), поэтому его ждут быстрым путём
# (_wait_region(fast=True)). Обычный цикл опроса стоит ~1.4с — не из-за паузы
# между итерациями, а из-за съёмки: кадр 1920x1200 кодируется в PNG и читается
# обратно. То есть на полуторасекундную заставку приходится один шанс, и в
# прогоне 23.07.2026 он сработал впритык: промах в 10:42:01.2, попадание в
# 10:42:02.6, соседних кадров с заставкой нет. Быстрый путь снимает сырой PPM
# (13 мс) и режет из него область — итерация укладывается в ~0.15с вместе с
# паузой ниже, то есть заставку успевает увидеть около десяти кадров подряд.
BANNER_POLL_INTERVAL = 0.1


@pytest.mark.windows
@pytest.mark.ui
# Свой таймаут вместо общего (test_settings.timeout = 60с в vms_config.yaml):
# сценарий длинный по своей природе — активация, закрытие приложения, повторный
# запуск с заставкой и окном восстановления. Замер 23.07.2026: тело теста 88с.
# Прогонщики (run_tests.py, консоль, режим разработчика) передают общий таймаут
# в командной строке, и тест падал бы по нему при полностью исправном сценарии.
# 300с — заведомо выше реального худшего случая, но всё ещё ловит настоящее
# зависание.
@pytest.mark.timeout(300)
# app: приложение остаётся открытым после теста, поэтому прогон идёт последним —
# иначе окно Altami перекрывает рабочий стол тестам, которые сверяют его с
# эталоном (сортировка — в tests/conftest.py).
@pytest.mark.app
class TestWindowsLicenseActivation(BaseVMTest):
    """Активация лицензии из файла и проверка, что демо-режим снят."""

    vm_id = "windows"

    async def _park_mouse(self) -> None:
        """Увести курсор в нейтральную точку, чтобы он не попал в кадр."""
        await self.qmp.mouse_move(*MOUSE_PARK)
        self._ptr = MOUSE_PARK
        await asyncio.sleep(0.2)

    async def _wait_region(self, name, box, want=True, timeout=10.0,
                           interval=POLL_INTERVAL, fast=False):
        """Опрашивать область, пока она (не) совпадёт с эталоном.

        want=True  — ждём появления (SSIM > порога);
        want=False — ждём исчезновения (SSIM <= порога).
        Возвращает последний ComparisonResult (по нему видно, дождались ли).

        fast=True — быстрая съёмка (см. base_tests.capture_region): итерация
        стоит ~0.05с вместо ~1.4с. Курсор при этом паркуется один раз до
        цикла, а не на каждой итерации: внутри цикла мышь никто не двигает,
        а парковка стоит дороже самой съёмки. Так опрашивают окна, которые
        живут секунду-полторы. Промахи быстрого цикла diff не пишут, поэтому
        по таймауту область досматривается ещё раз обычным путём — ради
        diff-картинки последнего состояния экрана.
        """
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        result = None
        if fast:
            await self._park_mouse()
        while loop.time() < deadline:
            if not fast:
                await self._park_mouse()
            result = await self.compare_region(name, box, fast=fast)
            if result.passed == want:
                return result
            await asyncio.sleep(interval)
        if fast:
            result = await self.compare_region(name, box)
        return result

    async def _dismiss_demo_reminder(self) -> bool:
        """Закрыть напоминание демо-режима, если оно всплыло поверх окон.

        Пока лицензия не активирована, окно «Altami Studio Демо версия»
        появляется само примерно раз в три минуты и перехватывает клики,
        предназначенные мастеру активации. Возвращает True, если закрывали.
        """
        await self._park_mouse()
        reminder = await self.compare_region("altami_demo_dialog", DEMO_DIALOG_BOX)
        if not reminder.passed:
            return False
        logger.info("Всплыло напоминание демо-режима — закрываю")
        await self.glide_click(*DEMO_CLOSE_BTN)
        await asyncio.sleep(0.6)
        return True

    async def _open_license_submenu(self) -> None:
        """Помощь -> навести на «Лицензия», чтобы раскрылось подменю.

        Пункт открывается наведением, а не кликом, и glide обязателен: одиночное
        событие абсолютной позиции Qt за наведение не считает и подменю не
        раскрывает (см. base_tests.glide).
        """
        await self.glide_click(*HELP_MENU)
        await asyncio.sleep(0.8)
        await self.glide(*LICENSE_ITEM)
        await asyncio.sleep(0.8)

    async def _require_start_state(self) -> None:
        """Сверить экран со стартовым состоянием теста. Не совпало — падение.

        Стартовое состояние — конечное состояние TC-85: Altami Studio открыт в
        демо-режиме, на экране главное окно с панелью инструментов.

        Тест ничего не нажимает до этой проверки и не пытается состояние
        подготовить: несовпадение — это сообщение, а не повод что-то открыть.
        """
        await self._park_mouse()
        toolbar = await self.compare_region("altami_app_toolbar", APP_TOOLBAR_BOX)
        if toolbar.passed:
            logger.info("Стартовое состояние подтверждено: Altami Studio открыт")
            return

        message = [
            "ВМ не в стартовом состоянии — тест не запускался.",
            "  Нужно: Altami Studio открыт в демо-режиме, на экране главное окно "
            "(конечное состояние TC-85).",
            f"  Сейчас: панель инструментов не совпала с эталоном, "
            f"SSIM={toolbar.score:.6f} (нужно > {toolbar.threshold}).",
            f"    текущий: {toolbar.current_path}",
            f"    эталон:  {toolbar.baseline_path}",
        ]
        if toolbar.diff_path:
            message.append(f"    различия: {toolbar.diff_path}")
        message.append(
            "  Подготовьте состояние вручную (или прогоном TC-85) и запустите снова."
        )
        pytest.fail("\n".join(message))

    async def _choose_license_file(self) -> None:
        """В диалоге выбора файла дойти до Astra.alic на рабочем столе.

        Диалог открывается в «Документы/Altami Documents», а дерево слева
        прокручено к разделу «Сеть» — до «Рабочего стола» надо подняться вверх.
        Список справа длиннее окна, и Astra.alic лежит в самом низу.
        """
        logger.info("Прокручиваю дерево слева вверх и выбираю «Рабочий стол»")
        await self.glide(*TREE_SCROLL_POINT)
        await self.qmp.mouse_wheel(TREE_SCROLL_UP, up=True)
        await asyncio.sleep(0.6)
        await self.glide_click(*DESKTOP_TREE_ITEM)
        await asyncio.sleep(1.2)

        logger.info("Прокручиваю список справа вниз и выбираю Astra.alic")
        await self.glide(*LIST_SCROLL_POINT)
        await self.qmp.mouse_wheel(LIST_SCROLL_DOWN, up=False)
        await asyncio.sleep(0.6)
        await self.glide_click(*ASTRA_ALIC_FILE)
        await asyncio.sleep(0.8)

        # Файл выбран — в поле «Имя файла» появилось Astra.alic. Проверяем до
        # клика по «Открыть»: иначе промах по строке списка обнаружился бы
        # только на следующем шаге, где причина уже не видна.
        await self._park_mouse()
        await self.assert_region("altami_file_name_field", FILE_NAME_FIELD_BOX)
        await self.glide_click(*FILE_OPEN_BTN)

    async def test_license_activation_from_file(self):
        """Полный сценарий: активация файлом -> перезапуск -> данные лицензии."""
        # 0. Стартовое состояние TC-85: главное окно Altami Studio открыто.
        await self._require_start_state()

        # 1. Помощь -> Лицензия -> Активировать.
        logger.info("Открываю Помощь -> Лицензия -> Активировать")
        await self._dismiss_demo_reminder()
        await self._open_license_submenu()
        await self.glide_click(*ACTIVATE_ITEM)
        wizard = await self._wait_region(
            "altami_activation_title", ACTIVATION_TITLE_BOX, want=True,
            timeout=DIALOG_TIMEOUT,
        )
        assert wizard and wizard.passed, "Окно «Активация лицензии» не открылось"
        await self._park_mouse()
        await self.assert_region("altami_activation_methods", ACTIVATION_METHODS_BOX)

        # 2. «Указать существующий лицензионный файл» -> диалог выбора файла.
        logger.info("Выбираю «Указать существующий лицензионный файл»")
        await self._dismiss_demo_reminder()
        await self.glide_click(*EXISTING_FILE_OPTION)
        chooser = await self._wait_region(
            "altami_file_dialog_title", FILE_DIALOG_TITLE_BOX, want=True,
            timeout=DIALOG_TIMEOUT,
        )
        assert chooser and chooser.passed, (
            "Диалог «Выберите лицензионный файл» не открылся"
        )

        # 3. Рабочий стол -> Astra.alic -> «Открыть».
        await self._choose_license_file()
        back = await self._wait_region(
            "altami_activation_title", ACTIVATION_TITLE_BOX, want=True,
            timeout=FILE_LOAD_TIMEOUT,
        )
        assert back and back.passed, (
            "После «Открыть» мастер «Активация лицензии» не вернулся на экран"
        )

        # 4. «Далее» -> экран успеха -> «Завершить».
        logger.info("Жму «Далее» и жду завершения активации")
        await self._dismiss_demo_reminder()
        await self.glide_click(*WIZARD_NEXT_BTN)
        done = await self._wait_region(
            "altami_activation_done", ACTIVATION_DONE_BOX, want=True,
            timeout=ACTIVATION_TIMEOUT,
        )
        assert done and done.passed, (
            "Мастер не дошёл до экрана «Процесс успешно завершен» после «Далее»"
        )
        logger.info("Жму «Завершить»")
        await self.glide_click(*WIZARD_FINISH_BTN)

        # 5. Уведомление об успешной активации в правом нижнем углу.
        logger.info("Проверяю уведомление об успешной активации")
        toast = await self._wait_region(
            "altami_activation_toast", ACTIVATION_TOAST_BOX, want=True,
            timeout=TOAST_TIMEOUT,
        )
        assert toast and toast.passed, (
            "Уведомление «Активация завершена» не появилось в правом нижнем углу: "
            f"SSIM={toast.score:.6f}" if toast
            else "не удалось снять кадр после «Завершить»"
        )

        # 6. Закрыть приложение крестиком.
        logger.info("Закрываю Altami Studio крестиком")
        await self.glide_click(*APP_CLOSE_BTN)
        closed = await self._wait_region(
            "altami_app_toolbar", APP_TOOLBAR_BOX, want=False, timeout=CLOSE_TIMEOUT
        )
        assert closed and not closed.passed, (
            "Altami Studio не закрылся по крестику: панель инструментов всё ещё "
            f"на экране (SSIM={closed.score:.6f})" if closed
            else "не удалось снять кадр после клика по крестику"
        )

        # 7. Запуск заново с ярлыка. ГЛАВНАЯ проверка: на баннере нет «Демо-версия».
        logger.info("Запускаю Altami Studio заново и проверяю баннер без «Демо-версия»")
        await self.glide(*ALTAMI_SHORTCUT)
        await asyncio.sleep(0.4)
        await self.double_click(*ALTAMI_SHORTCUT)
        banner = await self._wait_region(
            "altami_licensed_banner", LICENSED_BANNER_BOX, want=True,
            timeout=LAUNCH_TIMEOUT, interval=BANNER_POLL_INTERVAL, fast=True,
        )
        assert banner and banner.passed, (
            "Баннер-заставка не совпал с эталоном лицензированной версии — "
            "надпись «Демо-версия» осталась или заставку не удалось поймать: "
            f"SSIM={banner.score:.6f}" if banner
            else "не удалось снять кадр заставки после запуска"
        )

        # 8. Окно восстановления состояния -> «Пропустить».
        logger.info("Жду окно восстановления состояния и жму «Пропустить»")
        restore = await self._wait_region(
            "altami_restore_title", RESTORE_TITLE_BOX, want=True,
            timeout=RESTORE_TIMEOUT,
        )
        assert restore and restore.passed, (
            "Окно «Восстановить состояние приложения» не появилось после запуска"
        )
        await self.glide_click(*RESTORE_SKIP_BTN)
        gone = await self._wait_region(
            "altami_restore_title", RESTORE_TITLE_BOX, want=False,
            timeout=DISMISS_TIMEOUT,
        )
        assert gone and not gone.passed, (
            "Окно «Восстановить состояние» не исчезло после «Пропустить»"
        )
        # Титул главного окна — «Altami Studio», без «Демо версия». Заставка
        # живёт полторы секунды, а титул виден всё время, поэтому это вторая,
        # устойчивая ко времени проверка того же факта.
        await self._park_mouse()
        await self.assert_region("altami_licensed_title", LICENSED_TITLE_BOX)

        # 9. Помощь -> Лицензия -> Информация: данные лицензии заполнены.
        logger.info("Открываю Помощь -> Лицензия -> Информация")
        await self._open_license_submenu()
        await self.glide_click(*INFO_ITEM)
        info = await self._wait_region(
            "altami_license_info_title", LICENSE_INFO_TITLE_BOX, want=True,
            timeout=DIALOG_TIMEOUT,
        )
        assert info and info.passed, "Окно «Информация о лицензии» не открылось"

        logger.info("Проверяю электронную почту и регистрационный номер лицензии")
        await self._park_mouse()
        await self.assert_region("altami_license_email", LICENSE_EMAIL_BOX)
        await self.assert_region("altami_license_regnum", LICENSE_REGNUM_BOX)

        # 10. Закрыть окно «Информация о лицензии» крестиком.
        logger.info("Закрываю окно «Информация о лицензии»")
        await self.glide_click(*INFO_CLOSE_BTN)
        info_gone = await self._wait_region(
            "altami_license_info_title", LICENSE_INFO_TITLE_BOX, want=False,
            timeout=DISMISS_TIMEOUT,
        )
        assert info_gone and not info_gone.passed, (
            "Окно «Информация о лицензии» не закрылось по крестику"
        )
        logger.info("Сценарий завершён — Altami Studio остаётся открытым")
