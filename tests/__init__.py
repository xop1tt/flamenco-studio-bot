"""Переменные окружения, нужные для одного только запуска тестов.

``flamenco_bot.config.Config`` проверяет обязательную переменную
(``BOT_TOKEN``) уже на этапе импорта модуля — у тестов, которые импортируют
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
import sys
from pathlib import Path

from dotenv import load_dotenv

# Тесты запускаются и из корня этого проекта, и из родительской папки
# рабочей области редактора (обнаружение тестов в VS Code): пакет
# ``flamenco_bot`` лежит в src/, и от PYTHONPATH или установки пакета зависеть
# нельзя. Этот файл импортируется раньше любого тестового модуля.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _path in (_PROJECT_ROOT / "src", _PROJECT_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

load_dotenv()

os.environ.setdefault("BOT_TOKEN", "123456:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
