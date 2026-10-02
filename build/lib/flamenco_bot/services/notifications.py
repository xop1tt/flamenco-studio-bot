"""Уведомления администраторов студии через существующего Telegram-бота."""

import logging
from dataclasses import dataclass
from typing import Any

from aiogram.exceptions import TelegramAPIError


logger = logging.getLogger("bot.services.notifications")


@dataclass(frozen=True)
class NotificationReport:
    recipients: int
    delivered: int

    @property
    def complete(self) -> bool:
        return self.recipients > 0 and self.delivered == self.recipients


class AdminNotifier:
    """Рассылает сообщение всем администраторам из bot_users.

    Ошибка доставки одному администратору не прерывает рассылку остальным:
    бизнес-операция к этому моменту уже сохранена в БД.
    """

    def __init__(self, bot: Any, repository: Any) -> None:
        self.bot = bot
        self.repository = repository

    async def notify(self, text: str, event: str) -> NotificationReport:
        admin_ids = await self.repository.list_admin_ids()
        delivered = 0
        for admin_id in admin_ids:
            try:
                await self.bot.send_message(admin_id, text)
                delivered += 1
            except TelegramAPIError as error:
                logger.warning(
                    "Admin notification failed event=%s admin_id=%s error_type=%s",
                    event,
                    admin_id,
                    type(error).__name__,
                )
        return NotificationReport(recipients=len(admin_ids), delivered=delivered)
