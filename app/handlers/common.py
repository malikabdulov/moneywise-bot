"""Common inline keyboards for handlers."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.models import Category


def build_comment_choice_keyboard(*, enter_data: str, skip_data: str) -> InlineKeyboardMarkup:
    """Return inline keyboard with options to enter or skip a comment."""

    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Ввести", callback_data=enter_data)
    builder.button(text="⏭ Пропустить", callback_data=skip_data)
    builder.adjust(2)
    return builder.as_markup()


def build_category_shortcuts_keyboard(
    categories: Sequence[Category],
    *,
    encode: Callable[[Category], str],
    all_categories_data: str,
) -> InlineKeyboardMarkup:
    """Return inline keyboard with a few quick category options."""

    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.button(text=category.name, callback_data=encode(category))
    builder.button(text="Все категории", callback_data=all_categories_data)
    builder.adjust(2)
    return builder.as_markup()


def build_all_categories_keyboard(
    categories: Sequence[Category],
    *,
    encode: Callable[[Category], str],
) -> InlineKeyboardMarkup:
    """Return inline keyboard with the full list of categories."""

    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.button(text=category.name, callback_data=encode(category))
    if categories:
        builder.adjust(2)
    return builder.as_markup()
