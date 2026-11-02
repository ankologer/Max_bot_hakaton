"""Настройка логгирования через loguru"""

from logging import (
    Handler,
    LogRecord,
    __file__ as logging_file,
    basicConfig,
    currentframe,
)
from pathlib import Path
from sys import stderr

from loguru import logger


class InterceptHandler(Handler):
    def emit(self, record: LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame = currentframe()
        depth = 0
        while frame and (
            depth == 0
            or frame.f_code.co_filename == logging_file
        ):
            frame = frame.f_back
            depth += 1

        logger.opt(
            depth=depth,
            exception=record.exc_info,
        ).log(level, record.getMessage())


def setup_logging(level: str, log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    options = {
        "level": level,
        "enqueue": True,
        "backtrace": False,
        "diagnose": False,
        "format": (
            "{time:YYYY-MM-DD HH:mm:ss.SSS Z} | {level: <8} | "
            "{name}:{line} | {message}"
        ),
    }
    logger.add(stderr, **options)
    logger.add(
        log_file,
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
        **options,
    )
    basicConfig(
        handlers=[InterceptHandler()],
        level=logger.level(level).no,
        force=True,
    )
