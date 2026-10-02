"""Переменные окружения, нужные для одного только запуска тестов.

``flamenco_bot.config.Config`` и ``flamenco_bot.api.config.WebConfig``
проверяют обязательные переменные (``BOT_TOKEN``, ``SESSION_SECRET_KEY``) уже
на этапе импорта модуля — у тестов, которые импортируют
``flamenco_bot.api.app`` (например, ``test_api_auth.py``), это происходит
раньше, чем сам тест успевает что-то настроить.

Этот файл — пакетный ``__init__.py`` ``tests/`` — Python импортирует его
раньше любого тестового модуля при discovery (и ``unittest discover``, и
``pytest``), поэтому это единственное надёжное место подставить тестовые
заглушки до того, как упадёт импорт.

``load_dotenv()`` сначала подтягивает реальный `.env` разработчика (как и
``config/__init__.py``), а ``setdefault`` ниже подставляет значение только
если его там не оказалось — реальные секреты из `.env` не перезаписываются.
Эти заглушки никогда не используются вне тестового процесса.
"""

import os

from dotenv import load_dotenv

load_dotenv()

os.environ.setdefault("BOT_TOKEN", "123456:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
os.environ.setdefault(
    "SESSION_SECRET_KEY", "test-session-secret-key-not-for-production-use"
)
