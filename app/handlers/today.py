"""Handler for the /today command."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.services import ExpenseService

router = Router()


@router.message(Command("today"))
async def cmd_today(message: Message, expense_service: ExpenseService) -> None:
    """Send the list of today's expenses."""

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    report = await expense_service.render_today_message(user_id=message.from_user.id)
    await message.answer(report)
