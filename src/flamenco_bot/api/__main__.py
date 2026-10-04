import ipaddress
import os

import uvicorn


# Rate limit входа (/api/auth/*) считает попытки по IP клиента
# (``request.client.host``). За прокси это адрес прокси, поэтому uvicorn
# подставляет IP из X-Forwarded-For — но только для соединений от адресов из
# FORWARDED_ALLOW_IPS и выбирая самый правый недоверенный адрес. Доверять
# можно лишь прокси, который сам записывает IP клиента: в production это
# контейнер сайта за edge-прокси (см. compose.yaml и docs/deployment.md).
# Без переменной — только 127.0.0.1, как у uvicorn по умолчанию (локальный
# запуск без прокси).
DEFAULT_FORWARDED_ALLOW_IPS = "127.0.0.1"


def forwarded_allow_ips() -> str:
    value = os.getenv("FORWARDED_ALLOW_IPS", DEFAULT_FORWARDED_ALLOW_IPS)
    entries = [item.strip() for item in value.split(",") if item.strip()]
    if not entries:
        raise ValueError("FORWARDED_ALLOW_IPS не должен быть пустым")
    for entry in entries:
        if entry == "*":
            # С "*" любой клиент подставит произвольный X-Forwarded-For и
            # обойдёт rate limit входа.
            raise ValueError(
                "FORWARDED_ALLOW_IPS='*' небезопасен: укажите IP или сеть "
                "доверенного прокси"
            )
        try:
            ipaddress.ip_network(entry, strict=False)
        except ValueError as error:
            # uvicorn молча считает некорректную запись строкой и никогда с
            # ней не совпадёт — лучше упасть при старте, чем тихо не доверять.
            raise ValueError(
                "FORWARDED_ALLOW_IPS: «{}» — не IP-адрес и не сеть".format(entry)
            ) from error
    return ",".join(entries)


def run() -> None:
    uvicorn.run(
        "flamenco_bot.api.app:app",
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips=forwarded_allow_ips(),
    )


if __name__ == "__main__":
    run()
