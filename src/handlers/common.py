"""Помощь и профиль пользователя."""

from maxo import Bot, Router
from maxo.omit import is_defined
from maxo.routing.filters import Command, SyncFilter
from maxo.types import MessageCallback, MessageCreated

from src.models import User


def is_help(event):
    if not is_defined(event.payload):
        return False
    return event.payload == "game:help"


async def show_error(ui, bot, profile, error):
    player = await ui.service.ensure_player(profile.id)
    await ui.show_state(bot, player, str(error) + "\n\n")


def create_router(ui):
    router = Router(name="common")

    @router.message_created(Command("help"))
    async def help_command(
        event: MessageCreated, bot: Bot, profile: User,
    ):
        await ui.show_help(bot, profile.id)

    @router.message_callback(SyncFilter(is_help))
    async def help_button(
        event: MessageCallback, bot: Bot, profile: User,
    ):
        await event.callback_answer()
        await ui.show_help(bot, profile.id)

    @router.message_created(Command("me"))
    async def profile_command(
        event: MessageCreated, bot: Bot, profile: User,
    ):
        player = await ui.service.ensure_player(profile.id)
        await ui.show_profile(bot, profile, player)

    return router
