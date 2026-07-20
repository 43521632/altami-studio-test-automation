# Как написать тест: от запуска ВМ до сравнения с эталоном

Пошаговая инструкция для Windows и Astra Linux. Предполагается, что окружение
уже настроено по README (второй QMP-сокет, USB-планшет, правило AppArmor,
каталог `/var/lib/libvirt/screenshots`).

---

## 1. Как устроен прогон

Одна ВМ — один процесс pytest. Какую ВМ тестировать, задаёт переменная
окружения `VM_ID`; `run_tests.py` выставляет её сам для каждой ОС.

```bash
VM_ID=windows pytest tests/windows/
VM_ID=astra   pytest tests/Astra/
```

Внутри одной ОС тесты идут **строго последовательно** — гость один, вести его
двумя тестами одновременно нельзя.

ВМ поднимается **один раз на всю сессию** pytest фикстурой `vm_session`
(`tests/conftest.py`), а не на каждый тест. Отсюда важное следствие:

> Тесты не изолированы друг от друга. Состояние экрана, оставленное одним
> тестом, достаётся следующему. Либо возвращайте UI в исходное состояние в
> конце теста, либо пишите тесты так, чтобы порядок не имел значения.

---

## 2. Запуск ВМ

Отдельно запускать ВМ не нужно — фикстура делает это сама:

* домен не запущен → libvirt его стартует (`start_if_stopped=True`);
* ждём появления QMP-сокета;
* ждём стабилизации картинки на экране — это прокси для «ОС загрузилась»
  (`wait_for_boot=True`).

Стабилизация: раз в 3 с снимается кадр и сравнивается с предыдущим; два
подряд кадра с SSIM > 0.999 считаются загрузкой. Предел — `boot_timeout` из
`config/vms_config.yaml` (Windows 180 с, Astra 120 с). По таймауту тесты
**всё равно продолжатся** — в лог уйдёт предупреждение
`экран не стабилизировался за N с`.

Если ВМ недоступна, вся сессия помечается как skipped, а не падает сорока
ошибками.

Ручное управление, когда нужно:

```bash
python run_tests.py --menu     # интерактивное меню: запуск/остановка/статус
virsh -c qemu:///system start win_11_auto-test
```

Дождаться стабилизации экрана вручную внутри теста:

```python
await self.session.wait_until_screen_stable(timeout=60)
```

---

## 3. Логин в гостевую ОС

Автологина в этих ВМ нет — после загрузки обе стоят на экране блокировки.
Логин делается той же инжекцией ввода, что и всё остальное.

> Код в этом разделе и в примерах 7–8 — **шаблон, а не проверенный сценарий**.
> Инжекция ввода, скриншоты и сравнение проверены на живых ВМ; сам вход —
> нет, поскольку паролей у автора не было. Пароли и координаты подставьте
> свои и прогоните первый раз с `--log-cli-level=DEBUG`, глядя на скриншоты.

> **Кириллица не поддерживается.** Раскладка qcode в QMP американская,
> `type_text()` умеет только ASCII. Пароль с кириллицей ввести не получится —
> смените его на латиницу или заводите логин через буфер обмена гостя.

### Windows

Экран блокировки сначала нужно убрать, и только потом появится поле пароля:

```python
async def _login(self):
    await self.press("esc")            # убрать экран блокировки
    await asyncio.sleep(1)
    await self.type_text("ваш-пароль")
    await self.press("ret")            # Enter
    # Рабочий стол прорисовывается не мгновенно
    await self.session.wait_until_screen_stable(timeout=60)
```

Если учётных записей несколько, перед вводом пароля кликните нужную:
`await self.click(x, y)`.

### Astra Linux

Экран блокировки с часами убирается клавишей или кликом, дальше — поле пароля
в fly-dm. Логин часто уже подставлен:

```python
async def _login(self):
    await self.press("esc")
    await asyncio.sleep(1)
    await self.type_text("пароль")
    await self.press("ret")
    await self.session.wait_until_screen_stable(timeout=60)
```

Если поле логина пустое, заполните оба поля через `tab`:

```python
    await self.type_text("user")
    await self.press("tab")
    await self.type_text("пароль")
    await self.press("ret")
```

### Логин один раз на сессию

Логиниться в каждом тесте не нужно — ВМ живёт всю сессию, вход достаточно
выполнить один раз. Самый простой способ — отдельный тест `test_00_login`
первым в классе: pytest выполняет тесты в порядке объявления, а остальные
тесты рассчитывают на уже выполненный вход.

Минус подхода честный: тесты становятся зависимы от порядка, и запуск
одного теста через `-k` без логина работать не будет. Если это мешает —
выносите вход в автофикстуру уровня класса с `loop_scope="session"`
(обязательно тот же loop scope, иначе прогон зависнет — см. раздел 10).

---

## 4. Эмуляция мыши и клавиатуры

Всё доступно прямо на `self` (см. `tests/base_tests.py`), полный набор
примитивов — через `self.qmp`.

### Мышь

```python
await self.click(960, 540)                  # левый клик
await self.click(960, 540, button="right")  # правый
await self.double_click(100, 200)
await self.qmp.mouse_move(500, 300)         # только перемещение
await self.qmp.mouse_drag(x1, y1, x2, y2)   # перетаскивание
```

Координаты — **в пикселях гостя**, отсчёт от левого верхнего угла. Пересчёт в
абсолютный диапазон QMP (0..32767) делается автоматически, разрешение
определяется само.

> Абсолютные координаты работают только с USB-планшетом. Без него клики уходят
> мимо — см. README, «USB-планшет».

Как узнать координаты: снимите скриншот (`await self.capture("probe")`),
откройте PNG в любом редакторе и посмотрите координаты нужного элемента.

### Клавиатура

```python
await self.type_text("hello world")   # набор строки, ASCII
await self.press("ret")               # одна клавиша
await self.press("ctrl", "a")         # комбинация
await self.press("ctrl", "alt", "delete")
```

Имена клавиш — это QKeyCode из `qapi/ui.json`, а не привычные подписи.
Часто нужные:

| Клавиша | qcode | Клавиша | qcode |
|---|---|---|---|
| Enter | `ret` | Пробел | `spc` |
| Esc | `esc` | Tab | `tab` |
| Backspace | `backspace` | Delete | `delete` |
| Стрелки | `up` `down` `left` `right` | Windows / Meta | `meta_l` |
| Ctrl / Alt / Shift | `ctrl` `alt` `shift` | F1–F12 | `f1`…`f12` |

`type_text()` сам подставляет Shift для заглавных букв и символов вроде
`!@#$%`. Точка — `dot`, запятая — `comma`, минус — `minus`.

### Паузы

Гостевая ОС реагирует не мгновенно. Между действием и проверкой нужна пауза:

```python
import asyncio
await self.click(100, 200)
await asyncio.sleep(1)          # дать UI отрисоваться
await self.assert_screen("menu_opened")
```

Для тяжёлых переходов (запуск приложения) надёжнее не фиксированная пауза, а
`await self.session.wait_until_screen_stable(timeout=30)`.

---

## 5. Скриншот и сравнение с эталоном

```python
await self.assert_screen("main_window")   # снять + сравнить + упасть при расхождении
path = await self.capture("debug_shot")   # просто снять, без сравнения
result = await self.screenshot.compare("main_window")   # сравнить без падения
print(result.score, result.passed)
```

### Первый прогон создаёт эталон

Если `baseline/<vm_id>/<имя>.png` отсутствует, текущий скриншот **становится
эталоном и тест проходит**. То есть первый прогон ничего не проверяет.

> Снимайте эталон осознанно, с нужного экрана. Эталон, снятый с экрана
> блокировки с часами, будет падать каждую минуту — на этом проекте так уже
> происходило: SSIM 0.9668 между двумя прогонами с разницей в одну минуту.

Пересоздать эталон — удалить файл и прогнать тест заново:

```bash
rm baseline/windows/main_window.png
VM_ID=windows pytest tests/windows/ -k main_window
```

либо программно:

```python
from src.screenshot_compare import ScreenshotComparator
ScreenshotComparator().save_baseline(path, "main_window", "windows", overwrite=True)
```

### Порог

Задаётся в `config/vms_config.yaml` → `test_settings.screenshot_comparison`:

```yaml
threshold: 0.99          # тест проходит при SSIM > этого значения
save_diff: true
resize_on_mismatch: false
```

`0.99` — строго, ловит мелкие сдвиги; `0.95` — терпимо к сглаживанию шрифтов
и курсору; `0.999` — практически попиксельно.

Разное разрешение скриншота и эталона по умолчанию считается падением: почти
всегда это значит, что ВМ загрузилась в другом видеорежиме.

### Что делать с нестабильными областями

Часы, трей, анимации, сетевые виджеты ломают сравнение всего экрана. Варианты:
понизить порог, либо строить тест вокруг статичной области — открыть нужное
окно и сравнивать экран с ним, а не пустой рабочий стол.

---

## 6. Где смотреть логи, скриншоты и диффы

Каталоги задаются в `config/vms_config.yaml` → `logging`.

```
logs/                                  # в репозитории
├── test_run.log                       # общий лог, ротация 10 МБ × 5
└── pytest.log                         # вывод pytest, уровень DEBUG

screenshots/diff/                      # в репозитории
├── <vm_id>_<тест>_<время>_diff.png    # трёхпанельный дифф
└── <vm_id>_boot_<время>_diff.png      # шум от ожидания загрузки, см. ниже

baseline/<vm_id>/<тест>.png            # эталоны — в git!

reports/                               # в репозитории
├── <vm_id>/junit_attempt1.xml
├── <vm_id>/report_attempt1.html       # HTML-отчёт pytest-html
├── kiwi_export.json
└── kiwi_export.csv

/var/lib/libvirt/screenshots/<vm_id>/  # ВНЕ репозитория
└── <имя>_<время>.png                  # снимки, включая FAILED_* при падении
```

Две оговорки к тому, что написано в README:

* **Отдельных логов на каждый тест нет.** README обещает
  `logs/<vm_id>/<тест>_<время>.log`, и класс `TestLogContext` в
  `src/logging_setup.py` для этого написан — но он не вызывается ниоткуда.
  Фактически есть только `test_run.log` и `pytest.log`.
* **`screenshots/diff/` засоряется кадрами загрузки.** Ожидание стабилизации
  экрана сравнивает соседние кадры и на каждое несовпадение пишет дифф
  `<vm_id>_boot_<время>_diff.png`. Это не результаты тестов — при разборе
  падения ищите файл с именем своего теста.

> Сами снимки лежат **не в проекте**, а в `/var/lib/libvirt/screenshots/`.
> Так сделано намеренно: `screendump` выполняет процесс QEMU от имени
> `libvirt-qemu`, который не может писать в домашний каталог. Диффы и эталоны
> строит уже наш код, поэтому они остаются в репозитории.

### Дифф-изображение

При падении сравнения сохраняется картинка из трёх панелей:

```
[ эталон ] [ текущий ] [ подсветка различий ]
```

Красным подсвечены изменившиеся области. Значение SSIM и пути ко всем трём
файлам попадают и в сообщение об ошибке теста, и в JSON-отчёт:

```
Скриншот не совпал с эталоном: SSIM=0.966825 (нужно > 0.99)
  текущий: /var/lib/libvirt/screenshots/astra/desktop_20260720_173812.png
  эталон:  /home/.../baseline/astra/desktop.png
  различия: /home/.../screenshots/diff/astra_desktop_20260720_173812_diff.png
```

При падении **любого** теста скриншот снимается автоматически (фикстура
`screenshot_on_failure`) и кладётся рядом с префиксом `FAILED_`.

Живой лог прямо в консоли:

```bash
VM_ID=astra pytest tests/Astra/ -v --log-cli-level=DEBUG
```

---

## 7. Полный пример: Windows

`tests/windows/test_windows_notepad.py`

```python
"""UI-тест Блокнота на Windows."""

import asyncio

import pytest

from tests.base_tests import BaseVMTest


@pytest.mark.windows
@pytest.mark.ui
class TestWindowsNotepad(BaseVMTest):
    vm_id = "windows"

    async def test_00_login(self):
        """Вход в систему. Должен идти первым в файле."""
        await self.press("esc")
        await asyncio.sleep(1)
        await self.type_text("ваш-пароль")
        await self.press("ret")
        assert await self.session.wait_until_screen_stable(timeout=60), \
            "Рабочий стол не появился после входа"

    async def test_notepad_opens(self):
        """Блокнот открывается через Win+R и выглядит как эталон."""
        await self.press("meta_l", "r")        # Win+R
        await asyncio.sleep(1)
        await self.type_text("notepad")
        await self.press("ret")
        await asyncio.sleep(2)

        await self.assert_screen("notepad_empty")

    async def test_notepad_accepts_text(self):
        """Набранный текст отображается в окне."""
        await self.type_text("Hello from QMP")
        await asyncio.sleep(0.5)
        await self.assert_screen("notepad_with_text")

        # Вернуть состояние: выделить всё и удалить
        await self.press("ctrl", "a")
        await self.press("delete")
```

Запуск:

```bash
VM_ID=windows pytest tests/windows/test_windows_notepad.py -v
```

---

## 8. Полный пример: Astra Linux

`tests/Astra/test_astra_terminal.py`

```python
"""UI-тест терминала на Astra Linux."""

import asyncio

import pytest

from tests.base_tests import BaseVMTest


@pytest.mark.astra
@pytest.mark.ui
class TestAstraTerminal(BaseVMTest):
    vm_id = "astra"

    async def test_00_login(self):
        """Вход в систему."""
        await self.press("esc")
        await asyncio.sleep(1)
        await self.type_text("пароль-латиницей")
        await self.press("ret")
        assert await self.session.wait_until_screen_stable(timeout=60), \
            "Рабочий стол не появился после входа"

    async def test_terminal_opens(self):
        """Терминал открывается по Ctrl+Alt+T."""
        await self.press("ctrl", "alt", "t")
        await asyncio.sleep(2)
        await self.assert_screen("terminal_opened")

    async def test_terminal_runs_command(self):
        """Команда выполняется и печатает вывод."""
        await self.type_text("echo qmp-test")
        await self.press("ret")
        await asyncio.sleep(1)
        await self.assert_screen("terminal_echo")

        await self.type_text("exit")
        await self.press("ret")
```

Запуск:

```bash
VM_ID=astra pytest tests/Astra/test_astra_terminal.py -v
```

---

## 9. Чек-лист нового теста

1. Файл в `tests/windows/` или `tests/Astra/`, имя вида `test_*.py`.
2. Класс наследует `BaseVMTest`, поле `vm_id` — `"windows"` или `"astra"`.
3. Маркеры: ОС (`@pytest.mark.windows` / `@pytest.mark.astra`) плюс тип
   (`ui`, `system`, `smoke`). Маркеры строгие — незарегистрированный в
   `pytest.ini` маркер уронит прогон.
4. Методы тестов — `async def`, `await` на каждом действии.
5. Между действием и проверкой — пауза или `wait_until_screen_stable`.
6. Первый прогон создаст эталоны: **просмотрите их глазами**, прежде чем
   доверять результатам.
7. Верните UI в исходное состояние в конце теста — следующий тест получит его
   как есть.

## 10. Частые грабли

| Симптом | Причина |
|---|---|
| Клики уходят мимо | Не добавлен USB-планшет |
| `QEMU не создал файл скриншота` | Нет прав у `libvirt-qemu` или блокирует AppArmor |
| `таймаут подключения к QMP` | К сокету уже подключён другой клиент — QMP допускает одного |
| `QMP-сокет не появился` | Нет `<qemu:commandline>` в XML либо ВМ не выключалась полностью после правки |
| Тест висит вечно | Цикл событий: фикстуры и тесты должны быть в одном loop scope (`pytest.ini`) |
| SSIM чуть ниже порога каждый раз | Часы, курсор, анимации, сетевые виджеты в кадре |
| `SSIM <= порога` сразу после создания эталона | Эталон снят со случайного состояния экрана |
| Кириллица не набирается | Не поддерживается: раскладка qcode американская |
