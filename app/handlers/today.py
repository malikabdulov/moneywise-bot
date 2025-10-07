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

    summary = await expense_service.get_today_summary(user_id=message.from_user.id)

    if not summary.expenses:
        await message.answer("Сегодня ещё не было трат.")
        return

    lines = ["Сегодняшние траты:"]
    for expense in summary.expenses:
        time_text = expense.spent_at.strftime("%H:%M")
        description = f" — {expense.description}" if expense.description else ""
        lines.append(f"• {time_text} | {expense.category}: {expense.amount} ₽{description}")
    lines.append(f"Всего за день: {summary.total} ₽")

    await message.answer("\n".join(lines))
