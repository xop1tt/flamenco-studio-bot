import logging
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from ..keyboards.common import MAIN_MENU
from ..keyboards.user import CONTACT_SUPPORT, cancel_keyboard, main_menu_keyboard
from ..runtime.admin_access import get_admin_id
from ..runtime.security import SupportRateLimiter
from .states import SupportForm


logger = logging.getLogger("bot.handlers.support")
router = Router(name="support")


@router.message(F.text == CONTACT_SUPPORT)
async def start_support(
    message: Message,
    state: FSMContext,
) -> None:
    await state.set_state(SupportForm.waiting_for_message)
    await message.answer(
        "Опишите вопрос одним сообщением (до 2000 символов). "
        "Обращение увидят только администраторы студии.",
        reply_markup=cancel_keyboard(),
    )


@router.message(SupportForm.waiting_for_message, F.text == MAIN_MENU)
async def leave_support(message: Message, state: FSMContext, repository: Any) -> None:
    await state.clear()
    await message.answer(
        "Главное меню студии фламенко.",
        reply_markup=main_menu_keyboard(
            is_admin=await get_admin_id(message, repository) is not None
        ),
    )


@router.message(SupportForm.waiting_for_message, F.text, ~F.text.startswith("/"))
async def submit_support_message(
    message: Message,
    state: FSMContext,
    repository: Any,
    support_limiter: SupportRateLimiter,
) -> None:
    sender = message.from_user
    if sender is None:
        raise ValueError("У сообщения отсутствует Telegram-пользователь")
    bot = message.bot
    if bot is None:
        raise RuntimeError("Telegram bot is unavailable while saving support")
    body = (message.text or "").strip()
    if not body or len(body) > 2000:
        await message.answer("Сообщение должно содержать от 1 до 2000 символов.")
        return
    if not support_limiter.allow(sender.id):
        logger.warning("Support rate limit exceeded telegram_id=%s", sender.id)
        await message.answer(
            "Слишком много сообщений. Попробуйте отправить обращение через "
            "несколько минут."
        )
        return

    await repository.get_or_create_profile(
        telegram_id=sender.id,
        user_name=sender.full_name.strip() or "Участник студии",
        is_admin=False,
    )
    ticket_id, created = await repository.create_support_message(sender.id, body)
    delivered = 0
    recipients = await repository.list_admin_ids()
    for admin_id in recipients:
        try:
            await bot.send_message(
                admin_id,
                "Обращение №{} от {} ({}):\n{}".format(
                    ticket_id,
                    sender.full_name,
                    sender.id,
                    body,
                ),
            )
            delivered += 1
        except TelegramAPIError as error:
            logger.warning(
                "Support notification failed ticket_id=%s admin_id=%s error_type=%s",
                ticket_id,
                admin_id,
                type(error).__name__,
            )

    notifications_available = bool(recipients) and delivered == len(recipients)
    if not notifications_available:
        logger.error(
            "Support ticket saved without notifying all admins ticket_id=%s "
            "recipients=%s delivered=%s",
            ticket_id,
            len(recipients),
            delivered,
        )
    await state.clear()
    is_admin = await get_admin_id(message, repository) is not None
    if not recipients:
        confirmation = (
            "Обращение №{} сохранено, но администраторы пока не настроены."
        ).format(ticket_id)
    elif not notifications_available:
        confirmation = (
            "Обращение №{} сохранено, но уведомить администратора не удалось. "
            "Администраторы проверят его в панели поддержки."
        ).format(ticket_id)
    else:
        confirmation = (
            "Обращение №{} сохранено. Администратор ответит вам здесь."
        ).format(ticket_id)
    await message.answer(
        confirmation,
        reply_markup=main_menu_keyboard(is_admin=is_admin),
    )
    logger.info(
        "Support message saved ticket_id=%s telegram_id=%s new_ticket=%s "
        "admin_notifications=%s",
        ticket_id,
        sender.id,
        created,
        delivered,
    )


@router.message(SupportForm.waiting_for_message, ~F.text)
async def reject_non_text_support_message(message: Message) -> None:
    await message.answer("Пожалуйста, отправьте обращение обычным текстом.")


@router.message(Command("support_tickets"))
async def list_support_tickets(message: Message, repository: Any) -> None:
    admin_id = await get_admin_id(message, repository)
    if admin_id is None:
        await message.answer("Команда доступна только администратору студии.")
        return
    tickets = await repository.list_open_support_tickets(limit=20)
    if not tickets:
        await message.answer("Открытых обращений нет.")
        return
    lines = ["Открытые обращения:"]
    for ticket in tickets:
        excerpt = ticket.last_message.replace("\n", " ")[:160]
        lines.append(
            "№{} | пользователь {} | {}".format(
                ticket.id,
                ticket.telegram_id,
                excerpt or "сообщение ещё не загружено",
            )
        )
    await message.answer("\n".join(lines))


@router.message(Command("support_reply"))
async def reply_to_support_ticket(message: Message, repository: Any) -> None:
    admin_id = await get_admin_id(message, repository)
    if admin_id is None:
        await message.answer("Команда доступна только администратору студии.")
        return
    bot = message.bot
    if bot is None:
        raise RuntimeError("Telegram bot is unavailable while replying to support")
    command_text = message.text or ""
    parts = command_text.split(maxsplit=2)
    if len(parts) != 3 or not parts[1].isdigit():
        await message.answer("Формат: /support_reply ID текст ответа")
        return
    ticket_id = int(parts[1])
    body = parts[2].strip()
    if not body or len(body) > 2000:
        await message.answer("Ответ должен содержать от 1 до 2000 символов.")
        return
    user_id = await repository.reply_support_ticket(ticket_id, admin_id, body)
    if user_id is None:
        await message.answer("Открытое обращение с таким номером не найдено.")
        return
    try:
        await bot.send_message(
            user_id,
            "Ответ службы поддержки по обращению №{}:\n{}".format(ticket_id, body),
        )
    except TelegramAPIError as error:
        logger.exception(
            "Support reply delivery failed ticket_id=%s user_id=%s error_type=%s",
            ticket_id,
            user_id,
            type(error).__name__,
        )
        await message.answer(
            "Ответ сохранён, но Telegram не доставил его пользователю. "
            "Проверьте, что пользователь не заблокировал бота."
        )
        return
    await message.answer("Ответ по обращению №{} доставлен.".format(ticket_id))
    logger.info(
        "Support reply delivered ticket_id=%s admin_id=%s user_id=%s",
        ticket_id,
        admin_id,
        user_id,
    )


@router.message(Command("support_close"))
async def close_support_ticket(message: Message, repository: Any) -> None:
    admin_id = await get_admin_id(message, repository)
    if admin_id is None:
        await message.answer("Команда доступна только администратору студии.")
        return
    bot = message.bot
    if bot is None:
        raise RuntimeError("Telegram bot is unavailable while closing support")
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Формат: /support_close ID")
        return
    ticket_id = int(parts[1])
    user_id = await repository.close_support_ticket(ticket_id, admin_id)
    if user_id is None:
        await message.answer("Открытое обращение с таким номером не найдено.")
        return
    try:
        await bot.send_message(
            user_id,
            "Обращение №{} закрыто службой поддержки.".format(ticket_id),
        )
    except TelegramAPIError as error:
        logger.warning(
            "Support close notification failed ticket_id=%s user_id=%s error_type=%s",
            ticket_id,
            user_id,
            type(error).__name__,
        )
    await message.answer("Обращение №{} закрыто.".format(ticket_id))
    logger.info(
        "Support ticket closed ticket_id=%s admin_id=%s user_id=%s",
        ticket_id,
        admin_id,
        user_id,
    )


__all__ = ["router"]
