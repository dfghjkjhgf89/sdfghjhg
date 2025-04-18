# 🤖 Telegram Bot с Админ-панелью

## 📋 Требования
- Python 3.9+
- PostgreSQL
- [ngrok](https://ngrok.com/) (опционально, для тестирования на локальной машине)

## 🚀 Быстрый старт

### 1. Клонирование репозитория
```bash
git clone <repository-url>
cd <repository-name>
```

### 2. Создание виртуального окружения
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/MacOS
source venv/bin/activate
```

### 3. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 4. Настройка окружения
Создайте файл `.env` в корневой директории проекта:
```env
# База данных
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
DB_POOL_SIZE=5

# Админ-панель
ADMIN_USERNAME=admin
ADMIN_PASSWORD=123123
SECRET_KEY=your-secret-key

# Настройки приложения
DEBUG=True
HOST=0.0.0.0
PORT=8000

# Telegram Bot
BOT_TOKEN=your-bot-token

# Tinkoff Bank (если используется)
TBANK_SHOP_ID=your-shop-id
TBANK_SECRET_KEY=your-secret-key
```

### 5. Инициализация базы данных
```bash
python init_db.py
```

### 6. Запуск приложения

#### Запуск бота
```bash
python bot.py
```

#### Запуск админ-панели
```bash
python -m flask --app admin_panel/app run
```

Админ-панель будет доступна по адресу: http://localhost:8000

Логин: `admin`
Пароль: `123123`

## 🔧 Тестовый режим
- Длительность подписки установлена на 10 минут для тестирования
- Стоимость подписки: 1500₽
- Автоплатежи можно включить/отключить через команды `/stop` и `/resume`

## 📱 Основные команды бота
- `/start` - Начало работы с ботом
- `/stop` - Отключить автоплатежи
- `/resume` - Включить автоплатежи

## 👨‍💼 Функции админ-панели
- Управление пользователями
- Просмотр и управление подписками
- Белый список пользователей
- Рассылка сообщений
- Статистика платежей

## ⚠️ Важные замечания
1. Не забудьте изменить тестовые учетные данные в production
2. Рекомендуется использовать SSL для production-окружения
3. Для тестирования платежей используется Tinkoff API
4. Все временные метки хранятся в UTC 