"""Database repositories provide high level access to persistent data."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Expense


class ExpenseRepository:
    """Repository for working with :class:`Expense` records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_expense(
        self,
        *,
        user_id: int,
        amount: Decimal,
        category: str,
        description: str | None,
        spent_at: dt.datetime,
    ) -> Expense:
        """Persist a new expense and return the created entity."""

        expense = Expense(
            user_id=user_id,
            amount=amount,
            category=category,
            description=description,
            spent_at=spent_at,
        )
        self._session.add(expense)
        await self._session.commit()
        await self._session.refresh(expense)
        return expense

    async def get_expenses_for_period(
        self,
        *,
        user_id: int,
        start: dt.datetime,
        end: dt.datetime,
    ) -> list[Expense]:
        """Return expenses for a user in the given time frame."""

        statement = (
            select(Expense)
            .where(Expense.user_id == user_id)
            .where(Expense.spent_at >= start)
            .where(Expense.spent_at < end)
            .order_by(Expense.spent_at.desc())
        )
        result = await self._session.execute(statement)
        expenses = list(result.scalars().all())
        return expenses

    async def get_category_stats(
        self,
        *,
        user_id: int,
        start: dt.datetime,
        end: dt.datetime,
    ) -> dict[str, Decimal]:
        """Return aggregated expense sum grouped by category."""

        statement = (
            select(Expense.category, func.sum(Expense.amount))
            .where(Expense.user_id == user_id)
            .where(Expense.spent_at >= start)
            .where(Expense.spent_at < end)
            .group_by(Expense.category)
        )
        result = await self._session.execute(statement)
        stats: dict[str, Decimal] = defaultdict(Decimal)
        for category, total in result.all():
            stats[category] = Decimal(total)
        return dict(stats)

    async def list_recent_expenses(
        self,
        *,
        user_id: int,
        limit: int,
    ) -> list[Expense]:
        """Return the most recent expenses for the user."""

        statement = (
            select(Expense)
            .where(Expense.user_id == user_id)
            .order_by(Expense.spent_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())


def sum_expenses(expenses: Iterable[Expense]) -> Decimal:
    """Return the total amount spent across the iterable of expenses."""

    total = sum((expense.amount for expense in expenses), Decimal(0))
    return total


__all__ = ["ExpenseRepository", "sum_expenses"]
