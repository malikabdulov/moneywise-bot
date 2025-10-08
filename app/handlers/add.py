"""Handler for adding new expenses."""

from __future__ import annotations

import logging
from contextlib import suppress
from decimal import Decimal
from typing import TYPE_CHECKING

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services import CategoryService, ExpenseService

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.db.models import Category

logger = logging.getLogger(__name__)

router = Router()


class AddExpenseStates(StatesGroup):
    """Finite states for step-by-step expense creation."""

    choosing_category = State()
    entering_amount = State()
    entering_description = State()


class AddExpenseAction(CallbackData, prefix="exp"):
    """Callback data schema for the expense creation flow."""

    action: str
    category_id: int | None = None


def build_categories_keyboard(categories: list["Category"]) -> InlineKeyboardMarkup:
    """Return inline keyboard with available categories."""

    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.button(
            text=category.name,
            callback_data=AddExpenseAction(
                action="choose", category_id=category.id
            ).pack(),
        )
    builder.button(
        text="Отмена",
        callback_data=AddExpenseAction(action="cancel").pack(),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_cancel_keyboard() -> InlineKeyboardMarkup:
    """Return inline keyboard with a single cancel button."""

    builder = InlineKeyboardBuilder()
    builder.button(
        text="Отмена",
        callback_data=AddExpenseAction(action="cancel").pack(),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_description_keyboard() -> InlineKeyboardMarkup:
    """Return inline keyboard for the description stage."""

    builder = InlineKeyboardBuilder()
    builder.button(
        text="Пропустить",
        callback_data=AddExpenseAction(action="skip_description").pack(),
    )
    builder.button(
        text="Отмена",
        callback_data=AddExpenseAction(action="cancel").pack(),
    )
    builder.adjust(1)
    return builder.as_markup()


@router.message(Command("add"))
async def cmd_add(
    message: Message,
    expense_service: ExpenseService,
    category_service: CategoryService,
    state: FSMContext,
) -> None:
    """Handle the /add command and store a new expense."""

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    text = (message.text or "").strip()
    if text and text != "/add":
        try:
            confirmation = await expense_service.add_expense_from_message(
                user_id=message.from_user.id,
                message_text=message.text or "",
            )
        except ValueError as error:
            logger.warning("Failed to add expense: %s", error)
            await message.answer(str(error))
            return

        await message.answer(confirmation)
        return

    await state.clear()
    categories = await category_service.list_categories(user_id=message.from_user.id)
    if not categories:
        await message.answer(
            "Сначала создайте хотя бы одну категорию через команду /categories."
        )
        return

    await state.set_state(AddExpenseStates.choosing_category)
    await message.answer(
        "Выберите категорию для нового расхода:",
        reply_markup=build_categories_keyboard(categories),
    )


@router.callback_query(
    AddExpenseAction.filter(F.action == "choose"),
    AddExpenseStates.choosing_category,
)
async def category_chosen(
    callback: CallbackQuery,
    callback_data: AddExpenseAction,
    category_service: CategoryService,
    state: FSMContext,
) -> None:
    """Process category selection and ask for the amount."""

    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return

    category = await category_service.get_category(
        user_id=callback.from_user.id,
        category_id=callback_data.category_id or 0,
    )
    if category is None:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    await state.update_data(
        category_id=category.id,
        category_name=category.name,
    )
    await state.set_state(AddExpenseStates.entering_amount)
    await callback.message.edit_text(
        (
            f'Категория "{category.name}" выбрана.\n'
            "Введите сумму расхода:"
        ),
        reply_markup=build_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AddExpenseStates.choosing_category)
async def awaiting_category_selection(message: Message) -> None:
    """Prompt the user to use buttons while waiting for a category selection."""

    await message.answer("Выберите категорию с помощью кнопок ниже или нажмите «Отмена».")


@router.message(AddExpenseStates.entering_amount)
async def amount_received(
    message: Message,
    state: FSMContext,
    expense_service: ExpenseService,
) -> None:
    """Handle amount input from the user."""

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    try:
        amount = expense_service.parse_amount(message.text or "")
    except ValueError as error:
        await message.answer(str(error))
        return

    await state.update_data(amount=str(amount))
    await state.set_state(AddExpenseStates.entering_description)

    await message.answer(
        "Добавьте комментарий к расходу или нажмите «Пропустить».",
        reply_markup=build_description_keyboard(),
    )


async def finalize_expense(
    *,
    user_id: int,
    state: FSMContext,
    expense_service: ExpenseService,
    description: str | None,
) -> str:
    """Persist the expense using data from the state and return confirmation text."""

    data = await state.get_data()
    if "category_name" not in data or "amount" not in data:
        await state.clear()
        raise ValueError("Не удалось завершить добавление расхода. Попробуйте ещё раз.")

    category_name = str(data["category_name"])
    amount = Decimal(str(data["amount"]))
    confirmation = await expense_service.add_expense(
        user_id=user_id,
        amount=amount,
        category=category_name,
        description=description,
    )
    await state.clear()
    return confirmation


@router.message(AddExpenseStates.entering_description)
async def description_received(
    message: Message,
    state: FSMContext,
    expense_service: ExpenseService,
) -> None:
    """Persist the expense when the user sends a description."""

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    description = (message.text or "").strip() or None

    try:
        confirmation = await finalize_expense(
            user_id=message.from_user.id,
            state=state,
            expense_service=expense_service,
            description=description,
        )
    except ValueError as error:
        await message.answer(str(error))
        return

    await message.answer(confirmation)


@router.callback_query(
    AddExpenseAction.filter(F.action == "skip_description"),
    AddExpenseStates.entering_description,
)
async def skip_description(
    callback: CallbackQuery,
    state: FSMContext,
    expense_service: ExpenseService,
) -> None:
    """Persist the expense without a description."""

    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return

    try:
        confirmation = await finalize_expense(
            user_id=callback.from_user.id,
            state=state,
            expense_service=expense_service,
            description=None,
        )
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return

    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup()
    await callback.message.answer(confirmation)
    await callback.answer("Комментарий не добавлен")


@router.callback_query(AddExpenseAction.filter(F.action == "cancel"))
async def cancel_addition(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel the expense creation flow."""

    await state.clear()

    if callback.message is not None:
        with suppress(TelegramBadRequest):
            await callback.message.edit_text("Добавление расхода отменено.")

    await callback.answer()
