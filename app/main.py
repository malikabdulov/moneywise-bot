"""Application entry point for the Moneywise Telegram bot."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from app.config import ConfigurationError, get_settings
from app.db import Base, create_session_factory, get_engine
from app.handlers import setup_routers
from app.services import CategoryService, ExpenseService, UserService

logger = logging.getLogger(__name__)


async def on_startup() -> tuple[Dispatcher, Bot]:
    """Configure application components and return dispatcher and bot."""

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
    dispatcher["engine"] = engine

    return dispatcher, bot


async def main() -> None:
    """Run polling using the configured dispatcher and bot."""

    dispatcher, bot = await on_startup()
    engine = dispatcher["engine"]

    try:
        logger.info("Starting Moneywise bot polling")
        await dispatcher.start_polling(bot)
    finally:
        await dispatcher.storage.close()
        await dispatcher.storage.wait_closed()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ConfigurationError as error:
        logging.basicConfig(level=logging.ERROR)
        logging.error("Configuration error: %s", error)
