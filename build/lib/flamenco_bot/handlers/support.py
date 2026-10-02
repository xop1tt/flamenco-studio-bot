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
from ..services import (
    AdminNotifier,
    SupportMessageInvalidError,
    SupportRateLimitedError,
    SupportService,
)
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

    support_service = SupportService(
        repository, support_limiter, AdminNotifier(bot, repository)
    )
    try:
        submission = await support_service.submit_message(
            telegram_id=sender.id,
            user_name=sender.full_name.strip() or "Участник студии",
            body=message.text or "",
        )
    except SupportMessageInvalidError as error:
        await message.answer(str(error))
        return
    except SupportRateLimitedError:
        await message.answer(
            "Слишком много сообщений. Попробуйте отправить обращение через "
            "несколько минут."
        )
        return

    await state.clear()
    is_admin = await get_admin_id(message, repository) is not None
    report = submission.notifications
    if report.recipients == 0:
        confirmation = (
            "Обращение №{} сохранено, но администраторы пока не настроены."
        ).format(submission.ticket_id)
    elif not report.complete:
        confirmation = (
            "Обращение №{} сохранено, но уведомить администратора не удалось. "
            "Администраторы проверят его в панели поддержки."
        ).format(submission.ticket_id)
    else:
        confirmation = (
            "Обращение №{} сохранено. Администратор ответит вам здесь."
        ).format(submission.ticket_id)
    await message.answer(
        confirmation,
        reply_markup=main_menu_keyboard(is_admin=is_admin),
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
