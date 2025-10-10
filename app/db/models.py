"""Database models for the Moneywise bot."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> dt.datetime:
    """Return current UTC datetime without timezone info."""

    return dt.datetime.utcnow()


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(), default=utcnow, nullable=False)


class User(Base):
    """Represents a Telegram user interacting with the bot."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True, nullable=False
    )
    username: Mapped[str | None] = mapped_column(String(32))
    first_name: Mapped[str | None] = mapped_column(String(64))
    last_name: Mapped[str | None] = mapped_column(String(64))
    language_code: Mapped[str | None] = mapped_column(String(8))
    is_bot: Mapped[bool] = mapped_column(default=False, nullable=False)
    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )

    expenses: Mapped[list["Expense"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    categories: Mapped[list["Category"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return "User(id={id}, telegram_id={telegram_id})".format(
            id=self.id, telegram_id=self.telegram_id
        )


class Category(Base):
    """Represents a spending category available to a Telegram user."""

    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("user_id", "normalized_name", name="uq_categories_user_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    monthly_limit: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    user: Mapped["User"] = relationship(back_populates="categories")
    expenses: Mapped[list["Expense"]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            "Category(id={id}, user_id={user_id}, name={name}, monthly_limit={limit})".format(
                id=self.id,
                user_id=self.user_id,
                name=self.name,
                limit=self.monthly_limit,
            )
        )


class Expense(Base):
    """Represents a single expense made by a Telegram user."""

    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    spent_at: Mapped[dt.datetime] = mapped_column(DateTime(), default=utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="expenses")
    category: Mapped["Category"] = relationship(back_populates="expenses")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            "Expense(id={id}, user_id={user_id}, amount={amount}, category_id={category_id})".format(
                id=self.id,
                user_id=self.user_id,
                amount=self.amount,
                category_id=self.category_id,
            )
        )

