"""Reminder related business logic services."""

from __future__ import annotations

from dataclasses import dataclass

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import User
from app.db.repositories import UserRepository


REMINDER_TEXT: str = "💭 Сегодня пока нет трат. Что-нибудь купить успел?"


@dataclass(slots=True)
class ReminderAction(CallbackData, prefix="remind"):
    """Callback data schema for reminder-related inline buttons."""

    action: str


ADD_EXPENSE_ACTION = "add"
TOGGLE_REMINDER_ACTION = "toggle"


def build_reminder_keyboard() -> InlineKeyboardMarkup:
    """Return inline keyboard for the daily reminder message."""

    builder = InlineKeyboardBuilder()
    builder.button(
        text="➕ Добавить расход",
        callback_data=ReminderAction(action=ADD_EXPENSE_ACTION).pack(),
    )
    builder.button(
        text="🔕 Отключить напоминания",
        callback_data=ReminderAction(action=TOGGLE_REMINDER_ACTION).pack(),
    )
    builder.adjust(2)
    return builder.as_markup()


class ReminderService:
    """Business logic for working with daily spending reminders."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def toggle_notifications(self, user_id: int) -> bool:
        """Toggle notification status for the user and return the new state."""

        async with self._session_factory() as session:
            repository = UserRepository(session)
            user = await repository.get_by_id(user_id)
            if user is None:
                raise ValueError("Пользователь не найден")
            updated = await repository.toggle_notifications(user)
        return bool(updated.notifications_enabled)

    async def disable_notifications(self, user_id: int) -> bool:
        """Disable notifications for the user and return the resulting state."""

        async with self._session_factory() as session:
            repository = UserRepository(session)
            user = await repository.get_by_id(user_id)
            if user is None:
                raise ValueError("Пользователь не найден")
            updated = await repository.set_notifications(user, enabled=False)
        return bool(updated.notifications_enabled)

    async def notifications_enabled(self, user_id: int) -> bool:
        """Return ``True`` if the user has reminders enabled."""

        async with self._session_factory() as session:
            repository = UserRepository(session)
            user = await repository.get_by_id(user_id)
            if user is None:
                raise ValueError("Пользователь не найден")
        return bool(user.notifications_enabled)

    async def list_users_with_notifications(self) -> list[User]:
        """Return all users who opted-in for daily reminders."""

        async with self._session_factory() as session:
            repository = UserRepository(session)
            users = await repository.list_with_notifications_enabled()
        return users


__all__ = [
    "ReminderService",
    "ReminderAction",
    "ADD_EXPENSE_ACTION",
    "TOGGLE_REMINDER_ACTION",
    "build_reminder_keyboard",
    "REMINDER_TEXT",
]
