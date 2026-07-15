# altami-studio-test-automation



# Создаем виртуальное окружение

python3.12 -m venv venv

# Активируем его

source venv/bin/activate

# Устанавливаем зависимости

pip install --upgrade pip

pip install -r requirements.txt

2. Горячие клавиши для continue
Действие	Команда
Autocomplete	Печатайте → Tab для принятия
Edit (редактировать выделенное)	Cmd/Ctrl + I
Chat (спросить AI)	Cmd/Ctrl + L
Agent (AI сам правит код)	Переключить внизу слева: Chat → Agent

Agent (Агент)
Что делает: самая мощная фича — AI сам может читать файлы, редактировать код, выполнять команды терминала и принимать решения

Как попробовать: переключитесь с "Chat" на "Agent" (выпадающий список внизу слева) → введите /init — и AI создаст файл CONTINUE.md с документацией проекта

Часы пиковой нагрузки у дипсик - с 16:00 до 19:00 с 21:00 до 00:00 следующего дня по МСК.



### `README.md`
```markdown
# QMP Test Framework

Фреймворк для автоматического тестирования виртуальных машин через QEMU QMP протокол.

## Структура проекта

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

## Установка

```bash
# Клонирование репозитория
git clone <repository-url>
cd qmp-test-framework

# Установка зависимостей
pip install -r requirements.txt
```

## Конфигурация

1. Настройте параметры в `.env` файле
2. Настройте ВМ в `config/vms_config.yaml`:
   - Укажите пути к QMP сокетам
   - MAC-адреса ВМ
   - Включенные тесты

## Запуск тестов

### Через run_tests.py (простой режим)

```bash
# Запуск всех тестов
python run_tests.py

# Запуск тестов для конкретной ВМ
python run_tests.py --vm windows11
python run_tests.py --vm astra

# Показать доступные ВМ
python run_tests.py --list
```

### Через pytest (режим разработки)

```bash
# Запуск всех тестов
pytest

# Запуск тестов для конкретной ВМ
pytest tests/windows/
pytest tests/astra/

# Запуск с маркерами
pytest -m windows
pytest -m astra
pytest -m "windows and system"

# Запуск с детальным выводом
pytest -v

# Запуск с логированием
pytest --log-cli-level=INFO
```

## Логирование

- Все логи сохраняются в `logs/`
- Результаты тестов сохраняются в JSON формате
- Каждый шаг теста логируется для отслеживания ошибок

## Интеграция с Kiwi TCMS

Результаты тестов сохраняются в JSON формате, который можно использовать для автоматической отправки в Kiwi TCMS.

## Требования

- Python 3.12+
- QEMU с включенным QMP
- Виртуальные машины должны быть запущены

## Поддерживаемые ОС

- Windows 10/11
- Astra Linux
- macOS (частично)
```

## 4. Создадим файл для интеграции с Kiwi TCMS

### `src/kiwi_integration.py`
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

Теперь у вас есть полностью рабочий проект с:

1. **Поддержкой нескольких ВМ** - Windows, Astra Linux, macOS
2. **Детальным логированием** - каждый шаг теста логируется
3. **Возможностью запуска отдельных ВМ** - через параметр `--vm`
4. **Интеграцией с Kiwi TCMS** - через экспорт результатов
5. **Двумя способами запуска**:
   - `run_tests.py` - простой режим
   - `pytest` - режим разработки

Проект готов к использованию! Проверьте, что пути к QMP сокетам в `vms_config.yaml` соответствуют вашей конфигурации QEMU.
