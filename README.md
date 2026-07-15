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
