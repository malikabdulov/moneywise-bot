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

## Автозапуск через systemd

Ниже приведён пример unit-файла для systemd, который можно разместить в `/etc/systemd/system/moneywise-bot.service`:

```ini
[Unit]
Description=Moneywise Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/moneywise-bot
EnvironmentFile=/opt/moneywise-bot/.env
ExecStart=/opt/moneywise-bot/.venv/bin/python -m app.main
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

После добавления unit-файла выполните:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now moneywise-bot.service
```

Следите за логами сервиса через `journalctl -u moneywise-bot.service -f`.

## Миграции

Приложение автоматически создаёт необходимые таблицы при запуске. Для сложных сценариев используйте Alembic или другую систему миграций.
