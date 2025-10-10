"""Handlers related to daily spending reminders."""

from __future__ import annotations

from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.handlers.add import start_add_expense_flow
from app.services import (
    ADD_EXPENSE_ACTION,
    CategoryService,
    ReminderAction,
    ReminderService,
    TOGGLE_REMINDER_ACTION,
    UserService,
)

router = Router()

REMINDER_ENABLED_TEXT = "Напоминания включены. Напишу в 22:00, если трат не будет."
REMINDER_DISABLED_TEXT = (
    "Напоминания выключены. Вернуть их можно командой /reminder."
)


@router.message(Command("reminder"))
async def cmd_reminder(
    message: Message,
    reminder_service: ReminderService,
    user_service: UserService,
) -> None:
    """Toggle reminder status for the current user."""

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    await user_service.upsert_from_telegram(message.from_user)
    try:
        enabled = await reminder_service.toggle_notifications(message.from_user.id)
    except ValueError:
        await message.answer("Не удалось изменить настройки напоминаний.")
        return

    await message.answer(REMINDER_ENABLED_TEXT if enabled else REMINDER_DISABLED_TEXT)


@router.callback_query(ReminderAction.filter(F.action == ADD_EXPENSE_ACTION))
async def reminder_add_expense(
    callback: CallbackQuery,
    category_service: CategoryService,
    state: FSMContext,
) -> None:
    """Start the expense creation flow from the reminder button."""

    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return

    await start_add_expense_flow(
        callback.message,
        user_id=callback.from_user.id,
        category_service=category_service,
        state=state,
    )
    await callback.answer()


@router.callback_query(ReminderAction.filter(F.action == TOGGLE_REMINDER_ACTION))
async def reminder_toggle(
    callback: CallbackQuery,
    reminder_service: ReminderService,
    user_service: UserService,
) -> None:
    """Toggle reminder status using the inline button."""

    if callback.from_user is None:
        await callback.answer()
        return

    await user_service.upsert_from_telegram(callback.from_user)
    try:
        enabled = await reminder_service.toggle_notifications(callback.from_user.id)
    except ValueError:
        await callback.answer("Не удалось изменить настройки.", show_alert=True)
        return

    response_text = REMINDER_ENABLED_TEXT if enabled else REMINDER_DISABLED_TEXT

    if callback.message is not None:
        with suppress(TelegramBadRequest):
            await callback.message.edit_reply_markup()
        await callback.message.answer(response_text)
        await callback.answer(
            "Напоминания включены" if enabled else "Напоминания отключены"
        )
    else:
        await callback.answer(response_text, show_alert=True)
