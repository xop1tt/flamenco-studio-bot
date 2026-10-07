"""Уведомления: администраторам (сразу) и участникам (через outbox)."""

import logging
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from aiogram.exceptions import TelegramAPIError

from ..database.studio_models import NotificationSettings, UserNotification


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


class NotificationService:
    """Лента уведомлений участника и его настройки (бот и сайт).

    Сами уведомления ставит в outbox репозиторий — в той же транзакции,
    что и событие; отправку в Telegram выполняет фоновый диспетчер
    (``runtime/notifications.py``).
    """

    def __init__(self, repository: Any) -> None:
        self.repository = repository

    async def feed(
        self,
        telegram_id: int,
        limit: int = 20,
        unread_only: bool = False,
        before_id: Optional[int] = None,
    ) -> Sequence[UserNotification]:
        return await self.repository.list_notifications(
            telegram_id, limit=limit, unread_only=unread_only, before_id=before_id
        )

    async def unread_count(self, telegram_id: int) -> int:
        return await self.repository.count_unread_notifications(telegram_id)

    async def mark_read(
        self,
        telegram_id: int,
        notification_ids: Optional[Sequence[int]] = None,
    ) -> int:
        return await self.repository.mark_notifications_read(
            telegram_id, notification_ids
        )

    async def settings(self, telegram_id: int) -> NotificationSettings:
        return await self.repository.get_notification_settings(telegram_id)

    async def update_settings(
        self,
        telegram_id: int,
        reminders: Optional[bool] = None,
        low_balance: Optional[bool] = None,
    ) -> NotificationSettings:
        settings = await self.repository.update_notification_settings(
            telegram_id, reminders=reminders, low_balance=low_balance
        )
        logger.info(
            "Notification settings updated telegram_id=%s reminders=%s low_balance=%s",
            telegram_id,
            settings.reminders,
            settings.low_balance,
        )
        return settings
