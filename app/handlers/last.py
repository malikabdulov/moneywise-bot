"""Handler for the /last command."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.services import ExpenseService

router = Router()


@router.message(Command("last"))
async def cmd_last(message: Message, expense_service: ExpenseService) -> None:
    """Send the list of recent expenses with an optional limit."""

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    limit = 10
    text = (message.text or "").strip()
    if text and text != "/last":
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            try:
                limit = int(parts[1])
            except ValueError:
                await message.answer(
                    "Нужно указать количество расходов числом. Пример: /last 25"
                )
                return
            if limit <= 0:
                await message.answer("Количество расходов должно быть положительным.")
                return

    report = await expense_service.render_recent_expenses_message(
        user_id=message.from_user.id, limit=limit
    )
    await message.answer(report)
