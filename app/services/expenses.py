"""Expense related business logic services."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
import re
from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Category, Expense
from app.db.repositories import CategoryRepository, ExpenseRepository, sum_expenses


TWO_PLACES = Decimal("0.01")


@dataclass(slots=True)
class ExpenseSummary:
    """Aggregated data for a period of expenses."""

    period_start: dt.datetime
    period_end: dt.datetime
    expenses: list[Expense]
    category_totals: dict[str, Decimal]
    total: Decimal


@dataclass(slots=True)
class SmartExpenseDraft:
    """Parsed entities extracted from a free-form expense message."""

    category: Category | None
    amount: Decimal | None
    spent_at: dt.datetime | None
    description: str | None


DATE_PATTERN = re.compile(r"\b(\d{1,2})[.](\d{1,2})[.](\d{2,4})\b")
AMOUNT_PATTERN = re.compile(r"(?<!\d)(\d+(?:[.,]\d{1,2})?)(?!\d)")
DATE_ALIASES = {
    "сегодня": 0,
    "вчера": 1,
    "позавчера": 2,
}


class ExpenseService:
    """Business logic for manipulating expenses."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def parse_smart_message(
        self,
        message_text: str,
        categories: Sequence[Category],
        *,
        now: dt.datetime | None = None,
    ) -> SmartExpenseDraft:
        """Extract entities from a free-form expense message."""

        now = now or dt.datetime.now()
        text = (message_text or "").strip()
        if not text:
            return SmartExpenseDraft(None, None, None, None)

        spans: list[tuple[int, int]] = []

        amount: Decimal | None = None
        amount_match = AMOUNT_PATTERN.search(text)
        if amount_match:
            raw_amount = amount_match.group(1).replace(",", ".")
            try:
                parsed_amount = Decimal(raw_amount)
            except InvalidOperation:
                parsed_amount = None
            else:
                if parsed_amount > 0:
                    amount = parsed_amount
                    spans.append(amount_match.span())

        spent_at: dt.datetime | None = None
        date_match = DATE_PATTERN.search(text)
        if date_match:
            day, month, year = map(int, date_match.groups())
            if year < 100:
                year += 2000
            try:
                date_value = dt.date(year, month, day)
            except ValueError:
                date_value = None
            else:
                if date_value <= now.date():
                    spent_at = now.replace(
                        year=date_value.year,
                        month=date_value.month,
                        day=date_value.day,
                    )
                    spans.append(date_match.span())

        if spent_at is None:
            for alias, offset in DATE_ALIASES.items():
                pattern = re.compile(rf"\b{re.escape(alias)}\b", re.IGNORECASE)
                match = pattern.search(text)
                if match:
                    date_value = now.date() - dt.timedelta(days=offset)
                    spent_at = now.replace(
                        year=date_value.year,
                        month=date_value.month,
                        day=date_value.day,
                    )
                    spans.append(match.span())
                    break

        category: Category | None = None
        if categories:
            for candidate in sorted(categories, key=lambda item: len(item.name), reverse=True):
                pattern = re.compile(rf"\b{re.escape(candidate.name)}\b", re.IGNORECASE)
                match = pattern.search(text)
                if match:
                    category = candidate
                    spans.append(match.span())
                    break

        description: str | None
        if spans:
            description = self._extract_description(text, spans)
        else:
            normalized = " ".join(text.split())
            description = normalized or None

        return SmartExpenseDraft(category, amount, spent_at, description)

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
        category: str | None = None,
        category_id: int | None = None,
        description: str | None,
        spent_at: dt.datetime | None = None,
    ) -> str:
        """Persist a new expense using validated data and return confirmation text."""

        spent_at = spent_at or dt.datetime.now()

        async with self._session_factory() as session:
            category_repository = CategoryRepository(session)
            if category_id is not None:
                category_obj = await category_repository.get_by_id(
                    user_id=user_id, category_id=category_id
                )
                if category_obj is None:
                    raise ValueError("Категория не найдена")
            else:
                if not category:
                    raise ValueError("Категория не указана")
                normalized_category = self._normalize_category_name(category)
                category_obj = await category_repository.get_by_normalized_name(
                    user_id=user_id,
                    normalized_name=normalized_category,
                )
                if category_obj is None:
                    raise ValueError(f'Категория "{category}" не найдена')

            expense_repository = ExpenseRepository(session)
            await expense_repository.add_expense(
                user_id=user_id,
                amount=amount,
                category_id=category_obj.id,
                description=description,
                spent_at=spent_at,
            )

        return self._render_confirmation(
            amount=amount,
            category=category_obj.name,
            description=description,
        )

    async def has_expenses_on_date(
        self,
        user_id: int,
        date_value: dt.date,
    ) -> bool:
        """Return ``True`` if the user has expenses for the provided date."""

        start = dt.datetime.combine(date_value, dt.time.min)
        end = start + dt.timedelta(days=1)

        async with self._session_factory() as session:
            repository = ExpenseRepository(session)
            return await repository.has_expenses_in_period(
                user_id=user_id,
                start=start,
                end=end,
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

    async def list_recent_expenses(self, user_id: int, limit: int = 10) -> list[Expense]:
        """Return the most recent expenses for the user."""

        async with self._session_factory() as session:
            repository = ExpenseRepository(session)
            expenses = await repository.list_recent_expenses(user_id=user_id, limit=limit)
        return expenses

    async def render_recent_expenses_message(self, user_id: int, limit: int) -> str:
        """Return a formatted list of recent expenses."""

        expenses = await self.list_recent_expenses(user_id=user_id, limit=limit)
        if not expenses:
            return "Расходов ещё не было"

        lines = ["Последние расходы:"]
        for expense in expenses:
            timestamp = expense.spent_at.strftime("%d.%m %H:%M")
            description = f" ({expense.description})" if expense.description else ""
            lines.append(
                (
                    f"{timestamp} — {expense.category.name}: "
                    f"{self._format_amount(expense.amount)} тенге{description}"
                )
            )
        return "\n".join(lines)

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
                (
                    f"{time_text} — {expense.category.name}: "
                    f"{self._format_amount(expense.amount)} тенге{description}"
                )
            )
        lines.append(f"Итого: {self._format_amount(summary.total)} тенге")
        return "\n".join(lines)

    async def render_month_message(self, user_id: int) -> str:
        """Return a monthly statistics text enriched with category limits."""

        summary = await self.get_month_summary(user_id=user_id)
        categories = await self._list_categories(user_id=user_id)

        if not summary.expenses and not categories:
            return "За текущий месяц ещё нет расходов"

        lines = ["Статистика за месяц:"]
        if not summary.expenses:
            lines.append("Расходов ещё не было.")

        totals_by_normalized: dict[str, tuple[str, Decimal]] = {}
        for name, total in summary.category_totals.items():
            totals_by_normalized[self._normalize_category_name(name)] = (name, total)

        if categories:
            category_lines = []
            for category in sorted(
                categories,
                key=lambda item: (
                    -totals_by_normalized.get(item.normalized_name, ("", Decimal(0)))[1],
                    item.name.lower(),
                ),
            ):
                spent = totals_by_normalized.pop(
                    category.normalized_name, (category.name, Decimal(0))
                )[1]
                category_lines.append(self._format_category_line(category, spent))
            lines.extend(category_lines)

        if totals_by_normalized:
            for name, total in sorted(
                totals_by_normalized.values(), key=lambda item: item[1], reverse=True
            ):
                lines.append(f"{name}: {self._format_amount(total)} тенге (лимит не задан)")

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

    @staticmethod
    def _extract_description(text: str, spans: Sequence[tuple[int, int]]) -> str | None:
        """Return remaining text after removing recognised entity spans."""

        if not spans:
            return None

        cleaned: list[str] = []
        last_index = 0
        for start, end in sorted(spans):
            if start > last_index:
                cleaned.append(text[last_index:start])
            last_index = max(last_index, end)
        cleaned.append(text[last_index:])

        remaining = "".join(cleaned)
        normalized = " ".join(remaining.split())
        return normalized or None

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

        category = category.strip()
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

    async def _list_categories(self, user_id: int) -> list[Category]:
        """Return categories belonging to the user."""

        async with self._session_factory() as session:
            repository = CategoryRepository(session)
            return await repository.list_categories(user_id=user_id)

    def _format_category_line(self, category: Category, spent: Decimal) -> str:
        """Return formatted statistic line for a category with limit info."""

        limit = category.monthly_limit
        line = (
            f"{category.name}: {self._format_amount(spent)} тенге из лимита "
            f"{self._format_amount(limit)} тенге"
        )
        if spent < limit:
            remaining = limit - spent
            line += f" — осталось {self._format_amount(remaining)} тенге"
        elif spent == limit:
            line += " — лимит исчерпан"
        else:
            over = spent - limit
            line += f" — ⚠️ Перерасход {self._format_amount(over)} тенге"
        return line

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

    @staticmethod
    def _normalize_category_name(name: str) -> str:
        """Normalize category name for consistent lookups."""

        return name.strip().lower()
