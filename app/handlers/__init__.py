"""Telegram bot handlers."""

from aiogram import Router

from . import add, categories, start, stats, today


def setup_routers() -> Router:
    """Return a root router with all sub-routers included."""

    router = Router()
    router.include_router(start.router)
    router.include_router(add.router)
    router.include_router(categories.router)
    router.include_router(stats.router)
    router.include_router(today.router)
    return router


__all__ = ["setup_routers"]
