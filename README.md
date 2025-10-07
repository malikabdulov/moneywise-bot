# Moneywise Bot

Современный Telegram-бот для учёта личных расходов на базе [aiogram 3](https://docs.aiogram.dev/en/latest/index.html).

## Возможности

- Добавление расходов с указанием суммы, категории и описания.
- Просмотр расходов за текущий день.
- Получение статистики за месяц с разбивкой по категориям.

## Стек

- Python 3.11+
- aiogram 3.x
- SQLAlchemy (async)
- SQLite (по умолчанию) или другая СУБД, поддерживаемая SQLAlchemy
- Docker (опционально)

## Структура проекта

```
app/
  config.py        # загрузка настроек из окружения
  main.py          # точка входа и запуск бота
  db/              # модели и работа с БД
  handlers/        # Telegram-хендлеры
  services/        # бизнес-логика
```

## Подготовка окружения

1. Создайте виртуальное окружение и установите зависимости:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Создайте файл `.env` по примеру ниже и укажите токен бота:

```env
BOT_TOKEN=ваш_токен_бота
# DATABASE_URL=sqlite+aiosqlite:///./moneywise.db
# LOG_LEVEL=INFO
```

## Запуск локально

```bash
python -m app.main
```

## Запуск в Docker

1. Соберите образ:

```bash
docker build -t moneywise-bot .
```

2. Запустите контейнер, передав токен бота через переменные окружения:

```bash
docker run --rm -e BOT_TOKEN=ваш_токен_бота moneywise-bot
```

При необходимости можно переопределить `DATABASE_URL` и `LOG_LEVEL` аналогичным образом.

## Миграции

Приложение автоматически создаёт необходимые таблицы при запуске. Для сложных сценариев используйте Alembic или другую систему миграций.
