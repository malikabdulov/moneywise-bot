"""Expense related business logic services."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Expense
from app.db.repositories import ExpenseRepository, sum_expenses


TWO_PLACES = Decimal("0.01")


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
        """Parse message text, persist the expense and return the legacy response."""

        amount, category, description = self._parse_add_command(message_text)
        return await self.add_expense(
            user_id=user_id,
            amount=amount,
            category=category,
            description=description,
        )

    async def add_expense(
        self,
        *,
        user_id: int,
        amount: Decimal,
        category: str,
        description: str | None,
        spent_at: dt.datetime | None = None,
    ) -> str:
        """Persist a new expense using validated data and return confirmation text."""

        spent_at = spent_at or dt.datetime.now()

        async with self._session_factory() as session:
            repository = ExpenseRepository(session)
            await repository.add_expense(
                user_id=user_id,
                amount=amount,
                category=category,
                description=description,
                spent_at=spent_at,
            )

        return self._render_confirmation(
            amount=amount,
            category=category,
            description=description,
        )

    async def get_today_summary(self, user_id: int, now: dt.datetime | None = None) -> ExpenseSummary:
        """Return summary of today's expenses for the given user."""

        now = now or dt.datetime.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + dt.timedelta(days=1)
        return await self._build_summary(user_id=user_id, start=start, end=end)

    async def get_month_summary(self, user_id: int, now: dt.datetime | None = None) -> ExpenseSummary:
        """Return summary of the current month's expenses for the user."""

        now = now or dt.datetime.now()
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month = (start + dt.timedelta(days=32)).replace(day=1)
        return await self._build_summary(user_id=user_id, start=start, end=next_month)

    async def list_recent_expenses(self, user_id: int, limit: int = 5) -> list[Expense]:
        """Return the most recent expenses for the user."""

        async with self._session_factory() as session:
            repository = ExpenseRepository(session)
            expenses = await repository.list_recent_expenses(user_id=user_id, limit=limit)
        return expenses

    async def render_today_message(self, user_id: int) -> str:
        """Return a text report for today's expenses matching the legacy bot."""

        summary = await self.get_today_summary(user_id=user_id)
        if not summary.expenses:
            return "Сегодня расходов ещё не было"

        lines = ["Расходы сегодня:"]
        for expense in summary.expenses:
            time_text = expense.spent_at.strftime("%H:%M")
            description = f" ({expense.description})" if expense.description else ""
            lines.append(
                f"{time_text} — {expense.category}: {self._format_amount(expense.amount)} тенге{description}"
            )
        lines.append(f"Итого: {self._format_amount(summary.total)} тенге")
        return "\n".join(lines)

    async def render_month_message(self, user_id: int) -> str:
        """Return a monthly statistics text matching the legacy bot."""

        summary = await self.get_month_summary(user_id=user_id)
        if not summary.expenses:
            return "За текущий месяц ещё нет расходов"

        lines = ["Статистика за месяц:"]
        for category, total in sorted(
            summary.category_totals.items(), key=lambda item: item[1], reverse=True
        ):
            lines.append(f"{category}: {self._format_amount(total)} тенге")
        lines.append(f"Всего: {self._format_amount(summary.total)} тенге")
        return "\n".join(lines)

    async def _build_summary(
        self,
        *,
        user_id: int,
        start: dt.datetime,
        end: dt.datetime,
    ) -> ExpenseSummary:
        async with self._session_factory() as session:
            repository = ExpenseRepository(session)
            expenses = await repository.get_expenses_for_period(
                user_id=user_id, start=start, end=end
            )
            category_totals = await repository.get_category_stats(
                user_id=user_id, start=start, end=end
            )
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
        description = parts[2].strip() if len(parts) == 3 else None

        amount = self.parse_amount(amount_str)

        category = category.strip().lower()
        if not category:
            raise ValueError("Категория не может быть пустой")

        return amount, category, description

    def parse_amount(self, value: str) -> Decimal:
        """Parse textual amount and return it as a Decimal."""

        normalized = value.strip().replace(",", ".")
        if not normalized:
            raise ValueError("Сумма должна быть числом")

        try:
            amount = Decimal(normalized)
        except InvalidOperation as exc:  # pragma: no cover - defensive
            raise ValueError("Сумма должна быть числом") from exc

        if amount <= 0:
            raise ValueError("Сумма должна быть положительной")

        return amount

    def format_amount(self, value: Decimal) -> str:
        """Public helper for rendering monetary values."""

        return self._format_amount(value)

    def _render_confirmation(
        self, *, amount: Decimal, category: str, description: str | None
    ) -> str:
        """Return confirmation text matching the legacy bot."""

        lines = [
            "Расход сохранён",
            f"Сумма: {self._format_amount(amount)} тенге",
            f"Категория: {category}",
        ]
        if description:
            lines.append(f"Комментарий: {description}")
        return "\n".join(lines)

    @staticmethod
    def _format_amount(value: Decimal) -> str:
        """Return human readable representation compatible with the legacy bot."""

        normalized = value.quantize(TWO_PLACES)
        if normalized == normalized.to_integral():
            return f"{int(normalized)}"
        return f"{normalized.normalize()}"
