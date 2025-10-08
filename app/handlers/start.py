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
        "Добавьте трату: /add 199 еда Обед\n"
        "Меню категорий и все действия: /categories (используйте кнопки)\n"
        "Добавить категорию: /category_add еда 15000\n"
        "Изменить лимит: /category_limit еда 20000\n"
        "Переименовать категорию: /category_rename еда | продукты\n"
        "Удалить категорию: /category_delete еда\n"
        "Статистика за месяц: /stats\n"
        "Сегодняшние траты: /today"
    )
