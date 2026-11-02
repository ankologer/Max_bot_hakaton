"""Настройка подключения к SQLite через Tortoise ORM"""

from pathlib import Path

from loguru import logger
from tortoise import Tortoise


async def connect_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    await Tortoise.init(
        config={
            "connections": {
                "default": {
                    "engine": "tortoise.backends.sqlite",
                    "credentials": {
                        "file_path": str(path),
                        "busy_timeout": 10000,
                    },
                },
            },
            "apps": {
                "models": {
                    "models": ["src.models"],
                    "default_connection": "default",
                },
            },
        },
        use_tz=True,
        timezone="UTC",
    )
    await Tortoise.generate_schemas(safe=True)
    logger.info("SQLite подключена: {}", path)


async def disconnect_database() -> None:
    await Tortoise.close_connections()
    logger.info("Соединения с SQLite закрыты")
