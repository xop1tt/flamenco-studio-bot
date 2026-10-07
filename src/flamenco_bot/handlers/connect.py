"""Вход на сайт и привязка Telegram через бота: /start c_<token>.

Сайт создаёт одноразовый запрос (``/api/auth/telegram/connect``) и ведёт
участника по ссылке t.me/<бот>?start=c_<token>. Здесь участник явно
подтверждает действие кнопкой; Telegram ID берётся из самого апдейта
Telegram, а не из сайта, — подделать его нельзя. Сессию сайт выдаёт только
браузеру, который создал запрос (секрет в его httpOnly-cookie).

callback_data: ``tgc:<token>`` — подтвердить, ``tgx:<token>`` — отказаться
(токен — 32 символа, укладывается в лимит 64 байта).
"""

import logging
from typing import Any

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message

from ..config import Config
from ..database.repository import TelegramAlreadyLinkedError
from ..database.studio_models import TelegramConnectError
from ..keyboards.user.screens import button, markup, show
from ..services import AuthService
from ..services.auth import CONNECT_START_PREFIX, mask_email
from ..studio_time import to_studio_time


logger = logging.getLogger("bot.handlers.connect")
router = Router(name="telegram_connect")


def _auth_service(repository: Any) -> AuthService:
    return AuthService(repository, Config.BOT_TOKEN)


@router.message(
    CommandStart(deep_link=True, magic=F.args.startswith(CONNECT_START_PREFIX))
)
async def start_connect(
    message: Message, command: CommandObject, repository: Any
) -> None:
    token = (command.args or "")[len(CONNECT_START_PREFIX) :]
    try:
        request = await _auth_service(repository).describe_telegram_connect(token)
    except TelegramConnectError:
        await message.answer(
            "Ссылка для входа на сайт недействительна или устарела. Вернитесь на "
            "сайт и нажмите «Войти через Telegram» ещё раз."
        )
        return
    until = to_studio_time(request.expires_at).strftime("%H:%M")
    if request.purpose == "link":
        text = (
            "Привязка Telegram к аккаунту сайта {}\n\n"
            "После привязки на сайте будут видны ваши занятия, баланс и "
            "абонементы из этого бота.\n\n"
            "Подтверждайте, только если вы сами сейчас привязываете Telegram на "
            "сайте студии. Никому не пересылайте эту ссылку. Ссылка действует "
            "до {}."
        ).format(mask_email(request.web_user_email), until)
        confirm = "✅ Привязать"
    else:
        text = (
            "Вход на сайт студии\n\n"
            "Нажмите «Войти на сайт», только если вы сами сейчас входите на "
            "сайт студии через Telegram. Никому не пересылайте эту ссылку: "
            "тот, кто подтвердит её, войдёт в ваш аккаунт. Ссылка действует "
            "до {}."
        ).format(until)
        confirm = "✅ Войти на сайт"
    await message.answer(
        text,
        reply_markup=markup(
            [button(confirm, "tgc:{}".format(token))],
            [button("Отмена", "tgx:{}".format(token))],
        ),
    )
    logger.info(
        "Telegram connect confirmation shown telegram_id=%s purpose=%s",
        message.from_user.id if message.from_user else None,
        request.purpose,
    )


@router.callback_query(F.data.startswith("tgc:"))
async def confirm_connect(callback: CallbackQuery, repository: Any) -> None:
    token = (callback.data or "").split(":", 1)[1]
    sender = callback.from_user
    try:
        request = await _auth_service(repository).confirm_telegram_connect(
            token, sender.id, sender.full_name
        )
    except TelegramConnectError:
        await callback.answer()
        await show(
            callback,
            "Ссылка уже использована или устарела. Вернитесь на сайт и начните "
            "вход заново.",
            None,
        )
        return
    except TelegramAlreadyLinkedError:
        # Сайт сразу узнает об отказе (статус rejected), а не ждёт истечения.
        await _auth_service(repository).reject_telegram_connect(token)
        await callback.answer()
        await show(
            callback,
            "Этот Telegram уже привязан к другому аккаунту сайта с email. Войдите "
            "на сайт через Telegram или напишите в «💬 Поддержка».",
            None,
        )
        return
    await callback.answer("Готово")
    await show(
        callback,
        "Готово ✓ Telegram привязан к аккаунту сайта. Вернитесь на сайт — "
        "страница обновится сама."
        if request.purpose == "link"
        else "Готово ✓ Вернитесь на сайт — вход выполнится автоматически.",
        None,
    )


@router.callback_query(F.data.startswith("tgx:"))
async def reject_connect(callback: CallbackQuery, repository: Any) -> None:
    token = (callback.data or "").split(":", 1)[1]
    await _auth_service(repository).reject_telegram_connect(token)
    await callback.answer()
    await show(
        callback, "Вход отменён. Если это были не вы — ничего делать не нужно.", None
    )
