"""UI-тест активации лицензии Altami Studio на Astra Linux (файл Astra.alic).

Стартовое состояние — конечное состояние TC-84: приложение уже запущено в
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
   «Выберите лицензионный файл».
3. В дереве слева выбираем «test» (домашний каталог), в списке справа двойным
   кликом заходим в «Desktop», кликаем по файлу Astra.alic и жмём «Открыть».
4. «Далее» -> «Завершить»: активация проходит, в правом нижнем углу всплывает
   уведомление «Активация завершена».
5. Закрываем Altami Studio крестиком и запускаем заново из меню «Пуск»
   (звезда -> «Научные» -> «Altami Studio»).
6. ГЛАВНАЯ проверка: на баннере-заставке больше НЕТ надписи «Демо-версия»
   (область та же, что у TC-84, но эталон другой: SSIM между демо- и
   лицензионным баннером 0.959 при пороге 0.99).
7. Окно восстановления состояния -> «Пропустить».
8. Помощь -> Лицензия -> Информация: проверяем, что заполнены электронная
   почта и регистрационный номер лицензии. Закрываем окно крестиком.

Приложение НАМЕРЕННО остаётся открытым в конце — как и в TC-84.

ВАЖНО, состояние ВМ. Активация необратима: после прогона приложение больше не
демо, и TC-84 (его главная проверка — надпись «Демо-версия») упадёт. Снапшот
ВМ откатывается ВРУЧНУЮ перед каждым прогоном — автоматики отката в проекте
нет. По этой же причине тест помечен `app` и идёт в конце.

Демо-напоминание. Пока лицензия не активирована, поверх любого окна примерно
раз в три минуты всплывает «Altami Studio Демо версия ... осталось N минут» с
кнопкой «Закрыть». Оно перехватывает клики, предназначенные мастеру активации
(на разведке 23.07.2026 из-за него не выделялся файл в диалоге), поэтому перед
кликами первой половины сценария вызывается `_dismiss_demo_reminder`. Полный
демо-лимит — 15 минут до принудительного закрытия приложения; первая половина
сценария укладывается в них с запасом.

Проверка надписей и окон — не OCR, а сравнение статичной области кадра с
эталоном (SSIM), см. base_tests.assert_region. Координаты и области сняты на
живой ВМ Astra_1_8_auto-test 23.07.2026 в видеорежиме рабочего стола 1920x1200.
"""

import asyncio
import logging

import pytest

from tests.base_tests import BaseVMTest

logger = logging.getLogger(__name__)

# --- Координаты кликов (пиксели гостя, режим рабочего стола 1920x1200) -------
# Меню «Пуск» — те же точки, что в TC-84: приложение запускается оттуда же.
START_STAR = (22, 1174)         # звезда «Пуск» в углу панели задач
NAUCHNYE_TAB = (250, 873)       # категория «Научные» (наводим — раскрывается)
ALTAMI_ITEM = (560, 715)        # ярлык «Altami Studio» в подменю «Научные»
APP_CLOSE_BTN = (1904, 14)      # крестик главного окна Altami Studio
HELP_MENU = (546, 40)           # пункт «Помощь» в строке меню
LICENSE_ITEM = (577, 143)       # «Лицензия» в меню «Помощь» (раскрывает подменю)
ACTIVATE_ITEM = (822, 143)      # «Активировать...» в подменю «Лицензия»
INFO_ITEM = (818, 167)          # «Информация...» в подменю «Лицензия»
EXISTING_FILE_OPTION = (663, 679)  # «Указать существующий лицензионный файл»
TEST_DIR_ITEM = (686, 394)      # «test» в дереве слева — домашний каталог
# «Desktop» в списке справа. ВНИМАНИЕ: строкой ниже (y=537) идёт «Desktops» —
# другой каталог, и промах на 19 пикселей уводит не туда.
DESKTOP_DIR_ITEM = (792, 518)
ASTRA_ALIC_FILE = (794, 423)    # файл Astra.alic в каталоге Desktop
FILE_OPEN_BTN = (1208, 672)     # кнопка «Открыть» диалога выбора файла
WIZARD_NEXT_BTN = (1389, 787)   # «Далее >» мастера активации
WIZARD_FINISH_BTN = (1389, 787) # «Завершить» — там же, где «Далее»
DEMO_CLOSE_BTN = (1151, 570)    # «Закрыть» в напоминании демо-режима
RESTORE_SKIP_BTN = (1102, 634)  # «Пропустить» в окне восстановления
INFO_CLOSE_BTN = (1189, 391)    # крестик окна «Информация о лицензии»
MOUSE_PARK = (1750, 250)        # нейтральная точка: увести курсор из кадра

# --- Области для сравнения с эталоном (left, top, right, bottom) -------------
DEMO_DIALOG_BOX = (730, 466, 910, 490)           # титул напоминания демо-режима
ACTIVATION_TITLE_BOX = (460, 266, 780, 286)      # титул «Активация лицензии»
ACTIVATION_METHODS_BOX = (483, 302, 1240, 336)   # шапка «Метод активации»
FILE_DIALOG_TITLE_BOX = (630, 288, 900, 308)     # титул «Выберите лицензионный файл»
FILE_NAME_FIELD_BOX = (730, 662, 900, 684)       # поле «Имя файла» со значением Astra.alic
# Поле «Лицензионный файл» на странице мастера после «Открыть». Это и есть
# признак возврата в мастер: титул окна «Активация лицензии» одинаков на всех
# его страницах и о смене страницы ничего не говорит.
LICENSE_FILE_FIELD_BOX = (623, 398, 900, 418)
# «Процесс успешно завершен». Ниже на этой же странице — даты активации и
# идентификатор компьютера, они меняются от прогона к прогону и в область
# НЕ входят.
ACTIVATION_DONE_BOX = (483, 302, 900, 352)
# Уведомление в правом нижнем углу. Заголовок панели «Информация: (N)» содержит
# счётчик сообщений и в область НЕ входит — только текст «Активация завершена».
ACTIVATION_TOAST_BOX = (1718, 1056, 1870, 1078)
# Баннер-заставка. Та же область, что и DEMO_BANNER_BOX в TC-84, но эталон
# другой: без красной надписи «Демо-версия».
LICENSED_BANNER_BOX = (668, 712, 1256, 878)
# Титул главного окна: после активации это «Altami Studio», без «Демо версия».
LICENSED_TITLE_BOX = (26, 4, 200, 26)
RESTORE_TITLE_BOX = (744, 386, 1162, 416)        # титул окна восстановления
APP_TOOLBAR_BOX = (0, 54, 1132, 96)              # панель инструментов главного окна
LICENSE_INFO_TITLE_BOX = (696, 382, 870, 402)    # титул «Информация о лицензии»
LICENSE_EMAIL_BOX = (983, 431, 1181, 453)        # поле «Электронная почта»
LICENSE_REGNUM_BOX = (983, 462, 1181, 484)       # поле «Регистрационный номер лицензии»

# --- Таймауты опроса (секунды) -----------------------------------------------
# Это ПРЕДЕЛ ожидания, а не фиксированная пауза: обычно окно появляется гораздо
# раньше, и тест сразу идёт дальше. Замеры разведки 23.07.2026.
LAUNCH_TIMEOUT = 20.0      # баннер после запуска из меню (на разведке ~2.5с)
DIALOG_TIMEOUT = 8.0       # окно мастера / диалог выбора файла
FILE_LOAD_TIMEOUT = 10.0   # возврат в мастер после «Открыть»
ACTIVATION_TIMEOUT = 15.0  # экран «Процесс успешно завершен» после «Далее»
TOAST_TIMEOUT = 10.0       # уведомление об активации после «Завершить»
RESTORE_TIMEOUT = 30.0     # окно восстановления после перезапуска
DISMISS_TIMEOUT = 6.0      # исчезновение окна после «Пропустить» / крестика
CLOSE_TIMEOUT = 15.0       # закрытие приложения по крестику
POLL_INTERVAL = 0.4        # как часто опрашивать экран
# Заставка лицензированной версии живёт около 2с (замер разведки: 13 кадров
# подряд при съёмке каждые 0.15с), поэтому её ждут быстрым путём
# (_wait_region(fast=True)). Обычный цикл опроса стоит ~1с — не из-за паузы
# между итерациями, а из-за съёмки: кадр 1920x1200 кодируется в PNG и читается
# обратно. Быстрый путь снимает сырой PPM (13 мс) и режет из него область.
BANNER_POLL_INTERVAL = 0.1

# --- Допуск на смещение окна (пиксели) ---------------------------------------
# Диалоги Altami центрируются по родителю и встают с точностью до пикселя
# по-разному от запуска к запуску: в прогоне 23.07.2026 окно «Выберите
# лицензионный файл» оказалось смещено на (-1, -1) относительно эталона, и
# полоса титула высотой 20px дала SSIM 0.46 вместо 1.0 — при том, что на экране
# было ровно то же окно. Поэтому области дочерних окон сверяются с допуском:
# эталон ищется по кадру со сдвигом до N пикселей (base_tests.compare_region).
# Проверка от этого не слабеет — сравнивается всё та же область целиком.
# Главное окно развёрнуто на весь экран и не смещается, его областям допуск не
# нужен; заставке хватает 1px — она большая, а опрашивается в быстром цикле.
DIALOG_SHIFT = 2
BANNER_SHIFT = 1

# --- Тайминги меню «Пуск» (секунды) ------------------------------------------
MENU_OPEN_WAIT = 1.5     # меню «Пуск» раскрывается
SUBMENU_WAIT = 2.0       # подменю «Научные» выезжает по наведению


@pytest.mark.astra
@pytest.mark.ui
# app: приложение остаётся открытым после теста, поэтому прогон идёт последним —
# иначе окно Altami перекрывает рабочий стол тестам, которые сверяют его с
# эталоном (сортировка — в tests/conftest.py).
@pytest.mark.app
class TestAstraLicenseActivation(BaseVMTest):
    """Активация лицензии из файла и проверка, что демо-режим снят."""

    vm_id = "astra"

    async def _park_mouse(self) -> None:
        """Увести курсор в нейтральную точку, чтобы он не попал в кадр."""
        await self.qmp.mouse_move(*MOUSE_PARK)
        self._ptr = MOUSE_PARK
        await asyncio.sleep(0.2)

    async def _wait_region(self, name, box, want=True, timeout=10.0,
                           interval=POLL_INTERVAL, fast=False, shift=0):
        """Опрашивать область, пока она (не) совпадёт с эталоном.

        want=True  — ждём появления (SSIM > порога);
        want=False — ждём исчезновения (SSIM <= порога).
        Возвращает последний ComparisonResult (по нему видно, дождались ли).

        fast=True — быстрая съёмка (см. base_tests.capture_region): итерация
        стоит ~0.05с вместо ~1с. Курсор при этом паркуется один раз до цикла,
        а не на каждой итерации: внутри цикла мышь никто не двигает, а парковка
        стоит дороже самой съёмки. Промахи быстрого цикла diff не пишут,
        поэтому по таймауту область досматривается ещё раз обычным путём —
        ради diff-картинки последнего состояния экрана.
        """
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        result = None
        if fast:
            await self._park_mouse()
        while loop.time() < deadline:
            if not fast:
                await self._park_mouse()
            result = await self.compare_region(name, box, fast=fast, shift=shift)
            if result.passed == want:
                return result
            await asyncio.sleep(interval)
        if fast:
            result = await self.compare_region(name, box, shift=shift)
        return result

    async def _dismiss_demo_reminder(self) -> bool:
        """Закрыть напоминание демо-режима, если оно всплыло поверх окон.

        Пока лицензия не активирована, окно «Altami Studio Демо версия»
        появляется само примерно раз в три минуты и перехватывает клики,
        предназначенные мастеру активации. Возвращает True, если закрывали.
        """
        await self._park_mouse()
        reminder = await self.compare_region("altami_demo_dialog", DEMO_DIALOG_BOX,
                                            shift=DIALOG_SHIFT)
        if not reminder.passed:
            return False
        logger.info("Всплыло напоминание демо-режима — закрываю")
        await self.glide_click(*DEMO_CLOSE_BTN)
        await asyncio.sleep(0.6)
        return True

    async def _click_wizard_button(self, point, name, box, timeout, shift=0,
                                   attempts=3) -> bool:
        """Нажать кнопку мастера и убедиться по экрану, что она сработала.

        Клик по кнопке мастера на Astra проходит не всегда. Замер 23.07.2026:
        «Завершить» не сработала ни в прогоне, ни при повторном клике вручную
        две минуты спустя — кнопка при этом была на месте, включена и в фокусе,
        мастер оставался на той же странице, а нажатие Enter её сработало
        мгновенно. Причина со стороны приложения не установлена; известно, что
        поверх мастера может всплыть напоминание демо-режима и перехватить
        клик, но в том случае его на экране не было.

        Поэтому кнопка считается нажатой не по факту клика, а по появлению
        ожидаемой области. Попытки: клик -> клик после паузы и закрытия
        напоминания -> Enter по кнопке, которая уже в фокусе. Возвращает True,
        если результат появился.
        """
        for attempt in range(1, attempts + 1):
            if attempt == attempts:
                logger.warning(
                    "Кнопка %s не сработала кликом (%d попытки) — нажимаю Enter",
                    point, attempts - 1,
                )
                await self.press("ret")
            else:
                await self._dismiss_demo_reminder()
                await self.glide_click(*point)
            result = await self._wait_region(
                name, box, want=True, timeout=timeout, shift=shift
            )
            if result and result.passed:
                if attempt > 1:
                    logger.info("Кнопка %s сработала с попытки %d", point, attempt)
                return True
            logger.warning(
                "После нажатия %s область '%s' не появилась за %.0fс (попытка %d)",
                point, name, timeout, attempt,
            )
        return False

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

        Стартовое состояние — конечное состояние TC-84: Altami Studio открыт в
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
            "(конечное состояние TC-84).",
            f"  Сейчас: панель инструментов не совпала с эталоном, "
            f"SSIM={toolbar.score:.6f} (нужно > {toolbar.threshold}).",
            f"    текущий: {toolbar.current_path}",
            f"    эталон:  {toolbar.baseline_path}",
        ]
        if toolbar.diff_path:
            message.append(f"    различия: {toolbar.diff_path}")
        message.append(
            "  Подготовьте состояние вручную (или прогоном TC-84) и запустите снова."
        )
        pytest.fail("\n".join(message))

    async def _choose_license_file(self) -> None:
        """В диалоге выбора файла дойти до Astra.alic в каталоге Desktop.

        Диалог открывается в «Документы/Altami Documents». Слева в дереве есть
        «test» — домашний каталог пользователя; из него двойным кликом заходим
        в «Desktop», где и лежит Astra.alic.
        """
        logger.info("Перехожу в домашний каталог «test»")
        await self.glide_click(*TEST_DIR_ITEM)
        await asyncio.sleep(1.2)

        logger.info("Захожу в каталог Desktop двойным кликом")
        await self.glide(*DESKTOP_DIR_ITEM)
        await asyncio.sleep(0.4)
        await self.double_click(*DESKTOP_DIR_ITEM)
        await asyncio.sleep(1.5)

        logger.info("Выбираю файл Astra.alic")
        await self._dismiss_demo_reminder()
        await self.glide_click(*ASTRA_ALIC_FILE)
        await asyncio.sleep(0.8)

        # Файл выбран — в поле «Имя файла» появилось Astra.alic. Проверяем до
        # клика по «Открыть»: иначе промах по строке списка обнаружился бы
        # только на следующем шаге, где причина уже не видна.
        await self._park_mouse()
        await self.assert_region("altami_file_name_field", FILE_NAME_FIELD_BOX,
                                 shift=DIALOG_SHIFT)
        await self.glide_click(*FILE_OPEN_BTN)

    async def _launch_from_start_menu(self) -> None:
        """Запустить Altami Studio из меню «Пуск» -> «Научные».

        Подменю fly раскрывается по наведению, а одиночный «телепорт» курсора
        QMP-планшетом Qt как движение не распознаёт — заходим в строку плавным
        перемещением (glide), как в TC-84.
        """
        await self.glide_click(*START_STAR)
        await asyncio.sleep(MENU_OPEN_WAIT)
        await self.glide(*NAUCHNYE_TAB)
        await asyncio.sleep(SUBMENU_WAIT)
        await self.glide(*ALTAMI_ITEM)
        await asyncio.sleep(0.6)
        await self.click(*ALTAMI_ITEM)

    async def test_license_activation_from_file(self):
        """Полный сценарий: активация файлом -> перезапуск -> данные лицензии."""
        # 0. Стартовое состояние TC-84: главное окно Altami Studio открыто.
        await self._require_start_state()

        # 1. Помощь -> Лицензия -> Активировать.
        logger.info("Открываю Помощь -> Лицензия -> Активировать")
        await self._dismiss_demo_reminder()
        await self._open_license_submenu()
        await self.glide_click(*ACTIVATE_ITEM)
        wizard = await self._wait_region(
            "altami_activation_title", ACTIVATION_TITLE_BOX, want=True,
            timeout=DIALOG_TIMEOUT, shift=DIALOG_SHIFT,
        )
        assert wizard and wizard.passed, "Окно «Активация лицензии» не открылось"
        await self._park_mouse()
        await self.assert_region("altami_activation_methods", ACTIVATION_METHODS_BOX,
                                 shift=DIALOG_SHIFT)

        # 2. «Указать существующий лицензионный файл» -> диалог выбора файла.
        logger.info("Выбираю «Указать существующий лицензионный файл»")
        await self._dismiss_demo_reminder()
        await self.glide_click(*EXISTING_FILE_OPTION)
        chooser = await self._wait_region(
            "altami_file_dialog_title", FILE_DIALOG_TITLE_BOX, want=True,
            timeout=DIALOG_TIMEOUT, shift=DIALOG_SHIFT,
        )
        assert chooser and chooser.passed, (
            "Диалог «Выберите лицензионный файл» не открылся"
        )

        # 3. test -> Desktop -> Astra.alic -> «Открыть».
        await self._choose_license_file()
        back = await self._wait_region(
            "altami_license_file_field", LICENSE_FILE_FIELD_BOX, want=True,
            timeout=FILE_LOAD_TIMEOUT, shift=DIALOG_SHIFT,
        )
        assert back and back.passed, (
            "После «Открыть» мастер не показал страницу с путём к лицензионному "
            "файлу"
        )

        # 4. «Далее» -> экран успеха.
        logger.info("Жму «Далее» и жду завершения активации")
        assert await self._click_wizard_button(
            WIZARD_NEXT_BTN, "altami_activation_done", ACTIVATION_DONE_BOX,
            timeout=ACTIVATION_TIMEOUT, shift=DIALOG_SHIFT,
        ), "Мастер не дошёл до экрана «Процесс успешно завершен» после «Далее»"

        # 5. «Завершить» -> уведомление об активации в правом нижнем углу.
        # Пауза перед нажатием: активация только что записала лицензию, и клик
        # в этот момент приложение теряет (см. _click_wizard_button).
        await asyncio.sleep(1.0)
        logger.info("Жму «Завершить» и проверяю уведомление об активации")
        assert await self._click_wizard_button(
            WIZARD_FINISH_BTN, "altami_activation_toast", ACTIVATION_TOAST_BOX,
            timeout=TOAST_TIMEOUT,
        ), "Уведомление «Активация завершена» не появилось в правом нижнем углу"

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

        # 7. Запуск заново из меню «Пуск». ГЛАВНАЯ проверка: нет «Демо-версия».
        logger.info("Запускаю Altami Studio заново и проверяю баннер без «Демо-версия»")
        await self._launch_from_start_menu()
        banner = await self._wait_region(
            "altami_licensed_banner", LICENSED_BANNER_BOX, want=True,
            timeout=LAUNCH_TIMEOUT, interval=BANNER_POLL_INTERVAL, fast=True,
            shift=BANNER_SHIFT,
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
            timeout=RESTORE_TIMEOUT, shift=DIALOG_SHIFT,
        )
        assert restore and restore.passed, (
            "Окно «Восстановить состояние приложения» не появилось после запуска"
        )
        await self.glide_click(*RESTORE_SKIP_BTN)
        gone = await self._wait_region(
            "altami_restore_title", RESTORE_TITLE_BOX, want=False,
            timeout=DISMISS_TIMEOUT, shift=DIALOG_SHIFT,
        )
        assert gone and not gone.passed, (
            "Окно «Восстановить состояние» не исчезло после «Пропустить»"
        )
        # Титул главного окна — «Altami Studio», без «Демо версия». Заставка
        # живёт пару секунд, а титул виден всё время, поэтому это вторая,
        # устойчивая ко времени проверка того же факта.
        await self._park_mouse()
        await self.assert_region("altami_licensed_title", LICENSED_TITLE_BOX)

        # 9. Помощь -> Лицензия -> Информация: данные лицензии заполнены.
        logger.info("Открываю Помощь -> Лицензия -> Информация")
        await self._open_license_submenu()
        await self.glide_click(*INFO_ITEM)
        info = await self._wait_region(
            "altami_license_info_title", LICENSE_INFO_TITLE_BOX, want=True,
            timeout=DIALOG_TIMEOUT, shift=DIALOG_SHIFT,
        )
        assert info and info.passed, "Окно «Информация о лицензии» не открылось"

        logger.info("Проверяю электронную почту и регистрационный номер лицензии")
        await self._park_mouse()
        await self.assert_region("altami_license_email", LICENSE_EMAIL_BOX,
                                 shift=DIALOG_SHIFT)
        await self.assert_region("altami_license_regnum", LICENSE_REGNUM_BOX,
                                 shift=DIALOG_SHIFT)

        # 10. Закрыть окно «Информация о лицензии» крестиком.
        logger.info("Закрываю окно «Информация о лицензии»")
        await self.glide_click(*INFO_CLOSE_BTN)
        info_gone = await self._wait_region(
            "altami_license_info_title", LICENSE_INFO_TITLE_BOX, want=False,
            timeout=DISMISS_TIMEOUT, shift=DIALOG_SHIFT,
        )
        assert info_gone and not info_gone.passed, (
            "Окно «Информация о лицензии» не закрылось по крестику"
        )
        logger.info("Сценарий завершён — Altami Studio остаётся открытым")
