# altami-studio-test-automation

Автоматизация UI-тестирования на виртуальных машинах **virt-manager / libvirt**.
Тесты выполняются в ВМ с Windows, Astra Linux и macOS; проверка результата —
сравнение скриншотов методом **SSIM** с порогом > 0.99.

---

## Архитектура

Две подсистемы с непересекающимися ролями:

| Слой | Инструмент | Отвечает за |
|---|---|---|
| Жизненный цикл ВМ | `libvirt` / virt-manager | запуск, остановка, перезапуск, статус, ресурсы хоста |
| Управление гостевым UI | `qemu.qmp` | клики мышью, ввод текста, скриншоты |
| Проверка результата | `scikit-image` | SSIM-сравнение с эталоном |

**Внутрь гостевой ОС ничего устанавливать не нужно.** Клавиатура и мышь
инжектируются командой QMP `input-send-event`, скриншоты снимаются через
`screendump`. Тесты полностью чёрный ящик.

### Почему два QMP-сокета

libvirt держит QMP-монитор домена **монопольно** — второй клиент к нему
подключиться не может. Поэтому каждой ВМ добавляется **отдельный, свой**
QMP-сокет: libvirt работает со своим монитором, тесты — со своим.
Настройка описана ниже.

### Структура проекта

```
.
├── config/
│   ├── settings.py            # Загрузка конфига и переменных окружения
│   └── vms_config.yaml        # Конфигурация ВМ, тестов, логов, Kiwi
├── src/
│   ├── libvirt_manager.py     # Жизненный цикл ВМ через libvirt
│   ├── qmp_client.py          # Управление гостевым UI через QMP
│   ├── vm_manager.py          # Связка: ВМ запущена + QMP-сессия открыта
│   ├── vm_menu.py             # Интерактивное меню (rich)
│   ├── screenshot_compare.py  # SSIM-сравнение с эталонами
│   ├── test_runner.py         # Оркестрация pytest по ОС
│   ├── kiwi_reporter.py       # Отчёты + заглушка Kiwi TCMS
│   └── logging_setup.py       # Логирование с ротацией
├── tests/
│   ├── conftest.py            # Фикстуры pytest
│   ├── base_tests.py          # Базовый класс тестов
│   ├── windows/ Astra/ macos/ # Тесты по ОС
├── scripts/
│   ├── check_vms.py           # Полная проверка готовности ВМ
│   └── check_vm_status.sh     # Быстрая проверка через virsh
├── baseline/                  # Эталонные скриншоты (локальные, не в git)
├── logs/ screenshots/ reports/ # Артефакты прогонов (не в git)
├── .env                       # Пароли к гостевым ОС (не в git)
├── .env.example               # Шаблон .env
├── run_tests.py               # Точка входа
└── requirements.txt
```

---

## Установка

### 1. Хост-система (Ubuntu)

```bash
# virt-manager, libvirt и заголовки для сборки libvirt-python
sudo apt update
sudo apt install -y virt-manager libvirt-daemon-system libvirt-dev \
                    pkg-config python3-dev

# Доступ к libvirt без sudo
sudo usermod -aG libvirt "$USER"
newgrp libvirt      # или перелогиньтесь

# Проверка
systemctl status libvirtd
virsh -c qemu:///system list --all - показывает список виртуальных машин в системе.
```

Если `virsh list` требует sudo — вы не в группе `libvirt`. Перелогиньтесь.

### 2. Python-окружение

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Если `libvirt-python` не собирается, используйте системный пакет:

```bash
sudo apt install -y python3-libvirt
python3 -m venv --system-site-packages venv
```

### 3. Создание ВМ

ВМ создаются **вручную в virt-manager** — проект их не создаёт и не удаляет,
только управляет уже существующими. Для каждой ОС:

1. virt-manager → Create a new virtual machine → установите ОС
2. Запомните **имя домена** — оно пойдёт в `vms_config.yaml`
3. Выполните две обязательные настройки ниже

---

## Обязательная настройка каждой ВМ

Без этих двух шагов тесты не заработают.

### Второй QMP-сокет

Нужен для управления UI. `virsh edit <имя-домена>`, затем:

1. В корневой тег `<domain>` добавьте пространство имён `qemu`
2. Перед закрывающим `</domain>` добавьте блок `<qemu:commandline>`

```xml
<domain type='kvm' xmlns:qemu='http://libvirt.org/schemas/domain/qemu/1.0'>
  ...
  <qemu:commandline>
    <qemu:arg value='-qmp'/>
    <qemu:arg value='unix:/var/lib/libvirt/qemu/windows-10-test.qmp,server=on,wait=off'/>
  </qemu:commandline>
</domain>
```

Путь должен совпадать с `qmp_socket` в `vms_config.yaml`.
После правки ВМ нужно **полностью выключить и включить** — перезагрузки гостя
недостаточно, аргументы командной строки применяются при старте QEMU.

Домен получит пометку «tainted: custom-argv» — это лишь запись в логе libvirt,
не ошибка.

### USB-планшет (абсолютные координаты мыши)

Без него гость получает только относительное движение мыши, и клики уходят мимо.

virt-manager → выберите ВМ → Add Hardware → Input → **EvTouch USB Graphics Tablet**

Проверить: `virsh dumpxml <домен> | grep tablet`

### Права на каталог скриншотов

`screendump` записывает файл **процессом QEMU** (пользователь `libvirt-qemu`),
а не нашим кодом. Каталог должен быть доступен ему на запись:

```bash
sudo mkdir -p /var/lib/libvirt/screenshots
sudo chown libvirt-qemu:kvm /var/lib/libvirt/screenshots
```

Если мешает AppArmor — см. раздел «Устранение неполадок».

---

## Конфигурация

Всё в `config/vms_config.yaml`. Ключевое — привязка к virt-manager:

```yaml
vms:
  windows:
    vm_name: "windows-10-test"    # ТОЧНОЕ имя домена из virsh list --all
    qmp_socket: "/var/lib/libvirt/qemu/windows-10-test.qmp"
    enabled: true
    test_path: "./tests/windows"
    boot_timeout: 180
    ui_settings:
      resolution: "1920x1080"
```

Проверить соответствие имён:

```bash
virsh -c qemu:///system list --all     # что есть в libvirt
python run_tests.py --list             # что ждёт конфиг
```

Порог SSIM, таймауты и параллельность — в секции `test_settings`.
Любую настройку можно переопределить переменной окружения
(`LIBVIRT_URI`, `TEST_TIMEOUT`, `PARALLEL_WORKERS`, `LOG_LEVEL`, `KIWI_API_KEY`).

---

## Проверка перед запуском

```bash
# Полная проверка: libvirt, домены, QMP-сокеты, IP, ресурсы хоста
python scripts/check_vms.py
python scripts/check_vms.py --vm windows

# Быстрая проверка через virsh (без Python)
./scripts/check_vm_status.sh
./scripts/check_vm_status.sh windows-10-test
```

`check_vm_status.sh` отдельно сообщает, настроены ли второй QMP-сокет и планшет.

---

## Интерактивное меню

```bash
python run_tests.py --menu
# или
python -m src.vm_menu
```

Возможности:

| Пункт | Действие |
|---|---|
| 1 | Список всех ВМ libvirt с состояниями и привязкой к конфигу |
| 2 | Подробный статус: память, vCPU, IP, автозапуск |
| 3 | Запуск ВМ (с ожиданием состояния «работает») |
| 4 | Остановка: ACPI-shutdown с откатом в принудительное завершение |
| 5 | Перезапуск |
| 6 | Скриншот консоли |
| 7 | Ресурсы хост-системы |

Выбор ВМ — по номерам: `1`, `1,3` или `all`. Меню предупреждает о ВМ,
которые есть в конфиге, но отсутствуют в libvirt.

---

## Запуск тестов

```bash
# Проверка готовности ВМ без запуска тестов
python run_tests.py --check

# Тесты для одной ОС
python run_tests.py --os windows

# Несколько ОС
python run_tests.py --os windows,astra

# Все ОС параллельно (до 3 ВМ одновременно)
python run_tests.py --os all --parallel 3

# Остановка при первом падении
python run_tests.py --os all --stop-on-fail

# Продолжить прерванный прогон
python run_tests.py --restart

# С интеграцией Kiwi TCMS (сейчас заглушка)
python run_tests.py --os windows --kiwi

# Локальный режим — только логи и отчёты
python run_tests.py --os all --local

# Другой домен, чем в конфиге
python run_tests.py --os windows --vm-name "custom-windows-vm"

# Без перезапуска упавших тестов
python run_tests.py --os all --no-retry
```

### Через pytest напрямую

`VM_ID` указывает, к какой ВМ подключаться:

```bash
VM_ID=windows pytest tests/windows/
VM_ID=windows pytest -m "windows and ui"
VM_ID=astra   pytest tests/Astra/ -v --log-cli-level=DEBUG
```

### Модель параллельности

Внутри одной ОС тесты идут **строго последовательно** — гость один, его
нельзя вести двумя тестами сразу. Параллелятся **разные ОС**: на каждую
запускается свой процесс pytest, до `--parallel` штук одновременно.

Коды возврата: `0` — всё прошло, `1` — есть падения, `2` — ошибка конфигурации
или libvirt, `130` — прервано.

---

## Написание тестов

```python
import pytest
from tests.base_tests import BaseVMTest

@pytest.mark.windows
@pytest.mark.ui
class TestLogin(BaseVMTest):
    vm_id = "windows"

    async def test_login_screen(self):
        await self.click(960, 540)            # клик по координатам гостя
        await self.type_text("username")      # ввод текста (ASCII)
        await self.press("ctrl", "a")         # комбинация клавиш
        await self.assert_screen("login")     # сравнение с эталоном по SSIM
```

Доступные методы `BaseVMTest`: `click`, `double_click`, `type_text`, `press`,
`capture`, `assert_screen`, `qmp_execute`, `get_vm_status`.
Полный набор QMP-примитивов — через `self.qmp` (`mouse_drag`, `mouse_move`,
`mouse_button`, `screendump`, `detect_resolution`).

**Ввод не-ASCII текста (кириллица) не поддерживается** — раскладка qcode в QMP
американская. Используйте буфер обмена или переключение раскладки в гостевой ОС.

---

## Сравнение скриншотов

### Создание эталонов

Эталон создаётся **автоматически при первом прогоне** теста: если файла
`baseline/<vm_id>/<test_name>.png` нет, текущий скриншот становится эталоном
и тест проходит.

> **Первый прогон ничего не проверяет.** Обязательно просмотрите созданные
> эталоны глазами, прежде чем доверять результатам.

Пересоздать эталон — удалите файл и прогоните тест заново, либо:

```python
from src.screenshot_compare import ScreenshotComparator
ScreenshotComparator().save_baseline(path, "test_login", "windows", overwrite=True)
```

### Порог

```yaml
test_settings:
  screenshot_comparison:
    threshold: 0.99          # тест проходит при SSIM > этого значения
    save_diff: true
    resize_on_mismatch: false  # true — масштабировать при разных размерах
```

Ориентиры: `0.99` — строго, ловит мелкие сдвиги элементов; `0.95` — терпимо
к сглаживанию шрифтов и курсору; `0.999` — практически попиксельно.

Разное разрешение скриншота и эталона по умолчанию считается падением —
это почти всегда означает, что ВМ загрузилась в другом видеорежиме.

### Анализ различий

При падении в `screenshots/diff/` сохраняется изображение из трёх панелей:

```
[ эталон ] [ текущий ] [ подсветка различий ]
```

Красным подсвечены изменившиеся области. Значение SSIM и пути ко всем трём
файлам попадают в сообщение об ошибке теста и в JSON-отчёт.

---

## Логи и отчёты

```
logs/
├── test_run.log              # Общий лог с ротацией (10 МБ × 5)
├── pytest.log                # Вывод pytest
└── <vm_id>/<тест>_<время>.log  # Отдельный лог на каждый тест
screenshots/
├── <vm_id>/<имя>_<время>.png   # Снимки, включая FAILED_* при падении
└── diff/                       # Трёхпанельные diff-изображения
reports/
├── <vm_id>/junit_attempt1.xml  # Машиночитаемые результаты
├── <vm_id>/report_attempt1.html # HTML-отчёт (pytest-html)
├── kiwi_export.json            # Полные результаты + сводка
└── kiwi_export.csv             # Плоская таблица для импорта
```

При падении теста скриншот снимается автоматически (фикстура
`screenshot_on_failure`).

---

## Аварийная остановка и восстановление

`Ctrl+C` (или `SIGTERM`) — корректная остановка: процессы pytest завершаются,
результаты сохраняются, состояние прогона пишется в `.test_state.json`.
Повторный `Ctrl+C` завершает процесс немедленно.

```bash
python run_tests.py --restart   # продолжить с недоделанных ВМ
```

Упавшие тесты автоматически перезапускаются до `retry_count` раз
(через pytest `--last-failed`). Отключается флагом `--no-retry`.

---

## План интеграции с Kiwi TCMS

Сейчас `KiwiReporter` — **заглушка**. Все результаты сохраняются локально в
`reports/kiwi_export.json` и `.csv` в формате, совместимом с моделью
`TestExecution` в Kiwi.

Когда появится доступ, нужно реализовать один метод —
`KiwiReporter._send_to_kiwi()`. Остальной код менять не придётся.

Порядок работ (Kiwi использует **JSON-RPC**, а не REST):

1. `pip install tcms-api`
2. Заполнить секцию `kiwi` в `vms_config.yaml`, ключ — через `KIWI_API_KEY`
3. Один раз за прогон создать `TestRun`
4. На каждый результат обновить `TestExecution` нужным статусом
5. Прикрепить логи и скриншоты через `add_comment` / `add_attachment`

Подробный псевдокод — в docstring метода `_send_to_kiwi` в
`src/kiwi_reporter.py`. Включение: `--kiwi`; `--local` перекрывает его.

---

## Устранение неполадок

**`Модуль libvirt недоступен`**
`sudo apt install python3-libvirt` либо `pip install libvirt-python`
(нужен `libvirt-dev`). При venv с системным пакетом — флаг
`--system-site-packages`.

**`Не удалось подключиться к libvirt по qemu:///system`**
`systemctl status libvirtd`; проверьте группу: `groups | grep libvirt`.
После `usermod -aG` необходим перелогин.

**`ВМ '<имя>' не найдена в libvirt`**
`vm_name` в конфиге не совпадает с `virsh list --all`. Сверьте
`python run_tests.py --list` со списком доменов.

**`QMP-сокет ... не появился`**
Не добавлен `<qemu:commandline>` в XML домена, либо ВМ не была полностью
выключена после правки. Проверка: `./scripts/check_vm_status.sh <домен>`.

**`таймаут подключения к QMP`**
К сокету уже подключён другой клиент — например, незавершённый прошлый прогон.
QMP допускает одного клиента на сокет.

**`QEMU не создал файл скриншота`**
Нет прав у пользователя `libvirt-qemu` на каталог, либо блокирует AppArmor.
Проверьте `sudo dmesg | grep -i apparmor`; при необходимости добавьте путь
в `/etc/apparmor.d/local/abstractions/libvirt-qemu` и выполните
`sudo systemctl reload apparmor`.

**Клики мышью уходят мимо**
Не добавлен USB-планшет — без него абсолютные координаты не работают.

**Скриншоты не совпадают при каждом прогоне**
Обычные причины: мигающий курсор, часы в трее, анимации. Либо понизьте порог,
либо стройте тесты вокруг статичных областей экрана.

**`SSIM ... <= порога` сразу после создания эталона**
Первый прогон создал эталон из случайного состояния экрана. Удалите
`baseline/<vm_id>/<тест>.png` и пересоздайте на нужном экране.

**ВМ не успевает загрузиться**
Увеличьте `boot_timeout` для этой ВМ. Готовность определяется не только
состоянием libvirt, но и стабилизацией картинки на экране
(`wait_until_screen_stable`).

---
---

# Архив: заметки и документация предыдущей версии проекта

*Раздел сохранён целиком из прежнего README. Часть сведений относится к
предыдущей архитектуре на прямом QMP-подключении (без libvirt) и оставлена
как справочная.*

## Создание виртуального окружения (исходная инструкция)

```bash
# Создаем виртуальное окружение
python3.12 -m venv venv

# Активируем его
source venv/bin/activate

# Устанавливаем зависимости
pip install --upgrade pip
pip install -r requirements.txt
```

## Горячие клавиши для continue

| Действие | Команда |
|---|---|
| Autocomplete | Печатайте → Tab для принятия |
| Edit (редактировать выделенное) | Cmd/Ctrl + I |
| Chat (спросить AI) | Cmd/Ctrl + L |
| Agent (AI сам правит код) | Переключить внизу слева: Chat → Agent |

**Agent (Агент)**

Что делает: самая мощная фича — AI сам может читать файлы, редактировать код,
выполнять команды терминала и принимать решения.

Как попробовать: переключитесь с "Chat" на "Agent" (выпадающий список внизу
слева) → введите /init — и AI создаст файл CONTINUE.md с документацией проекта.

Часы пиковой нагрузки у дипсик — с 16:00 до 19:00 и с 21:00 до 00:00
следующего дня по МСК.

## Прежний README: QMP Test Framework

Фреймворк для автоматического тестирования виртуальных машин через QEMU QMP протокол.

### Структура проекта

```
qmp-test-framework/
├── config/                 # Конфигурации
│   ├── settings.py        # Настройки проекта
│   └── vms_config.yaml    # Конфигурация ВМ
├── src/                   # Исходный код
│   ├── qmp_client.py     # QMP клиент
│   ├── vm_manager.py     # Управление ВМ
│   └── test_runner.py    # Запуск тестов
├── tests/                 # Тесты
│   ├── base_test.py      # Базовый класс
│   ├── windows/          # Тесты для Windows
│   ├── astra/            # Тесты для Astra Linux
│   └── macos/            # Тесты для macOS
├── scripts/               # Вспомогательные скрипты
├── logs/                  # Логи и результаты
├── .env                   # Переменные окружения
├── requirements.txt      # Зависимости
└── run_tests.py          # Точка входа
```

### Установка

```bash
git clone <repository-url>
cd qmp-test-framework
pip install -r requirements.txt
```

### Конфигурация

1. Настройте параметры в `.env` файле
2. Настройте ВМ в `config/vms_config.yaml`:
   - Укажите пути к QMP сокетам
   - MAC-адреса ВМ
   - Включенные тесты

### Запуск тестов

Через run_tests.py (простой режим):

```bash
python run_tests.py                  # Запуск всех тестов
python run_tests.py --vm windows11   # Тесты для конкретной ВМ
python run_tests.py --vm astra
python run_tests.py --list           # Показать доступные ВМ
```

Через pytest (режим разработки):

```bash
pytest                          # Все тесты
pytest tests/windows/           # Для конкретной ВМ
pytest tests/astra/
pytest -m windows               # По маркерам
pytest -m astra
pytest -m "windows and system"
pytest -v                       # Детальный вывод
pytest --log-cli-level=INFO     # С логированием
```

### Логирование

- Все логи сохраняются в `logs/`
- Результаты тестов сохраняются в JSON формате
- Каждый шаг теста логируется для отслеживания ошибок

### Интеграция с Kiwi TCMS

Результаты тестов сохраняются в JSON формате, который можно использовать для
автоматической отправки в Kiwi TCMS.

### Требования

- Python 3.12+
- QEMU с включенным QMP
- Виртуальные машины должны быть запущены

### Поддерживаемые ОС

- Windows 10/11
- Astra Linux
- macOS (частично)

## Прежний вариант интеграции с Kiwi TCMS

Файл `src/kiwi_integration.py` из предыдущей версии. Текущая реализация —
`src/kiwi_reporter.py`; код ниже сохранён как справочный.

```python
"""Интеграция с Kiwi TCMS"""

import logging
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from config.settings import LOGS_DIR

logger = logging.getLogger(__name__)

class KiwiTCMSIntegration:
    """Интеграция с Kiwi TCMS"""

    def __init__(self, api_url: Optional[str] = None, api_key: Optional[str] = None):
        self.api_url = api_url
        self.api_key = api_key

    def load_test_results(self, file_path: str) -> Dict:
        """Загрузка результатов тестов из JSON файла"""
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки результатов: {e}")
            return {}

    def convert_to_kiwi_format(self, results: Dict) -> Dict:
        """Конвертация результатов в формат Kiwi TCMS"""
        kiwi_data = {
            'test_run': {
                'name': f"Test Run {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                'product': 'QEMU Virtual Machines',
                'start_date': datetime.now().isoformat()
            },
            'test_cases': []
        }

        for vm_id, vm_results in results.get('results', {}).items():
            for result in vm_results:
                test_case = {
                    'title': f"{vm_id}: {result['test_name']}",
                    'status': result['status'].upper(),
                    'notes': result.get('error', '') or result.get('output', ''),
                    'execution_time': datetime.now().isoformat()
                }
                kiwi_data['test_cases'].append(test_case)

        return kiwi_data

    def export_for_kiwi(self, results_file: str, output_file: str = "kiwi_export.json") -> None:
        """Экспорт результатов для Kiwi TCMS"""
        results = self.load_test_results(results_file)
        kiwi_data = self.convert_to_kiwi_format(results)

        output_path = LOGS_DIR / output_file
        with open(output_path, 'w') as f:
            json.dump(kiwi_data, f, indent=2)

        logger.info(f"✅ Данные для Kiwi TCMS сохранены в {output_path}")
        return output_path
```

Итог прежней версии проекта:

1. **Поддержка нескольких ВМ** — Windows, Astra Linux, macOS
2. **Детальное логирование** — каждый шаг теста логируется
3. **Запуск отдельных ВМ** — через параметр `--vm`
4. **Интеграция с Kiwi TCMS** — через экспорт результатов
5. **Два способа запуска**: `run_tests.py` (простой режим) и `pytest`
   (режим разработки)
