"""Handler for the /stats command."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.services import ExpenseService

router = Router()


@router.message(Command("stats"))
async def cmd_stats(message: Message, expense_service: ExpenseService) -> None:
    """Send monthly statistics grouped by category."""

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    report = await expense_service.render_month_message(user_id=message.from_user.id)
    await message.answer(report)
