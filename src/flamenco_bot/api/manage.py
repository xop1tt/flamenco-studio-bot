"""Серверные команды веб-аккаунтов (не доступны через API).

    python -m flamenco_bot.api.manage create-admin --email admin@example.com
        Создаёт аккаунт администратора сайта или делает администратором
        существующий (пароль заменяется). Пароль спрашивается интерактивно;
        для скриптов — ``--password-stdin`` (одна строка из stdin).

    python -m flamenco_bot.api.manage revoke-admin --email admin@example.com
        Снимает права администратора сайта (users.is_admin). Права
        администратора бота (bot_users.is_admin) не меняются.

Использует тот же .env и ту же БД, что API и бот (запускать из папки
проекта, PYTHONPATH=src). Пароль не пишется в логи и не хранится в открытом
виде — только PBKDF2-хеш, как при обычной регистрации.
"""

import argparse
import asyncio
import getpass
import sys

from ..database import PostgresRepository, is_database_configured
from ..services import AuthService
from .config import WebConfig


async def _connect():
    if not is_database_configured(WebConfig.DATABASE_URL):
        raise SystemExit("DATABASE_URL не задан — администратора некуда сохранить")
    repository = await PostgresRepository.connect(
        WebConfig.DATABASE_URL,
        ssl_ca_path=WebConfig.DATABASE_SSL_CA,
        pool_min_size=1,
        pool_max_size=2,
        ssl_mode=WebConfig.DATABASE_SSL_MODE,
        allow_insecure_local=WebConfig.ENV == "development",
    )
    # Схема должна быть не старее нужной коду (миграции — в DATABASE).
    await repository.initialize()
    return repository


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    password = getpass.getpass("Пароль администратора: ")
    if password != getpass.getpass("Повторите пароль: "):
        raise SystemExit("Пароли не совпадают")
    return password


async def create_admin(email: str, password: str, name: str) -> None:
    repository = await _connect()
    try:
        user = await AuthService(repository, WebConfig.BOT_TOKEN).ensure_admin_account(
            email, password, name
        )
    finally:
        await repository.close()
    print("Администратор сайта: {} (аккаунт №{})".format(user.email, user.id))


async def revoke_admin(email: str) -> None:
    repository = await _connect()
    try:
        user = await repository.get_web_user_by_email(email.strip().lower())
        if user is None:
            raise SystemExit("Аккаунт с таким email не найден")
        await repository.set_web_user_admin(user.id, False)
    finally:
        await repository.close()
    print("Права администратора сайта сняты: {}".format(email))


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="python -m flamenco_bot.api.manage")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser(
        "create-admin", help="создать/назначить администратора"
    )
    create.add_argument("--email", required=True)
    create.add_argument("--name", default="Администратор")
    create.add_argument("--password-stdin", action="store_true")
    revoke = commands.add_parser("revoke-admin", help="снять права администратора")
    revoke.add_argument("--email", required=True)
    args = parser.parse_args(argv)

    if args.command == "create-admin":
        password = _read_password(args.password_stdin)
        try:
            asyncio.run(create_admin(args.email, password, args.name))
        except ValueError as error:
            raise SystemExit(str(error)) from error
    else:
        asyncio.run(revoke_admin(args.email))


__all__ = ["main"]

if __name__ == "__main__":
    main()
