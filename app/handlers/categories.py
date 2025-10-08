"""Handlers for managing expense categories."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.services import CategoryService

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("categories"))
async def cmd_categories(message: Message, category_service: CategoryService) -> None:
    """Send a list of existing categories to the user."""

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    response = await category_service.list_categories_message(user_id=message.from_user.id)
    await message.answer(response)


@router.message(Command("category_add"))
async def cmd_category_add(message: Message, category_service: CategoryService) -> None:
    """Handle creation of a new category."""

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    try:
        confirmation = await category_service.add_category_from_message(
            user_id=message.from_user.id,
            message_text=message.text or "",
        )
    except ValueError as error:
        logger.warning("Failed to add category: %s", error)
        await message.answer(str(error))
        return

    await message.answer(confirmation)


@router.message(Command("category_limit"))
async def cmd_category_limit(message: Message, category_service: CategoryService) -> None:
    """Handle updates of category monthly limits."""

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    try:
        confirmation = await category_service.update_limit_from_message(
            user_id=message.from_user.id,
            message_text=message.text or "",
        )
    except ValueError as error:
        logger.warning("Failed to update category limit: %s", error)
        await message.answer(str(error))
        return

    await message.answer(confirmation)


@router.message(Command("category_rename"))
async def cmd_category_rename(message: Message, category_service: CategoryService) -> None:
    """Handle renaming of existing categories."""

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    try:
        confirmation = await category_service.rename_category_from_message(
            user_id=message.from_user.id,
            message_text=message.text or "",
        )
    except ValueError as error:
        logger.warning("Failed to rename category: %s", error)
        await message.answer(str(error))
        return

    await message.answer(confirmation)


@router.message(Command("category_delete"))
async def cmd_category_delete(message: Message, category_service: CategoryService) -> None:
    """Handle deletion of categories."""

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    try:
        confirmation = await category_service.delete_category_from_message(
            user_id=message.from_user.id,
            message_text=message.text or "",
        )
    except ValueError as error:
        logger.warning("Failed to delete category: %s", error)
        await message.answer(str(error))
        return

    await message.answer(confirmation)
