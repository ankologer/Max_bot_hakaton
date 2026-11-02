"""Точка входа в программу.

Примеры команд для запуска (из корня проекта):
- ./.venv/bin/python -m src.main
- ./.venv/bin/python -m src.main --LOG_LEVEL=DEBUG
- ./.venv/bin/python -m src.main --DATABASE_PATH=data/dev.sqlite3

Справка (без запуска бота):
- ./.venv/bin/python -m src.main --help
- ./.venv/bin/python -m src.main -h
- ./.venv/bin/python -m src.main help
"""

from asyncio import (
    CancelledError,
    current_task,
    get_running_loop,
    run as asyncio_run,
)
from signal import SIGTERM
from sys import argv, stderr

from src.config import (
    HELP_TEXT,
    PROJECT_ROOT,
    Settings,
    load_settings,
    parse_overrides,
)
from src.instance import acquire_instance_lock, release_instance_lock


async def run(settings: Settings) -> None:
    from loguru import logger
    from maxo import Bot, Dispatcher

    from src.database import connect_database, disconnect_database
    from src.handlers import COMMANDS, create_router

    loop = get_running_loop()
    task = current_task()
    if task is not None:
        loop.add_signal_handler(SIGTERM, task.cancel)

    try:
        dispatcher = Dispatcher(disable_fsm=True)
        dispatcher.include(create_router())

        try:
            await connect_database(settings.database_path)
            bot = Bot(token=settings.bot_token)
            async with bot.context():
                await bot.edit_my_commands(commands=COMMANDS)
                logger.info("Запуск long polling")
                await dispatcher.start_polling(
                    bot,
                    auto_close_bot=False,
                    drop_pending_updates=False,
                    clear_subscriptions=False,
                )
        finally:
            await disconnect_database()
    except Exception:
        logger.opt(exception=True).critical(
            "Работа бота прервана ошибкой"
        )
        raise
    finally:
        if task is not None:
            loop.remove_signal_handler(SIGTERM)
        logger.info("Бот остановлен")
        await logger.complete()


def main() -> int:
    arguments = argv[1:]
    if any(
        argument in {"-h", "--help", "help"}
        for argument in arguments
    ):
        print(HELP_TEXT)
        return 0

    try:
        overrides = parse_overrides(arguments)
    except ValueError as error:
        print(
            f"Ошибка аргументов: {error} "
            "Справка: python -m src.main --help",
            file=stderr,
        )
        return 2

    try:
        settings = load_settings(overrides)
    except (ImportError, OSError, ValueError) as error:
        print(f"Ошибка настроек: {error}", file=stderr)
        return 1

    # Внешние библиотеки загружаются после проверки настроек.
    try:
        from loguru import logger

        from src.logging_setup import setup_logging

        setup_logging(settings.log_level, settings.log_file)
    except (ImportError, OSError, ValueError) as error:
        print(f"Ошибка настройки логирования: {error}", file=stderr)
        return 1

    try:
        instance_lock = acquire_instance_lock(
            settings.bot_token, PROJECT_ROOT / "data"
        )
        try:
            asyncio_run(run(settings))
        finally:
            release_instance_lock(instance_lock)
    except (KeyboardInterrupt, CancelledError):
        pass
    except Exception as error:
        logger.error("Запуск завершён с ошибкой: {}", error)
        logger.complete()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
