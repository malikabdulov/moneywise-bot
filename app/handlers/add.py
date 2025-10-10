"""Handler for adding new expenses."""

from __future__ import annotations

import datetime as dt
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
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services import CategoryService, ExpenseService

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.db.models import Category

logger = logging.getLogger(__name__)

router = Router()


ADD_MORE_PROMPT = "➕ Добавить еще"
SUCCESS_PREFIX = "✅ Расход добавлен!"
SMART_INPUT_FALLBACK = (
    "Не понял сообщение 🤔 Пример: \"такси 2500\" или \"2500 продукты\""
)


def build_success_keyboard() -> InlineKeyboardMarkup:
    """Return inline keyboard suggesting to add another expense."""

    builder = InlineKeyboardBuilder()
    builder.button(
        text=ADD_MORE_PROMPT,
        callback_data=AddExpenseAction(action="restart").pack(),
    )
    builder.adjust(1)
    return builder.as_markup()


def render_success_message(confirmation: str) -> str:
    """Return confirmation text prefixed with a friendly status line."""

    confirmation = confirmation.strip()
    if confirmation:
        return f"{SUCCESS_PREFIX}\n\n{confirmation}"
    return SUCCESS_PREFIX


class AddExpenseStates(StatesGroup):
    """Finite states for step-by-step expense creation."""

    choosing_category = State()
    choosing_date = State()
    entering_amount = State()
    entering_description = State()


class AddExpenseAction(CallbackData, prefix="exp"):
    """Callback data schema for the expense creation flow."""

    action: str
    category_id: int | None = None
    date: str | None = None


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


def build_date_keyboard(now: dt.datetime | None = None) -> InlineKeyboardMarkup:
    """Return inline keyboard for picking the expense date."""

    now = now or dt.datetime.now()
    today = now.date()
    options = [
        ("Сегодня", today),
        ("Вчера", today - dt.timedelta(days=1)),
        ("Позавчера", today - dt.timedelta(days=2)),
    ]

    builder = InlineKeyboardBuilder()
    for text, date in options:
        builder.button(
            text=f"{text} ({_format_date(date)})",
            callback_data=AddExpenseAction(action="date", date=date.isoformat()).pack(),
        )
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


async def start_add_expense_flow(
    message: Message,
    *,
    user_id: int,
    category_service: CategoryService,
    state: FSMContext,
) -> None:
    """Start the multi-step expense creation flow."""

    await state.clear()
    categories = await category_service.list_categories(user_id=user_id)
    if not categories:
        await message.answer(
            "Сначала создайте хотя бы одну категорию через команду /categories.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await state.set_state(AddExpenseStates.choosing_category)
    await message.answer(
        "Выберите категорию для нового расхода:",
        reply_markup=build_categories_keyboard(categories),
    )


@router.message(F.text)
async def smart_expense_input(
    message: Message,
    state: FSMContext,
    expense_service: ExpenseService,
    category_service: CategoryService,
) -> None:
    """Handle free-form expense input when no FSM state is active."""

    if message.from_user is None:
        return

    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return

    current_state = await state.get_state()
    if current_state is not None:
        return

    categories = await category_service.list_categories(user_id=message.from_user.id)
    parsed = expense_service.parse_smart_message(text, categories)

    if (
        parsed.category is None
        and parsed.spent_at is None
        and parsed.amount is None
    ):
        await message.answer(SMART_INPUT_FALLBACK)
        return

    if not categories:
        await state.clear()
        await message.answer(
            "Сначала создайте хотя бы одну категорию через команду /categories.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await state.clear()
    data: dict[str, object] = {}
    if parsed.category is not None:
        data["category_id"] = parsed.category.id
        data["category_name"] = parsed.category.name
    if parsed.spent_at is not None:
        data["spent_at"] = parsed.spent_at.isoformat()
    if parsed.amount is not None:
        data["amount"] = str(parsed.amount)
    if (
        parsed.description
        and not (
            parsed.category is not None
            and parsed.spent_at is not None
            and parsed.amount is not None
        )
    ):
        data["prefilled_description"] = parsed.description
    if data:
        await state.update_data(**data)

    if parsed.category is None:
        await state.set_state(AddExpenseStates.choosing_category)
        await message.answer(
            "Выберите категорию для нового расхода:",
            reply_markup=build_categories_keyboard(categories),
        )
        return

    if parsed.spent_at is None:
        await state.set_state(AddExpenseStates.choosing_date)
        await message.answer(
            (
                f'Категория "{parsed.category.name}" выбрана.\n'
                "Выберите дату расхода с помощью кнопок ниже "
                "или отправьте дату сообщением в формате ДД.ММ.ГГГГ "
                "(например, 05.09.2024)."
            ),
            reply_markup=build_date_keyboard(),
        )
        return

    date_value = parsed.spent_at.date()
    if parsed.amount is None:
        await state.set_state(AddExpenseStates.entering_amount)
        await message.answer(
            (
                f'Категория "{parsed.category.name}" выбрана.\n'
                f"Дата расхода: {_format_date(date_value)}.\n"
                "Введите сумму расхода:"
            ),
            reply_markup=build_cancel_keyboard(),
        )
        return

    await state.set_state(AddExpenseStates.entering_description)
    if parsed.description is not None:
        try:
            confirmation = await finalize_expense(
                user_id=message.from_user.id,
                state=state,
                expense_service=expense_service,
                description=parsed.description,
            )
        except ValueError as error:
            await message.answer(str(error))
            return

        await message.answer(
            render_success_message(confirmation),
            reply_markup=build_success_keyboard(),
        )
        return

    await message.answer(
        _render_description_prompt(parsed.category.name, date_value),
        reply_markup=build_description_keyboard(),
    )


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

        await message.answer(
            render_success_message(confirmation),
            reply_markup=build_success_keyboard(),
        )
        return

    await start_add_expense_flow(
        message,
        user_id=message.from_user.id,
        category_service=category_service,
        state=state,
    )


@router.callback_query(
    AddExpenseAction.filter(F.action == "choose"),
    AddExpenseStates.choosing_category,
)
async def category_chosen(
    callback: CallbackQuery,
    callback_data: AddExpenseAction,
    category_service: CategoryService,
    expense_service: ExpenseService,
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
    data = await state.get_data()
    spent_at = _parse_spent_at_date(data.get("spent_at"))
    amount = data.get("amount")
    prefilled_raw = data.get("prefilled_description")
    prefilled_description = (
        prefilled_raw.strip()
        if isinstance(prefilled_raw, str) and prefilled_raw.strip()
        else None
    )

    if spent_at is not None:
        if amount:
            await state.set_state(AddExpenseStates.entering_description)
            if prefilled_description:
                try:
                    confirmation = await finalize_expense(
                        user_id=callback.from_user.id,
                        state=state,
                        expense_service=expense_service,
                        description=prefilled_description,
                    )
                except ValueError as error:
                    await callback.answer(str(error), show_alert=True)
                    return

                with suppress(TelegramBadRequest):
                    await callback.message.edit_reply_markup()
                await callback.message.answer(
                    render_success_message(confirmation),
                    reply_markup=build_success_keyboard(),
                )
                await callback.answer()
                return

            await callback.message.edit_text(
                _render_description_prompt(category.name, spent_at),
                reply_markup=build_description_keyboard(),
            )
            await callback.answer()
            return

        await state.set_state(AddExpenseStates.entering_amount)
        await callback.message.edit_text(
            (
                f'Категория "{category.name}" выбрана.\n'
                f"Дата расхода: {_format_date(spent_at)}.\n"
                "Введите сумму расхода:"
            ),
            reply_markup=build_cancel_keyboard(),
        )
        await callback.answer()
        return

    await state.set_state(AddExpenseStates.choosing_date)
    await callback.message.edit_text(
        (
            f'Категория "{category.name}" выбрана.\n'
            "Выберите дату расхода с помощью кнопок ниже "
            "или отправьте дату сообщением в формате ДД.ММ.ГГГГ "
            "(например, 05.09.2024)."
        ),
        reply_markup=build_date_keyboard(),
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
    data = await state.get_data()
    prefilled_raw = data.get("prefilled_description")
    prefilled_description = (
        prefilled_raw.strip()
        if isinstance(prefilled_raw, str) and prefilled_raw.strip()
        else None
    )

    if prefilled_description:
        try:
            confirmation = await finalize_expense(
                user_id=message.from_user.id,
                state=state,
                expense_service=expense_service,
                description=prefilled_description,
            )
        except ValueError as error:
            await message.answer(str(error))
            return

        await message.answer(
            render_success_message(confirmation),
            reply_markup=build_success_keyboard(),
        )
        return

    category_name = str(data.get("category_name", ""))
    spent_at = _parse_spent_at_date(data.get("spent_at"))

    await message.answer(
        _render_description_prompt(category_name, spent_at),
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
    required_keys = {"category_id", "category_name", "amount", "spent_at"}
    if not required_keys.issubset(data):
        await state.clear()
        raise ValueError("Не удалось завершить добавление расхода. Попробуйте ещё раз.")

    category_id = int(data["category_id"])
    category_name = str(data["category_name"])
    amount = Decimal(str(data["amount"]))
    try:
        spent_at = dt.datetime.fromisoformat(str(data["spent_at"]))
    except ValueError as exc:
        await state.clear()
        raise ValueError(
            "Не удалось обработать дату расхода. Попробуйте добавить расход заново."
        ) from exc
    confirmation = await expense_service.add_expense(
        user_id=user_id,
        amount=amount,
        category=category_name,
        category_id=category_id,
        description=description,
        spent_at=spent_at,
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

    await message.answer(
        render_success_message(confirmation),
        reply_markup=build_success_keyboard(),
    )


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
    await callback.message.answer(
        render_success_message(confirmation),
        reply_markup=build_success_keyboard(),
    )
    await callback.answer("Комментарий не добавлен")


@router.callback_query(AddExpenseAction.filter(F.action == "restart"))
async def add_more_requested(
    callback: CallbackQuery,
    category_service: CategoryService,
    state: FSMContext,
) -> None:
    """Restart the expense creation flow when the user taps the quick button."""

    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return

    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup()

    await start_add_expense_flow(
        callback.message,
        user_id=callback.from_user.id,
        category_service=category_service,
        state=state,
    )
    await callback.answer()


@router.callback_query(AddExpenseAction.filter(F.action == "cancel"))
async def cancel_addition(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel the expense creation flow."""

    await state.clear()

    if callback.message is not None:
        with suppress(TelegramBadRequest):
            await callback.message.edit_text("Добавление расхода отменено.")

    await callback.answer()


def _combine_with_current_time(date_value: dt.date) -> dt.datetime:
    """Return datetime using the provided date and current local time."""

    now = dt.datetime.now()
    return now.replace(year=date_value.year, month=date_value.month, day=date_value.day)


def _format_date(date_value: dt.date) -> str:
    """Return formatted date for user messages."""

    return date_value.strftime("%d.%m.%Y")


def _parse_spent_at_date(value: str | None) -> dt.date | None:
    """Return date extracted from ISO formatted datetime string."""

    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _render_description_prompt(
    category_name: str,
    date_value: dt.date | None,
) -> str:
    """Return text prompting the user to provide an optional description."""

    lines: list[str] = []
    if category_name:
        lines.append(f'Категория "{category_name}" выбрана.')
    if date_value is not None:
        lines.append(f"Дата расхода: {_format_date(date_value)}.")
    lines.append("Добавьте комментарий к расходу или нажмите «Пропустить».")
    return "\n".join(lines)


DATE_INPUT_HINT = (
    "Введите дату в формате ДД.ММ.ГГГГ (например, 05.09.2024) "
    "или воспользуйтесь кнопками ниже."
)


@router.callback_query(
    AddExpenseAction.filter(F.action == "date"),
    AddExpenseStates.choosing_date,
)
async def date_selected(
    callback: CallbackQuery,
    callback_data: AddExpenseAction,
    expense_service: ExpenseService,
    state: FSMContext,
) -> None:
    """Process date selection and ask for the amount."""

    if callback.message is None:
        await callback.answer()
        return

    try:
        date_value = dt.date.fromisoformat(callback_data.date or "")
    except ValueError:
        await callback.answer("Не удалось определить дату", show_alert=True)
        return

    today = dt.date.today()
    if date_value > today:
        await callback.answer("Нельзя выбирать дату из будущего", show_alert=True)
        return

    data = await state.get_data()
    category_name = str(data.get("category_name", ""))
    spent_at = _combine_with_current_time(date_value).isoformat()
    await state.update_data(spent_at=spent_at)

    updated = await state.get_data()
    amount = updated.get("amount")
    prefilled_raw = updated.get("prefilled_description")
    prefilled_description = (
        prefilled_raw.strip()
        if isinstance(prefilled_raw, str) and prefilled_raw.strip()
        else None
    )

    if amount:
        await state.set_state(AddExpenseStates.entering_description)
        if prefilled_description:
            try:
                confirmation = await finalize_expense(
                    user_id=callback.from_user.id,
                    state=state,
                    expense_service=expense_service,
                    description=prefilled_description,
                )
            except ValueError as error:
                await callback.answer(str(error), show_alert=True)
                return

            with suppress(TelegramBadRequest):
                await callback.message.edit_reply_markup()
            await callback.message.answer(
                render_success_message(confirmation),
                reply_markup=build_success_keyboard(),
            )
            await callback.answer()
            return

        await callback.message.edit_text(
            _render_description_prompt(category_name, date_value),
            reply_markup=build_description_keyboard(),
        )
        await callback.answer()
        return

    await state.set_state(AddExpenseStates.entering_amount)

    message_text = "Введите сумму расхода:"
    if category_name:
        message_text = (
            f'Категория "{category_name}" выбрана.\n'
            f"Дата расхода: {_format_date(date_value)}.\n"
            f"{message_text}"
        )

    await callback.message.edit_text(
        message_text,
        reply_markup=build_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AddExpenseStates.choosing_date)
async def manual_date_entered(
    message: Message,
    state: FSMContext,
    expense_service: ExpenseService,
) -> None:
    """Allow the user to type a custom date for the expense."""

    text = (message.text or "").strip()
    if not text:
        await message.answer(DATE_INPUT_HINT)
        return

    try:
        date_value = dt.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer(
            "Не удалось распознать дату. "
            "Используйте формат ДД.ММ.ГГГГ, например 05.09.2024."
        )
        return

    today = dt.date.today()
    if date_value > today:
        await message.answer(
            "Нельзя выбрать дату из будущего. Попробуйте указать другую дату."
        )
        return

    data = await state.get_data()
    category_name = str(data.get("category_name", ""))

    spent_at = _combine_with_current_time(date_value).isoformat()
    await state.update_data(spent_at=spent_at)

    updated = await state.get_data()
    amount = updated.get("amount")
    prefilled_raw = updated.get("prefilled_description")
    prefilled_description = (
        prefilled_raw.strip()
        if isinstance(prefilled_raw, str) and prefilled_raw.strip()
        else None
    )

    if amount:
        await state.set_state(AddExpenseStates.entering_description)
        if prefilled_description:
            try:
                confirmation = await finalize_expense(
                    user_id=message.from_user.id,
                    state=state,
                    expense_service=expense_service,
                    description=prefilled_description,
                )
            except ValueError as error:
                await message.answer(str(error))
                return

            await message.answer(
                render_success_message(confirmation),
                reply_markup=build_success_keyboard(),
            )
            return

        await message.answer(
            _render_description_prompt(category_name, date_value),
            reply_markup=build_description_keyboard(),
        )
        return

    await state.set_state(AddExpenseStates.entering_amount)

    prompt = (
        f'Категория "{category_name}" выбрана.\n'
        f"Дата расхода: {_format_date(date_value)}.\n"
        "Введите сумму расхода:"
    )
    await message.answer(prompt, reply_markup=build_cancel_keyboard())

