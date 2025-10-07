"""Database engine and session factory helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings


def get_engine(settings: Settings) -> AsyncEngine:
    """Create an asynchronous SQLAlchemy engine based on provided settings."""

    return create_async_engine(settings.database.url, echo=False, future=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return a session factory bound to the given engine."""

    return async_sessionmaker(bind=engine, expire_on_commit=False)


def session_provider(factory: async_sessionmaker[AsyncSession]) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Return an async context manager that yields :class:`AsyncSession` objects."""

    async def _get_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    return _get_session


__all__ = ["get_engine", "create_session_factory", "session_provider"]
