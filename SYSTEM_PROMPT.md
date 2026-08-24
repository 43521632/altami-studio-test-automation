# SYSTEM PROMPT — altami-studio-test-automation

Этот файл — память агента. Когда я (агент) возвращаюсь в проект после
перерыва, я читаю этот файл первым, чтобы НЕ начинать с нуля.

---

## 1. Что это за проект

Фреймворк для UI-тестирования ВМ через libvirt/QMP. Тесты — pytest.
Внутрь гостя ничего не ставится. Управление — через QMP (мышь, клавиатура).
Проверка — SSIM-сравнение скриншотов с эталонами.

ВМ: Windows 11 (`win_11_auto-test`), Astra Linux (`Astra_1_8_auto-test`), macOS.

## 2. Ключевое: QMP принимает НЕ пиксели, а абсолютные координаты планшета

САМАЯ ЧАСТАЯ ОШИБКА (я её уже делал). QEMU ожидает координаты USB-планшета
в диапазоне **0–65535**, а не пиксели гостя (1920×1200).

В проекте есть пересчёт: `src/qmp_client.py` → `pixel_to_abs(value, extent)`.

**Как НЕ надо:**
```python
await qmp.execute("input-send-event", {
    "events": [{"type": "abs", "data": {"axis": "x", "value": 113}}]  # НЕВЕРНО
})
```

**Как надо (через штатные методы):**
```python
from src.qmp_client import QMPSession
qmp = QMPSession("windows", "/var/lib/libvirt/qemu/win_11_auto-test.qmp",
                 resolution=(1920, 1200))
await qmp.connect()
await qmp.mouse_move(113, 120)     # пиксели — пересчёт внутри
await qmp.mouse_click(113, 120)    # пиксели — пересчёт внутри
```

**Почему важно:** если передать пиксели напрямую, клик уходит в левый
верхний угол (x=113 → abs=~25 из 65535). GUI не реагирует.

**QMPSession обязательные параметры:**
```python
QMPSession(
    "windows",                               # vm_id
    "/var/lib/libvirt/qemu/win_11_auto-test.qmp",  # socket_path
    resolution=(1920, 1200)                  # ОБЯЗАТЕЛЬНО! без этого
)                                            # detect_resolution() упадёт
```

Если не передать `resolution`, `QMPSession` вызовет `detect_resolution()`,
который пишет probe-файл в `/var/lib/libvirt/screenshots/` и падает с
`Read-only file system` из-за песочницы. Всегда передавайте `resolution=(1920, 1200)`.

## 3. Скриншоты — через QMP в /var/lib/libvirt/screenshots/

Screendump пишет процесс QEMU (пользователь `libvirt-qemu`). Наш код ТОЛЬКО
читает. Каталог `/var/lib/libvirt/screenshots/` должен быть доступен
`libvirt-qemu` на запись.

**Рабочий путь:**
```python
import os; from pathlib import Path
os.makedirs("/var/lib/libvirt/screenshots/windows", exist_ok=True)
path = Path("/var/lib/libvirt/screenshots/windows/probe.ppm")
await qmp.screendump(path)

# Конвертировать PPM → PNG для просмотра
from PIL import Image
img = Image.open(path).convert("RGB")
img.save("/home/romand/git/altami-studio-test-automation/screenshots/windows_probe/probe.png")
```

**Локальные копии** храню в `screenshots/windows_probe/` — для анализа.

## 4. Glide — единственный способ открыть меню

QMP `mouse_move` — телепорт (одно событие). Qt распознаёт **поток событий
движения** как движение мыши, телепорт — нет. Поэтому fly-меню, подменю,
подсветка пунктов НЕ работают через `mouse_click(x, y)`.

**Правило:**
- По меню, подменю, пунктам — ТОЛЬКО `glide` или `glide_click`
- По обычным кнопкам (OK, Закрыть, Отмена) — можно `click`

Реализация glide:
```python
async def glide(x1, y1, x2, y2):
    steps = 24
    for i in range(1, steps + 1):
        nx = round(x1 + (x2 - x1) * i / steps)
        ny = round(y1 + (y2 - y1) * i / steps)
        await qmp.mouse_move(nx, ny)
        await asyncio.sleep(0.015)
```

## 5. Русский текст — только через OCR (Tesseract)

Кириллицу через QMP ввести НЕЛЬЗЯ — раскладка qcode американская.
Но ЧИТАТЬ русский текст со скриншотов можно через Tesseract OCR.

**Установка:**
```bash
# tesseract уже есть в системе
# Русские данные:
wget https://github.com/tesseract-ocr/tessdata/raw/main/rus.traineddata \
     -O /tmp/rus.traineddata
mkdir -p /home/romand/git/altami-studio-test-automation/tessdata
cp /tmp/rus.traineddata /home/romand/git/altami-studio-test-automation/tessdata/
cp /usr/share/tesseract-ocr/5/tessdata/eng.traineddata \
   /home/romand/git/altami-studio-test-automation/tessdata/
```

**Использование:**
```bash
TESSDATA_PREFIX=/home/romand/git/altami-studio-test-automation/tessdata \
  python3 -c "
import pytesseract
from PIL import Image
text = pytesseract.image_to_string(Image.open('shot.png'),
            lang='rus+eng', config='--psm 4')
print(text)
"
```

Важно: `TESSDATA_PREFIX` должен указывать на каталог с `rus.traineddata`.

**PSM режимы:** `--psm 4` (целый блок), `--psm 6` (единый блок текста),
`--psm 7` (одна строка текста).

## 6. Определение координат меню — сканированием + OCR

Чтобы найти, какой пункт меню где находится:

1. Кликнуть по позиции, сделать скриншот
2. Вырезать область выпадающего меню
3. Скормить Tesseract с русским языком

```python
# Сканирование текстовых строк в dropdown
for y in range(35, 250):
    dark = 0
    for xi in range(from_x, to_x, 2):
        if int(arr[y, xi, 0]) < 150: dark += 1
    if dark > 10:
        # OCR этой строки
        crop = img.crop((from_x, y-2, to_x, y+6))
        text = pytesseract.image_to_string(crop, lang='rus+eng', config='--psm 7')
```

## 7. Структура проекта (важно для навигации)

```
tests/windows/                        # тесты Windows
tests/Astra/                          # тесты Astra Linux
tests/base_tests.py                   # BaseVMTest (click, glide, assert_region...)
tests/conftest.py                     # фикстуры (vm_session, guest_login)
src/qmp_client.py                     # QMPSession (mouse_move, mouse_click, screendump...)
src/case_ids.py                       # соответствие тестов и ID кейсов (TC-XX)
src/screenshot_compare.py             # SSIM-сравнение
src/widget_geometry.py                # геометрическая проверка кнопок
src/vm_manager.py                     # VMManager / VMSession (жизненный цикл)
src/guest_login.py                    # автовход в гостевую ОС
config/vms_config.yaml                # конфиги ВМ
config/settings.py                    # загрузка настроек
baseline/<vm>/                        # эталонные скриншоты (НЕ в git)
docs/creating-ui-test-case.md         # инструкция по созданию тестов
scripts/ui_probe.py                   # ручной драйвер (разведка координат)
```

## 8. Регистрация нового теста

1. Создать файл `tests/<OS>/test_<что>.py`
2. Класс наследует `BaseVMTest` + `vm_id`
3. Маркеры: `@pytest.mark.<os>` + `@pytest.mark.ui` + `@pytest.mark.app` (если нужно)
4. Зарегистрировать в `src/case_ids.py`:
   - Ключ: `tests/windows/test_foo.py::TestClass::test_method`
   - Получить через: `VM_ID=windows pytest tests/windows/test_foo.py --collect-only -q`
5. Порядок прогона: по алфавиту имени файла, `@pytest.mark.app` — в конец

## 9. Эталоны (baseline)

- Лежат в `baseline/<vm>/<test_name>.png`
- Первый прогон создаёт их bootstrap-ом → НАДЁЖНОСТЬ НИЗКАЯ
- **Правильно:** засевать вручную из устоявшегося скриншота
- Размер PNG должен совпадать с box в `assert_region`
- Не в git (`.gitignore`)

```python
from PIL import Image
full = Image.open("/var/lib/libvirt/screenshots/windows/probe.png").convert("RGB")
crop = full.crop((720, 322, 1140, 336))
crop.save("baseline/windows/altami_quick_capture_title.png")
```

## 10. Доступные ВМ и их QMP-сокеты

| ВМ | Имя домена | QMP-сокет | Конфиг vm_name |
|----|-----------|-----------|----------------|
| Windows | `win_11_auto-test` | `/var/lib/libvirt/qemu/win_11_auto-test.qmp` | `Astra_1_8_auto-test` |
| Astra | `Astra_1_8_auto-test` | `/var/lib/libvirt/qemu/Astra_1_8_auto-test.qmp` | `Astra_1_8_auto-test` |

**Проверка статуса:**
```bash
virsh -c qemu:///system list --all
python run_tests.py --check
```

**Прямое подключение к QMP (без libvirt):**
```bash
source venv/bin/activate
python3 -c "
import asyncio
from src.qmp_client import QMPSession
async def t():
    qmp = QMPSession('windows', '/var/lib/libvirt/qemu/win_11_auto-test.qmp',
                     resolution=(1920,1200))
    await qmp.connect()
    print(await qmp.query_status())
    await qmp.disconnect()
asyncio.run(t())
"
```

## 11. Песочница и права

- **`danger-full-access`** требуется для `sudo apt` и записи в `/var/lib/libvirt/`
- Скриншоты пишет QEMU → нужны права на каталог
- `TESSDATA_PREFIX` — локальный каталог `~/git/altami-studio-test-automation/tessdata/`
- Рабочий каталог: `/home/romand/git/altami-studio-test-automation`
- Виртуальное окружение: `venv/`
- Всегда активировать: `source venv/bin/activate`

## 12. Сложности, которые я уже прошёл

1. ❌ **Пиксели vs абсолютные координаты** — передавал пиксели напрямую в QMP
   → клики уходили в угол. Решение: всегда использовать QMPSession с `resolution`.

2. ❌ **detect_resolution() падает** — метод пишет probe-файл в `/var/lib/libvirt/screenshots/`,
   который недоступен из песочницы. Решение: всегда передавать `resolution=(1920, 1200)`.

3. ❌ **Телепорт не открывает меню** — Qt ждёт поток событий движения.
   Решение: glide для меню и подменю.

4. ❌ **Bootstrap-эталон из полупрозрачного кадра** — первый прогон ловит ещё
   не отрисованное окно. Решение: засевать эталон вручную.

5. ❌ **Неправильная позиция «Настройки»** — сначала думал x=402, оказалось x=476.
   Решение: только OCR или визуальная проверка.

6. ❌ **Русские буквы в меню не читаются без OCR** — установлен Tesseract с русским.

7. ❌ **Клики по рабочему столу вместо Altami Studio** — Altami Studio была не
   запущена, хотя лог теста показывал PASS. Решение: проверять скриншот глазами.

## 13. Быстрый старт после перерыва

Когда я возвращаюсь в проект:

```bash
# 1. Проверить, что ВМ работает
virsh -c qemu:///system list --all

# 2. Активировать venv
source /home/romand/git/altami-studio-test-automation/venv/bin/activate

# 3. Проверить, что Tesseract с русским доступен
TESSDATA_PREFIX=/home/romand/git/altami-studio-test-automation/tessdata \
  tesseract --list-langs

# 4. Проверить последний лог (что произошло)
ls -lt logs/ | head -5
tail -50 logs/pytest_windows_last.log 2>/dev/null

# 5. Убедиться, что скриншоты работают
python3 -c "
import asyncio
from src.qmp_client import QMPSession
async def t():
    q = QMPSession('windows', '/var/lib/libvirt/qemu/win_11_auto-test.qmp',
                   resolution=(1920,1200))
    await q.connect()
    from pathlib import Path
    await q.screendump(Path('/var/lib/libvirt/screenshots/windows/check.ppm'))
    await q.disconnect()
    print('OK')
asyncio.run(t())
"
```

---

*Последнее обновление: 24.08.2026. Добавлен опыт создания TC-94.*