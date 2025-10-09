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
        "Привет! \n"
        "/add - Добавить расход: \n"
        "/add <b>199 еда Обед</b> - Можно добавить сразу \n"
        "/categories — Категории и управление лимитами \n"
        "/stats - Статистика за месяц\n"
        "/today - Сегодняшние траты"
    )
