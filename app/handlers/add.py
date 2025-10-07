"""Handler for adding new expenses."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.services import ExpenseService

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("add"))
async def cmd_add(message: Message, expense_service: ExpenseService) -> None:
    """Handle the /add command and store a new expense."""

    if message.from_user is None:
        await message.answer('Не удалось определить пользователя.')
        return

    try:
        confirmation = await expense_service.add_expense_from_message(
            user_id=message.from_user.id,
            message_text=message.text or "",
        )
    except ValueError as error:
        logger.warning("Failed to add expense: %s", error)
        await message.answer(str(error))
        return

    await message.answer(confirmation)
