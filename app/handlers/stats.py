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

    summary = await expense_service.get_month_summary(user_id=message.from_user.id)

    if not summary.expenses:
        await message.answer("За текущий месяц ещё нет трат.")
        return

    lines = ["Статистика по категориям за месяц:"]
    for category, total in sorted(summary.category_totals.items(), key=lambda item: item[1], reverse=True):
        lines.append(f"• {category}: {total} ₽")
    lines.append(f"Всего: {summary.total} ₽")

    await message.answer("\n".join(lines))
