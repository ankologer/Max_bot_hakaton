"""Объединение обработчиков и общие фильтры."""

from maxo import Router
from maxo.enums import ChatType
from maxo.omit import is_defined
from maxo.routing.filters import SyncFilter

from src.handlers import admin, common, game, registration, teams
from src.middleware import ProcessingMiddleware, UserContextMiddleware


def is_private_message(event):
    sender = event.message.sender
    if not is_defined(sender):
        return False
    if sender.is_bot:
        return False
    return event.message.recipient.chat_type == ChatType.DIALOG


def is_human_start(event):
    return not event.user.is_bot


def is_private_callback(event):
    if event.user.is_bot:
        return False
    if event.message is None:
        return True
    return event.message.recipient.chat_type == ChatType.DIALOG


def create_router(ui):
    router = Router(name="handlers")
    router.message_created.filter(SyncFilter(is_private_message))
    router.bot_started.filter(SyncFilter(is_human_start))
    router.message_callback.filter(SyncFilter(is_private_callback))
    processing = ProcessingMiddleware()
    user_context = UserContextMiddleware()
    router.message_created.middleware(processing, user_context)
    router.bot_started.middleware(processing, user_context)
    router.message_callback.middleware(processing, user_context)
    router.include(
        common.create_router(ui),
        admin.create_router(ui),
        teams.create_router(ui),
        game.create_router(ui),
        registration.create_router(ui),
    )
    return router
