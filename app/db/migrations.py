"""Lightweight database migrations for schema compatibility."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection


async def ensure_notifications_flag(connection: AsyncConnection) -> None:
    """Ensure the ``users`` table has the ``notifications_enabled`` column."""

    def _column_missing(sync_connection: Connection) -> bool:
        inspector = inspect(sync_connection)
        if not inspector.has_table("users"):
            return False

        columns = inspector.get_columns("users")
        return all(column["name"] != "notifications_enabled" for column in columns)

    if await connection.run_sync(_column_missing):
        await connection.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN notifications_enabled BOOLEAN NOT NULL DEFAULT 1
                """
            )
        )
        await connection.execute(
            text(
                """
                UPDATE users
                SET notifications_enabled = 1
                WHERE notifications_enabled IS NULL
                """
            )
        )


__all__ = ["ensure_notifications_flag"]

