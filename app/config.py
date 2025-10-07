"""Application configuration utilities.

This module loads and validates application configuration from environment
variables. It exposes a :func:`get_settings` helper that returns a cached
instance of :class:`Settings` with typed access to bot and database options.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

from dotenv import load_dotenv

load_dotenv()


class ConfigurationError(RuntimeError):
    """Raised when mandatory configuration values are missing."""


@dataclass(slots=True)
class BotConfig:
    """Telegram bot related configuration."""

    token: str


@dataclass(slots=True)
class DatabaseConfig:
    """Database connection settings."""

    url: str


@dataclass(slots=True)
class LoggingConfig:
    """Logging related configuration settings."""

    level: str


@dataclass(slots=True)
class Settings:
    """Container for all application settings."""

    bot: BotConfig
    database: DatabaseConfig
    logging: LoggingConfig


DEFAULT_DB_URL: Final[str] = "sqlite+aiosqlite:///./moneywise.db"
DEFAULT_LOG_LEVEL: Final[str] = "INFO"


def _load_bot_config() -> BotConfig:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ConfigurationError("BOT_TOKEN environment variable is required")
    return BotConfig(token=token)


def _load_database_config() -> DatabaseConfig:
    url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    return DatabaseConfig(url=url)


def _load_logging_config() -> LoggingConfig:
    level = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL)
    return LoggingConfig(level=level)


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings loaded from environment variables."""

    return Settings(
        bot=_load_bot_config(),
        database=_load_database_config(),
        logging=_load_logging_config(),
    )


__all__ = [
    "BotConfig",
    "DatabaseConfig",
    "LoggingConfig",
    "Settings",
    "ConfigurationError",
    "get_settings",
]
