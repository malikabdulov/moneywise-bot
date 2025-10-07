"""Expense related business logic services."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Expense
from app.db.repositories import ExpenseRepository, sum_expenses


@dataclass(slots=True)
class ExpenseSummary:
    """Aggregated data for a period of expenses."""

    period_start: dt.datetime
    period_end: dt.datetime
    expenses: list[Expense]
    category_totals: dict[str, Decimal]
    total: Decimal


class ExpenseService:
    """Business logic for manipulating expenses."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add_expense_from_message(self, user_id: int, message_text: str) -> str:
        """Parse message text and store the resulting expense.

        Returns a human-readable confirmation message.
        """

        amount, category, description = self._parse_add_command(message_text)
        spent_at = dt.datetime.utcnow()

        async with self._session_factory() as session:
            repository = ExpenseRepository(session)
            expense = await repository.add_expense(
                user_id=user_id,
                amount=amount,
                category=category,
                description=description,
                spent_at=spent_at,
            )

        return (
            f"Добавлена трата: {expense.amount} ₽, категория — {expense.category}"
            + (f". Описание: {expense.description}" if expense.description else "")
        )

    async def get_today_summary(self, user_id: int, now: dt.datetime | None = None) -> ExpenseSummary:
        """Return summary of today's expenses for the given user."""

        now = now or dt.datetime.utcnow()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + dt.timedelta(days=1)
        return await self._build_summary(user_id=user_id, start=start, end=end)

    async def get_month_summary(self, user_id: int, now: dt.datetime | None = None) -> ExpenseSummary:
        """Return summary of the current month's expenses for the user."""

        now = now or dt.datetime.utcnow()
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month = (start + dt.timedelta(days=32)).replace(day=1)
        return await self._build_summary(user_id=user_id, start=start, end=next_month)

    async def list_recent_expenses(self, user_id: int, limit: int = 5) -> list[Expense]:
        """Return the most recent expenses for a user."""

        async with self._session_factory() as session:
            repository = ExpenseRepository(session)
            expenses = await repository.list_recent_expenses(user_id=user_id, limit=limit)
        return expenses

    async def _build_summary(
        self,
        *,
        user_id: int,
        start: dt.datetime,
        end: dt.datetime,
    ) -> ExpenseSummary:
        async with self._session_factory() as session:
            repository = ExpenseRepository(session)
            expenses = await repository.get_expenses_for_period(user_id=user_id, start=start, end=end)
            category_totals = await repository.get_category_stats(user_id=user_id, start=start, end=end)
        total = sum_expenses(expenses)
        return ExpenseSummary(
            period_start=start,
            period_end=end,
            expenses=expenses,
            category_totals=category_totals,
            total=total,
        )

    def _parse_add_command(self, message_text: str) -> tuple[Decimal, str, str | None]:
        """Parse the text of an /add command into components."""

        payload = message_text.strip()
        if payload.startswith("/add"):
            payload = payload[4:].strip()

        if not payload:
            raise ValueError(
                "Не хватает данных. Используйте формат: /add <сумма> <категория> [описание]"
            )

        parts = payload.split(maxsplit=2)
        if len(parts) < 2:
            raise ValueError("Нужно указать сумму и категорию. Пример: /add 250 еда")

        amount_str, category = parts[0], parts[1]
        description = parts[2] if len(parts) == 3 else None

        try:
            amount = Decimal(amount_str)
        except InvalidOperation as exc:  # pragma: no cover - defensive
            raise ValueError("Сумма должна быть числом") from exc

        if amount <= 0:
            raise ValueError("Сумма должна быть положительной")

        category = category.lower()
        return amount, category, description

