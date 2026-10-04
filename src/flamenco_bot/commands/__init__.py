"""Команды, отображаемые в меню Telegram."""

from .commands import (
    get_admin_commands,
    get_bot_commands,
    get_client_commands,
    register_commands,
)

__all__ = [
    "get_admin_commands",
    "get_bot_commands",
    "get_client_commands",
    "register_commands",
]
