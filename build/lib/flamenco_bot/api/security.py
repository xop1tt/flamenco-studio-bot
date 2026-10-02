"""Сессионные cookie веб-API: формат токена и срок жизни.

Сессия хранится на сервере (таблица ``web_sessions``, см. миграцию
008_web_sessions.sql), а не в самоподписанном JWT: тот нельзя было отозвать
до истечения срока — logout лишь удалял cookie у клиента, похищенный токен
оставался действителен ещё 7 дней (см. аудит безопасности). Cookie несёт
только непрозрачный случайный токен; проверка и отзыв — через БД
(``repository.get_web_session_user_id`` / ``delete_web_session``).
"""

import secrets


SESSION_COOKIE_NAME = "session"
SESSION_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)
