"""Handlers for free-form expense input."""

from __future__ import annotations

from contextlib import suppress
from decimal import Decimal

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.services import CategoryService, ExpenseService
from app.services.expenses_parser import parse_expense_text

from .common import (
    build_all_categories_keyboard,
    build_category_shortcuts_keyboard,
    build_comment_choice_keyboard,
)

router = Router()

AMOUNT_PROMPT = "💰 Сколько потратил? (₸)"
COMMENT_PROMPT = "📝 Добавить комментарий?"
CATEGORY_PROMPT = "📂 Куда отнести {amount} ₸?"
CATEGORY_LIST_PROMPT = "📂 Выбери категорию"
ERROR_TEXT = "Не понял сообщение 🤔\nПример: 'еда 2500' или '2500 куликов'"
NO_CATEGORIES_TEXT = "⚠️ Сначала создай категорию через /categories"
UNKNOWN_CATEGORY_TEXT = "⚠️ Категория \"{name}\" не найдена. Выбери из списка"
COMMENT_INPUT_PROMPT = "✏️ Введите комментарий"
SAVE_ERROR_TEXT = "⚠️ Не удалось сохранить расход. Попробуй снова"
BUTTON_SKIP_TEXT = "Комментарий пропущен"


class ExpenseInputStates(StatesGroup):
    """Finite states for the expense input flow."""

    IDLE = State()
    WAIT_AMOUNT = State()
    WAIT_CATEGORY = State()
    INLINE_CHOICE_DESCRIPTION = State()
    WAIT_DESCRIPTION = State()


class CommentAction(CallbackData, prefix="exp_comment"):
    """Callback data schema for comment selection."""

    action: str


class CategoryAction(CallbackData, prefix="exp_category"):
    """Callback data schema for category selection."""

    action: str
    category_id: int | None = None


@router.message(Command("add"))
async def explain_add_usage(message: Message, state: FSMContext) -> None:
    """Tell the user how to add expenses without commands."""

    await _reset_to_idle(state)
    await message.answer("Напиши расход, например: 'еда 2500'.")


@router.message(StateFilter(ExpenseInputStates.IDLE, None), F.text)
async def handle_free_form_message(
    message: Message,
    state: FSMContext,
    category_service: CategoryService,
    expense_service: ExpenseService,
) -> None:
    """Parse a free-form message and route it to the proper scenario."""

    if message.text is None or message.text.startswith("/"):
        return
    if message.from_user is None:
        return

    if await state.get_state() is None:
        await state.set_state(ExpenseInputStates.IDLE)

    parsed = parse_expense_text(message.text)
    amount = parsed.get("amount")
    category_text = parsed.get("category")
    description = parsed.get("description")

    if amount is not None and category_text:
        category = await category_service.find_category_by_name(
            user_id=message.from_user.id,
            name=category_text,
        )
        if category is None:
            await state.update_data(amount=amount, description=description)
            await _ask_for_category(
                message,
                state=state,
                expense_service=expense_service,
                category_service=category_service,
                amount=amount,
                notify_unknown=category_text,
            )
            return

        await state.update_data(
            amount=amount,
            category_id=category.id,
            category_name=category.name,
            description=description,
        )
        await _ask_for_comment(message, state)
        return

    if category_text and amount is None:
        category = await category_service.find_category_by_name(
            user_id=message.from_user.id,
            name=category_text,
        )
        if category is None:
            await message.answer(UNKNOWN_CATEGORY_TEXT.format(name=category_text))
            await _reset_to_idle(state)
            return

        await state.update_data(
            category_id=category.id,
            category_name=category.name,
        )
        await state.set_state(ExpenseInputStates.WAIT_AMOUNT)
        await message.answer(AMOUNT_PROMPT)
        return

    if amount is not None:
        await state.update_data(amount=amount, description=description)
        await _ask_for_category(
            message,
            state=state,
            expense_service=expense_service,
            category_service=category_service,
            amount=amount,
            notify_unknown=None,
        )
        return

    await message.answer(ERROR_TEXT)
    await _reset_to_idle(state)


@router.message(ExpenseInputStates.WAIT_AMOUNT, F.text)
async def amount_received(
    message: Message,
    state: FSMContext,
) -> None:
    """Handle amount input when the bot is waiting for it."""

    parsed = parse_expense_text(message.text or "")
    amount = parsed.get("amount")
    if amount is None:
        await message.answer(AMOUNT_PROMPT)
        return

    await state.update_data(amount=amount, description=parsed.get("description"))
    await _ask_for_comment(message, state)


@router.message(ExpenseInputStates.WAIT_CATEGORY)
async def category_expected(message: Message) -> None:
    """Remind the user to choose a category from the inline keyboard."""

    await message.answer("⚠️ Выбери категорию кнопками ниже")


@router.message(ExpenseInputStates.INLINE_CHOICE_DESCRIPTION)
async def comment_choice_expected(message: Message) -> None:
    """Remind the user to use inline buttons for the comment step."""

    await message.answer("⚠️ Выбери вариант на клавиатуре")


@router.callback_query(CategoryAction.filter(), ExpenseInputStates.WAIT_CATEGORY)
async def category_chosen(
    callback: CallbackQuery,
    callback_data: CategoryAction,
    state: FSMContext,
    category_service: CategoryService,
) -> None:
    """Process category selection callbacks."""

    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return

    if callback_data.action == "all":
        categories = await category_service.list_categories(
            user_id=callback.from_user.id
        )
        if not categories:
            await callback.answer("Категорий нет", show_alert=True)
            return
        keyboard = build_all_categories_keyboard(
            categories,
            encode=lambda item: CategoryAction(action="pick", category_id=item.id).pack(),
        )
        try:
            await callback.message.edit_reply_markup(reply_markup=keyboard)
        except TelegramBadRequest:
            await callback.message.answer(
                callback.message.text or CATEGORY_LIST_PROMPT,
                reply_markup=keyboard,
            )
        await callback.answer()
        return

    if callback_data.category_id is None:
        await callback.answer()
        return

    category = await category_service.get_category(
        user_id=callback.from_user.id,
        category_id=callback_data.category_id,
    )
    if category is None:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    await state.update_data(
        category_id=category.id,
        category_name=category.name,
    )

    await callback.answer()
    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup()
    await _ask_for_comment(callback.message, state)


@router.callback_query(
    CommentAction.filter(F.action == "enter"),
    ExpenseInputStates.INLINE_CHOICE_DESCRIPTION,
)
async def comment_requested(callback: CallbackQuery, state: FSMContext) -> None:
    """Switch to comment input when the user wants to add it."""

    if callback.message is None:
        await callback.answer()
        return

    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup()
    await state.set_state(ExpenseInputStates.WAIT_DESCRIPTION)
    await callback.message.answer(COMMENT_INPUT_PROMPT)
    await callback.answer()


@router.callback_query(
    CommentAction.filter(F.action == "skip"),
    ExpenseInputStates.INLINE_CHOICE_DESCRIPTION,
)
async def comment_skipped(
    callback: CallbackQuery,
    state: FSMContext,
    expense_service: ExpenseService,
) -> None:
    """Persist expense when the user skips adding a comment."""

    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return

    data = await state.get_data()
    description = data.get("description")
    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup()
    await _save_expense(
        message=callback.message,
        state=state,
        expense_service=expense_service,
        user_id=callback.from_user.id,
        description=description if description else None,
    )
    await callback.answer(BUTTON_SKIP_TEXT)


@router.message(ExpenseInputStates.WAIT_DESCRIPTION, F.text)
async def comment_received(
    message: Message,
    state: FSMContext,
    expense_service: ExpenseService,
) -> None:
    """Persist expense when the user provides a comment."""

    if message.from_user is None:
        return

    description = (message.text or "").strip() or None
    await _save_expense(
        message=message,
        state=state,
        expense_service=expense_service,
        user_id=message.from_user.id,
        description=description,
    )


def _render_confirmation(amount: int, category: str, description: str | None) -> str:
    """Return confirmation text for a stored expense."""

    header = f"✅ {amount} ₸ — {category}"
    if description:
        return f"{header}\n{description}"
    return header


async def _ask_for_comment(message: Message, state: FSMContext) -> None:
    """Prompt the user to enter or skip a comment."""

    await state.set_state(ExpenseInputStates.INLINE_CHOICE_DESCRIPTION)
    keyboard = build_comment_choice_keyboard(
        enter_data=CommentAction(action="enter").pack(),
        skip_data=CommentAction(action="skip").pack(),
    )
    await message.answer(COMMENT_PROMPT, reply_markup=keyboard)


async def _ask_for_category(
    message: Message,
    *,
    state: FSMContext,
    expense_service: ExpenseService,
    category_service: CategoryService,
    amount: int,
    notify_unknown: str | None,
) -> None:
    """Prompt the user to choose a category for the expense."""

    if message.from_user is None:
        return

    categories = await category_service.list_categories(user_id=message.from_user.id)
    if not categories:
        await message.answer(NO_CATEGORIES_TEXT)
        await _reset_to_idle(state)
        return

    recent = await expense_service.list_recent_categories(
        user_id=message.from_user.id,
        limit=3,
    )
    if not recent:
        recent = categories[:3]

    keyboard = build_category_shortcuts_keyboard(
        recent,
        encode=lambda item: CategoryAction(action="pick", category_id=item.id).pack(),
        all_categories_data=CategoryAction(action="all").pack(),
    )

    if notify_unknown:
        await message.answer(UNKNOWN_CATEGORY_TEXT.format(name=notify_unknown))

    await state.set_state(ExpenseInputStates.WAIT_CATEGORY)
    await message.answer(CATEGORY_PROMPT.format(amount=amount), reply_markup=keyboard)


async def _save_expense(
    *,
    message: Message,
    state: FSMContext,
    expense_service: ExpenseService,
    user_id: int,
    description: str | None,
) -> None:
    """Persist expense data gathered in the state and send confirmation."""

    data = await state.get_data()
    amount = data.get("amount")
    category_id = data.get("category_id")
    category_name = data.get("category_name")

    if amount is None or category_id is None or category_name is None:
        await message.answer(SAVE_ERROR_TEXT)
        await _reset_to_idle(state)
        return

    base_description = data.get("description")
    final_description = description if description is not None else base_description

    await expense_service.add_expense(
        user_id=user_id,
        amount=Decimal(str(amount)),
        category_id=int(category_id),
        description=final_description,
    )

    await message.answer(
        _render_confirmation(amount=int(amount), category=category_name, description=final_description)
    )
    await _reset_to_idle(state)


async def _reset_to_idle(state: FSMContext) -> None:
    """Clear state data and mark the flow as idle."""

    await state.clear()
    await state.set_state(ExpenseInputStates.IDLE)
