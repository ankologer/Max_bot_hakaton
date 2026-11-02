"""Загрузка и проверка настроек"""

from dataclasses import dataclass, field
from enum import StrEnum
from os import environ, getenv
from pathlib import Path
from re import fullmatch

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class LogLevel(StrEnum):
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


HELP_TEXT = """Бот MAX — получение событий через long polling.

Запуск из корня проекта:
  python -m src.main
  python -m src.main --LOG_LEVEL=DEBUG
  python -m src.main --DATABASE_PATH=data/dev.sqlite3

Справка (без запуска бота):
  python -m src.main -h
  python -m src.main --help
  python -m src.main help

Приоритет настроек: --KEY=VALUE, затем .env, затем окружение процесса.
Для повторяющегося KEY используется последнее значение из команды.
Значения с пробелами заключайте в кавычки:
  --LOG_FILE="logs/my bot.log"
  BOT_TOKEN      Обязательный токен бота.
  DATABASE_PATH  Файл SQLite (по умолчанию data/bot.sqlite3).
  LOG_FILE       Файл логов (по умолчанию logs/bot.log).
  LOG_LEVEL      Уровень логирования (по умолчанию INFO).

Остановка: Ctrl+C или SIGTERM.
"""


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str = field(repr=False)
    database_path: Path
    log_file: Path
    log_level: LogLevel


def parse_overrides(arguments: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for argument in arguments:
        if not argument.startswith("--"):
            raise ValueError(
                "Настройки нужно передавать в формате --KEY=VALUE."
            )
        name, separator, value = argument[2:].partition("=")
        if (
            not separator
            or fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None
        ):
            raise ValueError(
                "Ожидается --KEY=VALUE, "
                "где KEY — имя переменной окружения."
            )
        overrides[name] = value
    return overrides


def _path_from_env(name: str, default: str) -> Path:
    value = getenv(name, default).strip()
    if not value:
        raise ValueError(f"{name} не должен быть пустым.")
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_settings(
    overrides: dict[str, str] | None = None,
) -> Settings:
    from dotenv import load_dotenv

    # Значения из .env перекрывают окружение процесса.
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    # Аргументы команды перекрывают .env и окружение процесса.
    if overrides:
        environ.update(overrides)

    token = getenv("BOT_TOKEN", "").strip()
    if not token:
        raise ValueError(
            "Не задан BOT_TOKEN. "
            "Укажите токен бота в .env или окружении."
        )

    try:
        log_level = LogLevel(
            getenv("LOG_LEVEL", LogLevel.INFO.value).strip().upper()
        )
    except ValueError:
        allowed_levels = ", ".join(level.value for level in LogLevel)
        raise ValueError(
            f"LOG_LEVEL должен быть одним из: {allowed_levels}."
        ) from None

    return Settings(
        bot_token=token,
        database_path=_path_from_env(
            "DATABASE_PATH", "data/bot.sqlite3"
        ),
        log_file=_path_from_env("LOG_FILE", "logs/bot.log"),
        log_level=log_level,
    )
