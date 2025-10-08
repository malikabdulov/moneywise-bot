"""Category related business logic services."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Category
from app.db.repositories import CategoryRepository

TWO_PLACES = Decimal("0.01")


class CategoryService:
    """Business logic for manipulating user categories."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_categories(self, user_id: int) -> list[Category]:
        """Return all categories for a given user."""

        async with self._session_factory() as session:
            repository = CategoryRepository(session)
            return await repository.list_categories(user_id=user_id)

    async def list_categories_message(self, user_id: int) -> str:
        """Return textual representation of existing categories."""

        categories = await self.list_categories(user_id=user_id)
        return self.render_categories(categories)

    def render_categories(self, categories: Sequence[Category]) -> str:
        """Render category collection using legacy text format."""

        if not categories:
            return "Категории пока не созданы"

        lines = ["Категории:"]
        for category in categories:
            lines.append(
                f"{category.name} — лимит {self._format_amount(category.monthly_limit)} руб."
            )
        return "\n".join(lines)

    async def get_category(self, user_id: int, category_id: int) -> Category | None:
        """Return a category by identifier if it belongs to the user."""

        async with self._session_factory() as session:
            repository = CategoryRepository(session)
            return await repository.get_by_id(user_id=user_id, category_id=category_id)

    async def create_category(self, user_id: int, name: str, monthly_limit: Decimal) -> str:
        """Create a category using validated data and return confirmation text."""

        name = name.strip()
        if not name:
            raise ValueError("Название категории не может быть пустым")
        if monthly_limit <= 0:
            raise ValueError("Лимит должен быть положительным")

        normalized_name = self._normalize_name(name)

        async with self._session_factory() as session:
            repository = CategoryRepository(session)
            existing = await repository.get_by_normalized_name(
                user_id=user_id, normalized_name=normalized_name
            )
            if existing is not None:
                raise ValueError(f'Категория "{existing.name}" уже существует')
            category = await repository.add_category(
                user_id=user_id,
                name=name,
                normalized_name=normalized_name,
                monthly_limit=monthly_limit,
            )

        return (
            f'Категория "{category.name}" с лимитом '
            f"{self._format_amount(category.monthly_limit)} руб. добавлена"
        )

    async def update_category_limit(
        self, user_id: int, category_id: int, monthly_limit: Decimal
    ) -> str:
        """Update category limit by identifier and return confirmation text."""

        if monthly_limit <= 0:
            raise ValueError("Лимит должен быть положительным")

        async with self._session_factory() as session:
            repository = CategoryRepository(session)
            category = await repository.get_by_id(user_id=user_id, category_id=category_id)
            if category is None:
                raise ValueError("Категория не найдена")
            category = await repository.update_category(
                category,
                monthly_limit=monthly_limit,
            )

        return (
            f'Лимит для категории "{category.name}" обновлён: '
            f"{self._format_amount(category.monthly_limit)} руб."
        )

    async def rename_category(self, user_id: int, category_id: int, new_name: str) -> str:
        """Rename a category by identifier and return confirmation text."""

        new_name = new_name.strip()
        if not new_name:
            raise ValueError("Название категории не может быть пустым")

        new_normalized = self._normalize_name(new_name)

        async with self._session_factory() as session:
            repository = CategoryRepository(session)
            category = await repository.get_by_id(user_id=user_id, category_id=category_id)
            if category is None:
                raise ValueError("Категория не найдена")
            if category.normalized_name == new_normalized:
                raise ValueError("Новое название должно отличаться от текущего")
            conflict = await repository.get_by_normalized_name(
                user_id=user_id, normalized_name=new_normalized
            )
            if conflict is not None and conflict.id != category.id:
                raise ValueError(f'Категория "{conflict.name}" уже существует')
            old_name = category.name
            category = await repository.update_category(
                category,
                name=new_name,
                normalized_name=new_normalized,
            )

        return f'Категория "{old_name}" переименована в "{category.name}"'

    async def delete_category(self, user_id: int, category_id: int) -> str:
        """Delete a category by identifier and return confirmation text."""

        async with self._session_factory() as session:
            repository = CategoryRepository(session)
            category = await repository.get_by_id(user_id=user_id, category_id=category_id)
            if category is None:
                raise ValueError("Категория не найдена")
            await repository.delete_category(category)

        return f'Категория "{category.name}" удалена'

    def parse_limit(self, value: str) -> Decimal:
        """Parse textual limit and propagate validation errors."""

        return self._parse_limit(value)

    def format_amount(self, amount: Decimal) -> str:
        """Expose amount formatting for UI helpers."""

        return self._format_amount(amount)

    async def add_category_from_message(self, user_id: int, message_text: str) -> str:
        """Parse message text and create a new category."""

        payload = self._strip_command(message_text, prefix="/category_add")
        name, monthly_limit = self._split_name_and_limit(
            payload,
            "Используйте формат: /category_add <название> <лимит>",
        )
        return await self.create_category(
            user_id=user_id,
            name=name,
            monthly_limit=monthly_limit,
        )

    async def update_limit_from_message(self, user_id: int, message_text: str) -> str:
        """Update monthly limit for an existing category."""

        payload = self._strip_command(message_text, prefix="/category_limit")
        name, monthly_limit = self._split_name_and_limit(
            payload,
            "Используйте формат: /category_limit <название> <лимит>",
        )
        normalized_name = self._normalize_name(name)

        async with self._session_factory() as session:
            repository = CategoryRepository(session)
            category = await repository.get_by_normalized_name(
                user_id=user_id, normalized_name=normalized_name
            )
            if category is None:
                raise ValueError(f'Категория "{name}" не найдена')
            category = await repository.update_category(
                category,
                monthly_limit=monthly_limit,
            )

        return (
            f'Лимит для категории "{category.name}" обновлён: '
            f"{self._format_amount(category.monthly_limit)} руб."
        )

    async def rename_category_from_message(self, user_id: int, message_text: str) -> str:
        """Rename an existing category."""

        payload = self._strip_command(message_text, prefix="/category_rename")
        parts = [part.strip() for part in payload.split("|", maxsplit=1)] if payload else []
        if len(parts) != 2 or not all(parts):
            raise ValueError(
                "Используйте формат: /category_rename <старое название> | <новое название>"
            )
        old_name, new_name = parts
        old_normalized = self._normalize_name(old_name)
        new_normalized = self._normalize_name(new_name)
        if old_normalized == new_normalized:
            raise ValueError("Новое название должно отличаться от текущего")

        async with self._session_factory() as session:
            repository = CategoryRepository(session)
            category = await repository.get_by_normalized_name(
                user_id=user_id, normalized_name=old_normalized
            )
            if category is None:
                raise ValueError(f'Категория "{old_name}" не найдена')
            conflict = await repository.get_by_normalized_name(
                user_id=user_id, normalized_name=new_normalized
            )
            if conflict is not None and conflict.id != category.id:
                raise ValueError(f'Категория "{conflict.name}" уже существует')
            category = await repository.update_category(
                category,
                name=new_name,
                normalized_name=new_normalized,
            )

        return f'Категория "{old_name}" переименована в "{category.name}"'

    async def delete_category_from_message(self, user_id: int, message_text: str) -> str:
        """Delete an existing category."""

        payload = self._strip_command(message_text, prefix="/category_delete").strip()
        if not payload:
            raise ValueError("Укажите название категории: /category_delete <название>")
        name = payload
        normalized_name = self._normalize_name(name)

        async with self._session_factory() as session:
            repository = CategoryRepository(session)
            category = await repository.get_by_normalized_name(
                user_id=user_id, normalized_name=normalized_name
            )
            if category is None:
                raise ValueError(f'Категория "{name}" не найдена')
            await repository.delete_category(category)

        return f'Категория "{category.name}" удалена'

    def _split_name_and_limit(self, payload: str, error_message: str) -> tuple[str, Decimal]:
        """Split payload into category name and numeric limit."""

        if not payload:
            raise ValueError(error_message)
        parts = payload.split()
        if len(parts) < 2:
            raise ValueError(error_message)
        limit_str = parts[-1]
        name = " ".join(parts[:-1]).strip()
        if not name:
            raise ValueError("Название категории не может быть пустым")
        monthly_limit = self._parse_limit(limit_str)
        if monthly_limit <= 0:
            raise ValueError("Лимит должен быть положительным")
        return name, monthly_limit

    @staticmethod
    def _strip_command(message_text: str, *, prefix: str) -> str:
        """Remove command prefix from the incoming text."""

        payload = message_text.strip()
        if payload.startswith(prefix):
            payload = payload[len(prefix) :].strip()
        return payload

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Return a normalized version of category name for comparisons."""

        return name.strip().lower()

    @staticmethod
    def _parse_limit(value: str) -> Decimal:
        """Convert textual limit into a Decimal value."""

        normalized = value.replace(",", ".")
        try:
            return Decimal(normalized)
        except InvalidOperation as exc:  # pragma: no cover - defensive
            raise ValueError("Лимит должен быть числом") from exc

    @staticmethod
    def _format_amount(amount: Decimal) -> str:
        """Return a human readable representation of a decimal amount."""

        normalized = amount.quantize(TWO_PLACES)
        if normalized == normalized.to_integral():
            return f"{int(normalized)}"
        return f"{normalized.normalize()}"
