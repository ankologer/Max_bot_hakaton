"""Форматирование дат для сообщений игрокам."""

from datetime import datetime
from zoneinfo import ZoneInfo

_MOSCOW = ZoneInfo("Europe/Moscow")
_MONTHS = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def format_date(value: datetime) -> str:
    """Вернуть московское время в формате «9 ноября 23:59»."""
    if value.utcoffset() is None:
        raise ValueError("Дата должна содержать часовой пояс.")
    local = value.astimezone(_MOSCOW)
    return (
        f"{local.day} {_MONTHS[local.month - 1]} "
        f"{local.hour:02d}:{local.minute:02d}"
    )
