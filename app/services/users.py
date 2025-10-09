"""User related business logic services."""

from __future__ import annotations

from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repositories import UserRepository


class UserService:
    """Business logic for tracking Telegram user information."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def upsert_from_telegram(self, telegram_user: TelegramUser) -> None:
        """Create or update a user record based on Telegram profile data."""

        async with self._session_factory() as session:
            repository = UserRepository(session)
            existing = await repository.get_by_telegram_id(telegram_user.id)
            payload = {
                "telegram_id": telegram_user.id,
                "username": telegram_user.username,
                "first_name": telegram_user.first_name,
                "last_name": telegram_user.last_name,
                "language_code": telegram_user.language_code,
                "is_bot": telegram_user.is_bot,
            }
            if existing is None:
                await repository.create_user(
                    user_id=telegram_user.id,
                    **payload,
                )
            else:
                await repository.update_user(existing, **payload)


__all__ = ["UserService"]
