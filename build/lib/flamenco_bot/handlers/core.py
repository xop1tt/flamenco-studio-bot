import logging
from typing import Any

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from ..runtime.admin_access import get_admin_id
from ..keyboards.user import (
    lessons_menu_keyboard,
    main_menu_keyboard,
    purchase_menu_keyboard,
)
from ..keyboards.user.main_menu import ensure_profile
from ..keyboards.user.account import show_account
from ..keyboards.user.navigation import cancel_current_action
from ..class_catalog import format_class_schedule


logger = logging.getLogger("bot.handlers.core")
router = Router(name="core_commands")


@router.message(CommandStart())
async def start_command(
    message: Message,
    repository: Any,
    state: FSMContext,
) -> None:
    await state.clear()
    profile = await ensure_profile(message, repository)
    await message.answer(
        "¡Hola, {}! Добро пожаловать в студию фламенко.\n"
        "Здесь можно посмотреть учетную запись, выбрать свободное занятие "
        "и обратиться в поддержку.".format(profile.user_name),
        reply_markup=main_menu_keyboard(is_admin=profile.is_admin),
    )
    logger.info("Handled /start telegram_id=%s", profile.telegram_id)


@router.message(Command("help"))
async def help_command(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    await state.clear()
    await message.answer(
        "Команды:\n"
        "/start — главное меню и регистрация\n"
        "/account — учетная запись\n"
        "/lessons — занятия и запись\n"
        "/schedule — запрос актуального расписания\n"
        "/buy — запрос условий покупки занятий\n"
        "/help — эта справка\n"
        "/cancel — отменить текущий ввод\n"
        "/slots — слоты занятий (администратор)\n"
        "/support_tickets — обращения поддержки (администратор)\n"
        "/support_reply ID текст — ответить (администратор)\n"
        "/support_close ID — закрыть обращение (администратор)\n"
        "/slot_add ФОРМАТ ISO-ДАТА ВМЕСТИМОСТЬ — создать слот (администратор)\n"
        "/slot_capacity ID ЧИСЛО — изменить вместимость (администратор)\n"
        "/slot_close ID — закрыть слот (администратор)\n"
        "/admin — команды администратора\n"
        "/requests — список незакрытых заявок (администратор)\n"
        "/done ID — закрыть заявку (администратор)",
        reply_markup=main_menu_keyboard(
            is_admin=await get_admin_id(message, repository) is not None
        ),
    )
    sender = message.from_user
    logger.info("Handled /help telegram_id=%s", sender.id if sender else None)


@router.message(Command("account"))
async def account_command(
    message: Message,
    repository: Any,
    state: FSMContext,
) -> None:
    await state.clear()
    await show_account(message, repository=repository, state=state)
    logger.info(
        "Handled /account telegram_id=%s",
        message.from_user.id if message.from_user else None,
    )


@router.message(Command("lessons"))
async def lessons_command(
    message: Message,
    repository: Any,
    state: FSMContext,
) -> None:
    await state.clear()
    await ensure_profile(message, repository)
    await message.answer(
        "Занятия студии фламенко:",
        reply_markup=lessons_menu_keyboard(),
    )
    logger.info(
        "Handled /lessons telegram_id=%s",
        message.from_user.id if message.from_user else None,
    )


@router.message(Command("schedule"))
async def schedule_command(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    await state.clear()
    slots = await repository.list_class_slots(limit=50)
    await message.answer(
        format_class_schedule(slots),
        reply_markup=lessons_menu_keyboard(),
    )
    logger.info(
        "Handled /schedule telegram_id=%s",
        message.from_user.id if message.from_user else None,
    )


@router.message(Command("buy"))
async def buy_command(
    message: Message,
    repository: Any,
    state: FSMContext,
) -> None:
    await state.clear()
    await ensure_profile(message, repository)
    await message.answer(
        "Выберите пакет занятий. Итоговая сумма будет показана до перехода "
        "к оплате через ЮKassa.",
        reply_markup=purchase_menu_keyboard(),
    )
    logger.info(
        "Handled /buy telegram_id=%s",
        message.from_user.id if message.from_user else None,
    )


@router.message(Command("cancel"))
async def cancel_command(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    await cancel_current_action(message, state, repository)
    logger.info(
        "Handled /cancel telegram_id=%s",
        message.from_user.id if message.from_user else None,
    )
