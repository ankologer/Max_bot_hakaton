"""Межпроцессная блокировка polling для одного токена."""

from fcntl import LOCK_EX, LOCK_NB, LOCK_UN, flock
from hashlib import sha256
from os import getpid
from pathlib import Path
from typing import TextIO


def acquire_instance_lock(token: str, directory: Path) -> TextIO:
    directory.mkdir(parents=True, exist_ok=True)
    token_hash = sha256(token.encode()).hexdigest()
    path = directory / f".polling-{token_hash}.lock"
    file = path.open("a+")
    try:
        try:
            flock(file.fileno(), LOCK_EX | LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                "Бот с этим токеном уже запущен. "
                "Остановите другой экземпляр."
            ) from None
        file.seek(0)
        file.truncate()
        file.write(str(getpid()))
        file.flush()
    except BaseException:
        file.close()
        raise
    return file


def release_instance_lock(file: TextIO) -> None:
    try:
        flock(file.fileno(), LOCK_UN)
    finally:
        file.close()
