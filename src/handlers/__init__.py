"""Сборка обработчиков бота."""

from maxo import Router
from maxo.omit import is_defined
from maxo.routing.filters import SyncFilter

from src.handlers import common, echo
from src.handlers.common import COMMANDS
from src.middleware import (
    ProcessingMiddleware,
    UserContextMiddleware,
)

__all__ = ["COMMANDS", "create_router"]


def create_router() -> Router:
    """Подключение обработчиков"""
    router = Router(name="handlers")
    router.message_created.filter(
        SyncFilter(
            lambda event: is_defined(sender := event.message.sender)
            and not sender.is_bot,
        ),
    )
    router.bot_started.filter(
        SyncFilter(lambda event: not event.user.is_bot)
    )
    processing = ProcessingMiddleware()
    user_context = UserContextMiddleware()
    router.message_created.middleware(processing, user_context)
    router.bot_started.middleware(processing, user_context)
    router.include(common.create_router(), echo.create_router())
    return router
