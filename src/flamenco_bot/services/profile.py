"""Правила профиля участника, общие для бота и веб-API."""

MAX_USER_NAME_LENGTH = 64


class InvalidUserNameError(ValueError):
    pass


def normalize_user_name(value: str) -> str:
    """Имя без пробелов по краям, от 1 до ``MAX_USER_NAME_LENGTH`` символов."""
    user_name = value.strip()
    if not user_name or len(user_name) > MAX_USER_NAME_LENGTH:
        raise InvalidUserNameError(
            "Имя должно содержать от 1 до {} символов".format(MAX_USER_NAME_LENGTH)
        )
    return user_name
