import logging
import time
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ..keyboards.user import HELP, input_keyboard, main_menu_keyboard
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
# Брошенное обращение не должно через час превратить случайное сообщение
# («спасибо», «привет») в новое обращение.
SUPPORT_INPUT_TTL_SECONDS = 30 * 60


@router.message(F.text == HELP)
async def start_support(
    message: Message,
    state: FSMContext,
) -> None:
    await state.set_state(SupportForm.waiting_for_message)
    await state.update_data(support_started_at=time.time())
    await message.answer(
        "Поддержка\n\n"
        "Напишите вопрос одним сообщением (до 2000 символов) — его получат "
        "администраторы студии, ответ придёт в этот чат.\n\n"
        "Направления, цены и правила записи — /about. Прежние обращения "
        "и ответы — «👤 Профиль» → «📨 Мои обращения». "
        "Передумали писать — нажмите «❌ Отмена».",
        reply_markup=input_keyboard(),
    )


def reply_button_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ответить", callback_data="support_reply")]
        ]
    )


@router.callback_query(F.data == "support_reply")
async def start_support_reply(callback: CallbackQuery, state: FSMContext) -> None:
    """«Ответить» под ответом администратора — продолжить переписку.

    Сообщение попадёт в то же открытое обращение (репозиторий дописывает
    сообщения пользователя в его открытый тикет).
    """
    await callback.answer()
    if callback.message is None:
        return
    await start_support(callback.message, state)


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

    started_at = (await state.get_data()).get("support_started_at")
    if not started_at or time.time() - started_at > SUPPORT_INPUT_TTL_SECONDS:
        await state.clear()
        await message.answer(
            "Сообщение не отправлено: обращение было начато слишком давно. "
            "Чтобы написать в студию, нажмите «💬 Поддержка» ещё раз.",
            reply_markup=main_menu_keyboard(
                is_admin=await get_admin_id(message, repository) is not None
            ),
        )
        return

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
        await message.answer(
            str(error) + " Попробуйте ещё раз или нажмите «❌ Отмена»."
        )
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
            "Сообщение сохранено (обращение №{}), но администраторы пока не "
            "настроены — ответ может задержаться."
        ).format(submission.ticket_id)
    elif not report.complete:
        confirmation = (
            "Сообщение сохранено (обращение №{}), но уведомить администратора "
            "сразу не удалось — он увидит его в списке обращений. Ответ придёт "
            "в этот чат."
        ).format(submission.ticket_id)
    else:
        confirmation = (
            "Сообщение отправлено (обращение №{}). Ответ придёт в этот чат. "
            "Чтобы дописать, снова нажмите «💬 Поддержка»."
        ).format(submission.ticket_id)
    await message.answer(
        confirmation,
        reply_markup=main_menu_keyboard(is_admin=is_admin),
    )


@router.message(SupportForm.waiting_for_message, ~F.text)
async def reject_non_text_support_message(message: Message) -> None:
    await message.answer(
        "Пожалуйста, напишите вопрос обычным текстом или нажмите «❌ Отмена»."
    )


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
    await message.answer(
        await deliver_support_reply(bot, repository, ticket_id, admin_id, body)
    )


async def deliver_support_reply(
    bot: Any,
    repository: Any,
    ticket_id: int,
    admin_id: int,
    body: str,
) -> str:
    """Сохраняет ответ администратора и отправляет его участнику.

    Возвращает текст результата для администратора. Общий шаг для
    /support_reply и кнопки «Ответить» в админ-панели.
    """
    user_id = await repository.reply_support_ticket(ticket_id, admin_id, body)
    if user_id is None:
        return "Открытое обращение с таким номером не найдено."
    try:
        await bot.send_message(
            user_id,
            "Ответ службы поддержки по обращению №{}:\n{}".format(ticket_id, body),
            reply_markup=reply_button_markup(),
        )
    except TelegramAPIError as error:
        logger.exception(
            "Support reply delivery failed ticket_id=%s user_id=%s error_type=%s",
            ticket_id,
            user_id,
            type(error).__name__,
        )
        return (
            "Ответ сохранён, но Telegram не доставил его пользователю. "
            "Проверьте, что пользователь не заблокировал бота."
        )
    logger.info(
        "Support reply delivered ticket_id=%s admin_id=%s user_id=%s",
        ticket_id,
        admin_id,
        user_id,
    )
    return "Ответ по обращению №{} доставлен.".format(ticket_id)


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
    if not await close_ticket_and_notify(bot, repository, ticket_id, admin_id):
        await message.answer("Открытое обращение с таким номером не найдено.")
        return
    await message.answer("Обращение №{} закрыто.".format(ticket_id))


async def close_ticket_and_notify(
    bot: Any, repository: Any, ticket_id: int, admin_id: int
) -> bool:
    """Закрывает обращение и сообщает участнику; ``False`` — не найдено."""
    user_id = await repository.close_support_ticket(ticket_id, admin_id)
    if user_id is None:
        return False
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
    logger.info(
        "Support ticket closed ticket_id=%s admin_id=%s user_id=%s",
        ticket_id,
        admin_id,
        user_id,
    )
    return True


__all__ = ["router"]
