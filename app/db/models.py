"""Database models for the Moneywise bot."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> dt.datetime:
    """Return current UTC datetime."""

    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class Expense(Base):
    """Represents a single expense made by a Telegram user."""

    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    spent_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            "Expense(id={id}, user_id={user_id}, amount={amount}, category={category})".format(
                id=self.id, user_id=self.user_id, amount=self.amount, category=self.category
            )
        )

