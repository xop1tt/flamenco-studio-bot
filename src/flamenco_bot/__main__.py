import asyncio

from flamenco_bot.main import main


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
