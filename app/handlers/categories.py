"""Handlers for managing expense categories via inline keyboards."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services import CategoryService

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.db.models import Category

logger = logging.getLogger(__name__)

router = Router()


class CategoryStates(StatesGroup):
    """Finite states for multi-step category operations."""

    adding_name = State()
    adding_limit = State()
    renaming = State()
    updating_limit = State()


class CategoryAction(CallbackData, prefix="cat"):
    """Callback data schema for category menu buttons."""

    action: str
    category_id: int | None = None


def build_categories_keyboard(categories: Sequence["Category"]) -> InlineKeyboardMarkup:
    """Build an inline keyboard with existing categories and actions."""

    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.button(
            text=category.name,
            callback_data=CategoryAction(action="open", category_id=category.id).pack(),
        )
    builder.button(
        text="➕ Добавить категорию",
        callback_data=CategoryAction(action="add").pack(),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_category_actions_keyboard(category_id: int) -> InlineKeyboardMarkup:
    """Return keyboard with actions for a selected category."""

    builder = InlineKeyboardBuilder()
    builder.button(
        text="💰 Изменить лимит",
        callback_data=CategoryAction(action="limit", category_id=category_id).pack(),
    )
    builder.button(
        text="✏️ Переименовать",
        callback_data=CategoryAction(action="rename", category_id=category_id).pack(),
    )
    builder.button(
        text="🗑 Удалить",
        callback_data=CategoryAction(action="delete_prompt", category_id=category_id).pack(),
    )
    builder.button(
        text="⬅️ Назад",
        callback_data=CategoryAction(action="list").pack(),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_delete_confirmation_keyboard(category_id: int) -> InlineKeyboardMarkup:
    """Keyboard for confirming category deletion."""

    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Удалить",
        callback_data=CategoryAction(action="delete", category_id=category_id).pack(),
    )
    builder.button(
        text="⬅️ Назад",
        callback_data=CategoryAction(action="open", category_id=category_id).pack(),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_cancel_keyboard() -> InlineKeyboardMarkup:
    """Keyboard with a single cancel button for interactive steps."""

    builder = InlineKeyboardBuilder()
    builder.button(
        text="Отмена",
        callback_data=CategoryAction(action="cancel").pack(),
    )
    builder.adjust(1)
    return builder.as_markup()


async def categories_overview_payload(
    user_id: int, category_service: CategoryService
) -> tuple[str, InlineKeyboardMarkup]:
    """Return rendered text and keyboard for the category list."""

    categories = await category_service.list_categories(user_id=user_id)
    text = category_service.render_categories(categories)
    markup = build_categories_keyboard(categories)
    return text, markup


async def safe_edit_message(
    message: Message, text: str, reply_markup: InlineKeyboardMarkup
) -> None:
    """Safely edit message text, ignoring "message is not modified" errors."""

    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:  # pragma: no cover - Telegram API branch
        if "message is not modified" not in str(exc).lower():
            raise


async def refresh_categories_menu(
    message: Message,
    user_id: int,
    category_service: CategoryService,
    menu_message_id: int | None = None,
) -> None:
    """Refresh the categories menu, editing an existing message if possible."""

    text, markup = await categories_overview_payload(user_id, category_service)
    if menu_message_id is None:
        await message.answer(text, reply_markup=markup)
        return

    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=menu_message_id,
            text=text,
            reply_markup=markup,
        )
    except TelegramBadRequest as exc:  # pragma: no cover - Telegram API branch
        lowered = str(exc).lower()
        if "message is not modified" in lowered:
            return
        if "message to edit not found" in lowered:
            await message.answer(text, reply_markup=markup)
            return
        raise


async def show_category_details(
    message: Message,
    category_service: CategoryService,
    category: "Category",
) -> None:
    """Display details for a single category with action buttons."""

    text = (
        f'Категория "{category.name}"\n'
        f"Месячный лимит: {category_service.format_amount(category.monthly_limit)} руб.\n\n"
        "Выберите действие:"
    )
    await safe_edit_message(
        message,
        text,
        build_category_actions_keyboard(category.id),
    )


@router.message(Command("categories"))
async def cmd_categories(
    message: Message, category_service: CategoryService, state: FSMContext
) -> None:
    """Show categories overview with interactive controls."""

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    await state.clear()
    text, markup = await categories_overview_payload(message.from_user.id, category_service)
    await message.answer(text, reply_markup=markup)


@router.callback_query(CategoryAction.filter(F.action == "list"))
async def callback_list(
    callback: CallbackQuery, category_service: CategoryService, state: FSMContext
) -> None:
    """Return to the category list from nested menus."""

    if callback.from_user is None or callback.message is None:
        await callback.answer("Не удалось определить пользователя.", show_alert=True)
        return

    await state.clear()
    text, markup = await categories_overview_payload(callback.from_user.id, category_service)
    await safe_edit_message(callback.message, text, markup)
    await callback.answer()


@router.callback_query(CategoryAction.filter(F.action == "open"))
async def callback_open(
    callback: CallbackQuery,
    callback_data: CategoryAction,
    category_service: CategoryService,
    state: FSMContext,
) -> None:
    """Display actions for the selected category."""

    if callback.from_user is None or callback.message is None:
        await callback.answer("Не удалось определить пользователя.", show_alert=True)
        return

    if callback_data.category_id is None:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    category = await category_service.get_category(
        user_id=callback.from_user.id,
        category_id=callback_data.category_id,
    )
    if category is None:
        await callback.answer("Категория не найдена", show_alert=True)
        text, markup = await categories_overview_payload(callback.from_user.id, category_service)
        await safe_edit_message(callback.message, text, markup)
        return

    await state.clear()
    await show_category_details(callback.message, category_service, category)
    await callback.answer()


@router.callback_query(CategoryAction.filter(F.action == "add"))
async def callback_add(callback: CallbackQuery, state: FSMContext) -> None:
    """Start flow for creating a new category."""

    if callback.from_user is None or callback.message is None:
        await callback.answer("Не удалось определить пользователя.", show_alert=True)
        return

    await state.set_state(CategoryStates.adding_name)
    await state.update_data(menu_message_id=callback.message.message_id)
    await callback.message.answer(
        "Введите название новой категории:",
        reply_markup=build_cancel_keyboard(),
    )
    await callback.answer()


@router.message(CategoryStates.adding_name)
async def process_add_name(message: Message, state: FSMContext) -> None:
    """Receive the category name from the user."""

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    name = (message.text or "").strip()
    if not name:
        await message.answer("Название категории не может быть пустым")
        return

    await state.update_data(pending_name=name)
    await state.set_state(CategoryStates.adding_limit)
    await message.answer(
        "Введите месячный лимит для категории:",
        reply_markup=build_cancel_keyboard(),
    )


@router.message(CategoryStates.adding_limit)
async def process_add_limit(
    message: Message, category_service: CategoryService, state: FSMContext
) -> None:
    """Receive the monthly limit and create a category."""

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    data = await state.get_data()
    name = (data.get("pending_name") or "").strip()
    menu_message_id = data.get("menu_message_id")
    if not name:
        await state.clear()
        await message.answer("Действие отменено, попробуйте снова через меню категорий.")
        return

    try:
        monthly_limit = category_service.parse_limit(message.text or "")
    except ValueError as error:
        await message.answer(str(error))
        return

    try:
        confirmation = await category_service.create_category(
            user_id=message.from_user.id,
            name=name,
            monthly_limit=monthly_limit,
        )
    except ValueError as error:
        text = str(error)
        await message.answer(text)
        if "уже существует" in text:
            await state.set_state(CategoryStates.adding_name)
            await state.update_data(
                menu_message_id=menu_message_id,
                pending_name=None,
            )
            await message.answer(
                "Введите название новой категории:",
                reply_markup=build_cancel_keyboard(),
            )
        return

    await state.clear()
    await message.answer(confirmation)
    await refresh_categories_menu(
        message,
        message.from_user.id,
        category_service,
        menu_message_id=menu_message_id,
    )


@router.callback_query(CategoryAction.filter(F.action == "limit"))
async def callback_update_limit(
    callback: CallbackQuery,
    callback_data: CategoryAction,
    category_service: CategoryService,
    state: FSMContext,
) -> None:
    """Start flow for updating category limit."""

    if callback.from_user is None or callback.message is None:
        await callback.answer("Не удалось определить пользователя.", show_alert=True)
        return

    if callback_data.category_id is None:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    category = await category_service.get_category(
        user_id=callback.from_user.id,
        category_id=callback_data.category_id,
    )
    if category is None:
        await callback.answer("Категория не найдена", show_alert=True)
        text, markup = await categories_overview_payload(callback.from_user.id, category_service)
        await safe_edit_message(callback.message, text, markup)
        return

    await state.set_state(CategoryStates.updating_limit)
    await state.update_data(
        category_id=category.id,
        menu_message_id=callback.message.message_id,
    )
    await callback.message.answer(
        f'Введите новый месячный лимит для категории "{category.name}":',
        reply_markup=build_cancel_keyboard(),
    )
    await callback.answer()


@router.message(CategoryStates.updating_limit)
async def process_limit_update(
    message: Message, category_service: CategoryService, state: FSMContext
) -> None:
    """Handle new limit input and persist the update."""

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    data = await state.get_data()
    category_id = data.get("category_id")
    menu_message_id = data.get("menu_message_id")
    if category_id is None:
        await state.clear()
        await message.answer("Действие отменено, попробуйте снова через меню категорий.")
        return

    try:
        monthly_limit = category_service.parse_limit(message.text or "")
    except ValueError as error:
        await message.answer(str(error))
        return

    try:
        confirmation = await category_service.update_category_limit(
            user_id=message.from_user.id,
            category_id=category_id,
            monthly_limit=monthly_limit,
        )
    except ValueError as error:
        if str(error) == "Категория не найдена":
            await message.answer(str(error))
            await state.clear()
            await refresh_categories_menu(
                message,
                message.from_user.id,
                category_service,
                menu_message_id=menu_message_id,
            )
            return
        await message.answer(str(error))
        return

    await state.clear()
    await message.answer(confirmation)
    await refresh_categories_menu(
        message,
        message.from_user.id,
        category_service,
        menu_message_id=menu_message_id,
    )


@router.callback_query(CategoryAction.filter(F.action == "rename"))
async def callback_rename(
    callback: CallbackQuery,
    callback_data: CategoryAction,
    category_service: CategoryService,
    state: FSMContext,
) -> None:
    """Start flow for renaming a category."""

    if callback.from_user is None or callback.message is None:
        await callback.answer("Не удалось определить пользователя.", show_alert=True)
        return

    if callback_data.category_id is None:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    category = await category_service.get_category(
        user_id=callback.from_user.id,
        category_id=callback_data.category_id,
    )
    if category is None:
        await callback.answer("Категория не найдена", show_alert=True)
        text, markup = await categories_overview_payload(callback.from_user.id, category_service)
        await safe_edit_message(callback.message, text, markup)
        return

    await state.set_state(CategoryStates.renaming)
    await state.update_data(
        category_id=category.id,
        menu_message_id=callback.message.message_id,
    )
    await callback.message.answer(
        f'Введите новое название для категории "{category.name}":',
        reply_markup=build_cancel_keyboard(),
    )
    await callback.answer()


@router.message(CategoryStates.renaming)
async def process_rename(
    message: Message, category_service: CategoryService, state: FSMContext
) -> None:
    """Handle user input for renaming a category."""

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    data = await state.get_data()
    category_id = data.get("category_id")
    menu_message_id = data.get("menu_message_id")
    if category_id is None:
        await state.clear()
        await message.answer("Действие отменено, попробуйте снова через меню категорий.")
        return

    new_name = (message.text or "").strip()
    if not new_name:
        await message.answer("Название категории не может быть пустым")
        return

    try:
        confirmation = await category_service.rename_category(
            user_id=message.from_user.id,
            category_id=category_id,
            new_name=new_name,
        )
    except ValueError as error:
        if str(error) == "Категория не найдена":
            await message.answer(str(error))
            await state.clear()
            await refresh_categories_menu(
                message,
                message.from_user.id,
                category_service,
                menu_message_id=menu_message_id,
            )
            return
        await message.answer(str(error))
        return

    await state.clear()
    await message.answer(confirmation)
    await refresh_categories_menu(
        message,
        message.from_user.id,
        category_service,
        menu_message_id=menu_message_id,
    )


@router.callback_query(CategoryAction.filter(F.action == "delete_prompt"))
async def callback_delete_prompt(
    callback: CallbackQuery,
    callback_data: CategoryAction,
    category_service: CategoryService,
) -> None:
    """Ask the user to confirm category deletion."""

    if callback.from_user is None or callback.message is None:
        await callback.answer("Не удалось определить пользователя.", show_alert=True)
        return

    if callback_data.category_id is None:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    category = await category_service.get_category(
        user_id=callback.from_user.id,
        category_id=callback_data.category_id,
    )
    if category is None:
        await callback.answer("Категория не найдена", show_alert=True)
        text, markup = await categories_overview_payload(callback.from_user.id, category_service)
        await safe_edit_message(callback.message, text, markup)
        return

    text = (
        f'Удалить категорию "{category.name}"?\n'
        "Действие нельзя отменить."
    )
    await safe_edit_message(
        callback.message,
        text,
        build_delete_confirmation_keyboard(category.id),
    )
    await callback.answer()


@router.callback_query(CategoryAction.filter(F.action == "delete"))
async def callback_delete(
    callback: CallbackQuery,
    callback_data: CategoryAction,
    category_service: CategoryService,
    state: FSMContext,
) -> None:
    """Delete the selected category after confirmation."""

    if callback.from_user is None or callback.message is None:
        await callback.answer("Не удалось определить пользователя.", show_alert=True)
        return

    if callback_data.category_id is None:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    try:
        confirmation = await category_service.delete_category(
            user_id=callback.from_user.id,
            category_id=callback_data.category_id,
        )
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        text, markup = await categories_overview_payload(callback.from_user.id, category_service)
        await safe_edit_message(callback.message, text, markup)
        return

    await state.clear()
    await callback.message.answer(confirmation)
    text, markup = await categories_overview_payload(callback.from_user.id, category_service)
    await safe_edit_message(callback.message, text, markup)
    await callback.answer()


@router.callback_query(CategoryAction.filter(F.action == "cancel"))
async def callback_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    """Abort the current interactive flow."""

    await state.clear()
    if callback.message is not None:
        await callback.message.answer("Действие отменено")
    await callback.answer()
