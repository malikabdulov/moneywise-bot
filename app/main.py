"""Application entry point for the Moneywise Telegram bot."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from app.config import ConfigurationError, get_settings
from app.db import Base, create_session_factory, get_engine
from app.handlers import setup_routers
from app.services import (
    CategoryService,
    ExpenseService,
    ReminderService,
    UserService,
    REMINDER_TEXT,
    build_reminder_keyboard,
)

logger = logging.getLogger(__name__)


async def on_startup() -> tuple[Dispatcher, Bot, AsyncIOScheduler]:
    """Configure application components and return dispatcher, bot and scheduler."""

    settings = get_settings()

    logging.basicConfig(
        level=settings.logging.level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    engine = get_engine(settings)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    expense_service = ExpenseService(session_factory)
    category_service = CategoryService(session_factory)
    user_service = UserService(session_factory)
    reminder_service = ReminderService(session_factory)

    bot = Bot(
        token=settings.bot.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    storage = MemoryStorage()
    dispatcher = Dispatcher(storage=storage)
    dispatcher.include_router(setup_routers())

    dispatcher["settings"] = settings
    dispatcher["expense_service"] = expense_service
    dispatcher["category_service"] = category_service
    dispatcher["user_service"] = user_service
    dispatcher["reminder_service"] = reminder_service
    dispatcher["engine"] = engine

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_daily_reminders,
        "cron",
        hour=22,
        minute=0,
        args=(dispatcher, bot),
    )
    scheduler.start()

    return dispatcher, bot, scheduler


async def main() -> None:
    """Run polling using the configured dispatcher and bot."""

    dispatcher, bot, scheduler = await on_startup()
    engine = dispatcher["engine"]

    try:
        logger.info("Starting Moneywise bot polling")
        await dispatcher.start_polling(bot)
    finally:
        await dispatcher.storage.close()
        await dispatcher.storage.wait_closed()
        await bot.session.close()
        await scheduler.shutdown(wait=False)
        await engine.dispose()


async def send_daily_reminders(dispatcher: Dispatcher, bot: Bot) -> None:
    """Send reminder messages to users without expenses for today."""

    reminder_service: ReminderService = dispatcher["reminder_service"]
    expense_service: ExpenseService = dispatcher["expense_service"]

    today = dt.date.today()
    users = await reminder_service.list_users_with_notifications()
    if not users:
        return

    for user in users:
        try:
            has_expenses = await expense_service.has_expenses_on_date(
                user_id=user.id,
                date_value=today,
            )
        except Exception as error:  # pragma: no cover - defensive logging
            logger.warning(
                "Failed to check expenses for user %s: %s",
                user.telegram_id,
                error,
            )
            continue

        if has_expenses:
            continue

        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=REMINDER_TEXT,
                reply_markup=build_reminder_keyboard(),
            )
        except Exception as error:  # pragma: no cover - defensive logging
            logger.warning(
                "Failed to send reminder to user %s: %s",
                user.telegram_id,
                error,
            )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ConfigurationError as error:
        logging.basicConfig(level=logging.ERROR)
        logging.error("Configuration error: %s", error)
