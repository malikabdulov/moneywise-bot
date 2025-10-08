"""Handler for the /start command."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Send greeting and usage instructions to the user."""

    await message.answer(
        "Привет! Я помогу вести учёт расходов.\n"
        "Добавить расход: /add — выберите категорию, дату и сумму с помощью кнопок или отправьте данные вручную (например, /add 199 еда Обед).\n"
        "Категории и управление лимитами: /categories — все действия доступны через кнопки.\n"
        "Статистика за месяц: /stats\n"
        "Сегодняшние траты: /today"
    )
