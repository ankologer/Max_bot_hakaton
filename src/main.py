r"""Точка входа в программу.

Примеры команд для запуска (из корня проекта):
- python src/main.py
- python src/main.py --LOG_LEVEL=DEBUG
- python src/main.py --DATABASE_PATH=data/dev.sqlite3
- python -m src.main

PowerShell без активации окружения:
- .\.venv\Scripts\python.exe src/main.py

Справка (без запуска бота):
- python src/main.py --help
- python src/main.py -h
- python src/main.py help
"""

from asyncio import (
    CancelledError,
    current_task,
    get_running_loop,
    run as asyncio_run,
)
from io import TextIOWrapper
from signal import SIGTERM
from pathlib import Path
from sys import argv, path as sys_path, platform, stderr, stdout

if not __package__:
    sys_path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import (
    HELP_TEXT,
    Settings,
    load_settings,
    parse_overrides,
)


async def run(settings: Settings) -> None:
    from loguru import logger
    from maxo import Bot, Dispatcher

    from src.database import connect_database, disconnect_database
    from src.handlers.router import create_router
    from src.startup import notify_admins
    from src.texts import COMMANDS
    from src.views import GameViews

    loop = get_running_loop()
    task = current_task()
    if task is not None and platform != "win32":
        loop.add_signal_handler(SIGTERM, task.cancel)

    try:
        dispatcher = Dispatcher(disable_fsm=True)
        ui = GameViews(settings.admin_ids)
        dispatcher.include(create_router(ui))

        try:
            await connect_database(settings.database_path)
            bot = Bot(token=settings.bot_token)
            async with bot.context():
                await bot.edit_my_commands(commands=COMMANDS)
                await notify_admins(bot, ui)
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
        if task is not None and platform != "win32":
            loop.remove_signal_handler(SIGTERM)
        logger.info("Бот остановлен")
        await logger.complete()


def main() -> int:
    if platform == "win32":
        for stream in (stdout, stderr):
            if isinstance(stream, TextIOWrapper):
                stream.reconfigure(encoding="utf-8")

    arguments = argv[1:]
    for argument in arguments:
        if argument in {"-h", "--help", "help"}:
            print(HELP_TEXT)
            return 0

    try:
        overrides = parse_overrides(arguments)
    except ValueError as error:
        print(
            f"Ошибка аргументов: {error} "
            "Справка: python src/main.py --help",
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
        asyncio_run(run(settings))
    except (KeyboardInterrupt, CancelledError):
        pass
    except Exception as error:
        logger.error("Запуск завершён с ошибкой: {}", error)
        logger.complete()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
