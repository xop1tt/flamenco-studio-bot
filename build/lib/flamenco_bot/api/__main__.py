import os

import uvicorn


def run() -> None:
    uvicorn.run(
        "flamenco_bot.api.app:app",
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "8000")),
    )


if __name__ == "__main__":
    run()
