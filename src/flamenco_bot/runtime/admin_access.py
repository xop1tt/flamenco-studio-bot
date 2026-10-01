import logging
from typing import Any, Optional

from aiogram.types import Message


logger = logging.getLogger("bot.admin_access")


async def get_admin_id(message: Message, repository: Any) -> Optional[int]:
    sender = message.from_user
    if sender is None or message.chat.type != "private":
        logger.debug(
            "Admin access denied reason=%s telegram_id=%s",
            "missing_sender" if sender is None else "non_private_chat",
            sender.id if sender else None,
        )
        return None

    profile = await repository.get_profile(sender.id)
    if (
        profile is None
        or profile.telegram_id != sender.id
        or not profile.is_admin
    ):
        logger.debug(
            "Admin access denied reason=%s telegram_id=%s",
            "not_registered_or_not_admin",
            sender.id,
        )
        return None
    logger.debug("Admin access granted telegram_id=%s", sender.id)
    return sender.id
