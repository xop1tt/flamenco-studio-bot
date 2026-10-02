"""Обращения пользователей в поддержку."""

import logging
from dataclasses import dataclass
from typing import Any

from ..database.repository import MAX_SUPPORT_MESSAGE_LENGTH
from ..runtime.security import SupportRateLimiter
from .notifications import AdminNotifier, NotificationReport


logger = logging.getLogger("bot.services.support")


class SupportMessageInvalidError(ValueError):
    pass


class SupportRateLimitedError(RuntimeError):
    pass


@dataclass(frozen=True)
class SupportSubmission:
    ticket_id: int
    created: bool
    notifications: NotificationReport


class SupportService:
    def __init__(
        self,
        repository: Any,
        limiter: SupportRateLimiter,
        notifier: AdminNotifier,
    ) -> None:
        self.repository = repository
        self.limiter = limiter
        self.notifier = notifier

    async def submit_message(
        self,
        telegram_id: int,
        user_name: str,
        body: str,
    ) -> SupportSubmission:
        body = body.strip()
        if not body or len(body) > MAX_SUPPORT_MESSAGE_LENGTH:
            raise SupportMessageInvalidError(
                "Сообщение должно содержать от 1 до {} символов.".format(
                    MAX_SUPPORT_MESSAGE_LENGTH
                )
            )
        if not self.limiter.allow(telegram_id):
            logger.warning("Support rate limit exceeded telegram_id=%s", telegram_id)
            raise SupportRateLimitedError("Слишком много сообщений")

        await self.repository.get_or_create_profile(
            telegram_id=telegram_id,
            user_name=user_name,
            is_admin=False,
        )
        ticket_id, created = await self.repository.create_support_message(
            telegram_id, body
        )
        report = await self.notifier.notify(
            "Обращение №{} от {} ({}):\n{}".format(
                ticket_id,
                user_name,
                telegram_id,
                body,
            ),
            event="support_ticket",
        )
        if not report.complete:
            logger.error(
                "Support ticket saved without notifying all admins ticket_id=%s "
                "recipients=%s delivered=%s",
                ticket_id,
                report.recipients,
                report.delivered,
            )
        logger.info(
            "Support message saved ticket_id=%s telegram_id=%s new_ticket=%s "
            "admin_notifications=%s",
            ticket_id,
            telegram_id,
            created,
            report.delivered,
        )
        return SupportSubmission(ticket_id, created, report)
