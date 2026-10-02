import logging
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from ...runtime.admin_access import get_admin_id
from ...class_catalog import format_class_schedule
from . import (
    ACCOUNT_MENU,
    BACK_TO_LESSONS,
    BOOK_CLASS,
    BUY_LESSONS,
    CANCEL,
    LESSONS_MENU,
    MAIN_MENU,
    SCHEDULE,
    lessons_menu_keyboard,
    main_menu_keyboard,
    purchase_menu_keyboard,
)
from .navigation import cancel_current_action


logger = logging.getLogger("bot.handlers.menu")
router = Router(name="main_menu_keyboard")


@router.message(F.text == MAIN_MENU)
async def show_main_menu(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    await state.clear()
    sender = message.from_user
    logger.info("Showing main menu telegram_id=%s", sender.id if sender else None)
    await message.answer(
        "Главное меню студии фламенко. Выберите, что хотите сделать:",
        reply_markup=main_menu_keyboard(
            is_admin=await get_admin_id(message, repository) is not None
        ),
    )


@router.message(F.text == ACCOUNT_MENU)
async def open_account_from_menu(
    message: Message,
    state: FSMContext,
) -> None:
    sender = message.from_user
    logger.info("Opening account menu telegram_id=%s", sender.id if sender else None)
    from .account import open_account_menu

    await open_account_menu(message, state=state)


@router.message(F.text == LESSONS_MENU)
async def open_lessons_from_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    sender = message.from_user
    logger.info("Opening lessons menu telegram_id=%s", sender.id if sender else None)
    await message.answer(
        "Запись на занятия и покупка абонементов:",
        reply_markup=lessons_menu_keyboard(),
    )


@router.message(F.text == SCHEDULE)
async def show_schedule(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    await state.clear()
    sender = message.from_user
    logger.info("Schedule requested telegram_id=%s", sender.id if sender else None)
    slots = await repository.list_class_slots(limit=50)
    await message.answer(
        format_class_schedule(slots),
        reply_markup=lessons_menu_keyboard(),
    )


@router.message(F.text == BUY_LESSONS)
async def open_purchase_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    sender = message.from_user
    logger.info("Opening purchase menu telegram_id=%s", sender.id if sender else None)
    await message.answer(
        "Выберите формат занятий. Стоимость и условия абонемента подтвердит "
        "администратор до оплаты.",
        reply_markup=purchase_menu_keyboard(),
    )


@router.message(F.text == BOOK_CLASS)
async def open_class_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    from .lessons import choose_class

    await choose_class(message, state)


@router.message(F.text == CANCEL)
async def cancel_from_menu(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    await cancel_current_action(message, state, repository)


@router.message(F.text == BACK_TO_LESSONS)
async def back_to_lessons_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Запись на занятия и покупка абонементов:",
        reply_markup=lessons_menu_keyboard(),
    )


@router.message(F.text == "📚 О студии")
async def show_studio_info(message: Message, repository: Any) -> None:
    await message.answer(
        "Мы помогаем познакомиться с фламенко и развиваться в танце. "
        "Выберите уровень занятия и оставьте пожелания по времени — "
        "администратор уточнит детали и наличие мест.",
        reply_markup=main_menu_keyboard(
            is_admin=await get_admin_id(message, repository) is not None
        ),
    )


async def ensure_profile(message: Message, repository: Any) -> Any:
    sender = message.from_user
    if sender is None:
        raise ValueError("У сообщения отсутствует Telegram-пользователь")

    user_name = sender.full_name.strip() or "Участник студии"
    return await repository.get_or_create_profile(
        telegram_id=sender.id,
        user_name=user_name,
        is_admin=False,
    )
