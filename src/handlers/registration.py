"""Первое сообщение и ввод данных игрока."""

from loguru import logger
from maxo import Bot, Router
from maxo.routing.filters import CommandStart
from maxo.types import BotStarted, MessageCallback, MessageCreated

from src.game import GameError
from src.handlers.common import show_error
from src.handlers.game import read_answer
from src.models import Player, User
from src.texts import WELCOME_TEXT


async def welcome(ui, bot, profile):
    player = await ui.service.ensure_player(profile.id)
    await ui.show_state(bot, player, WELCOME_TEXT + "\n\n")


async def read_code(ui, bot, player, text):
    request = await ui.service.request_join(player.id, text)
    player = await ui.service.ensure_player(player.id)
    await ui.show_state(bot, player)
    try:
        await ui.show_request(bot, request)
    except Exception:
        logger.exception(
            "Капитан получит заявку через /team: {}", request.id,
        )


def create_router(ui):
    router = Router(name="registration")

    @router.bot_started()
    async def started(
        event: BotStarted, bot: Bot, profile: User,
    ):
        await welcome(ui, bot, profile)

    @router.message_created(CommandStart())
    async def start(
        event: MessageCreated, bot: Bot, profile: User,
    ):
        await welcome(ui, bot, profile)

    @router.message_created()
    async def message(
        event: MessageCreated, bot: Bot, profile: User,
    ):
        try:
            existing = await Player.get_or_none(id=profile.id)
            player = await ui.service.ensure_player(profile.id)
            text = (event.text or "").strip()
            if existing is None:
                await welcome(ui, bot, profile)
            elif text.startswith("/"):
                await ui.send(
                    bot, profile.id,
                    "Неизвестная команда. Открой /help или /start.",
                )
            elif not text:
                await ui.send(
                    bot, profile.id,
                    "Нужно текстовое сообщение. "
                    "Открой /start, чтобы увидеть текущий шаг.",
                )
            elif player.state == "school":
                player = await ui.service.set_school(player.id, text)
                await ui.show_state(bot, player)
            elif player.state == "class":
                player = await ui.service.set_class(player.id, text)
                await ui.show_state(bot, player)
            elif player.state == "code":
                await read_code(ui, bot, player, text)
            elif player.state == "ready":
                await read_answer(ui, bot, player, text)
            else:
                await ui.show_state(bot, player)
        except GameError as error:
            await show_error(ui, bot, profile, error)

    @router.message_callback()
    async def unknown_button(
        event: MessageCallback, bot: Bot, profile: User,
    ):
        await event.callback_answer()
        await ui.send(
            bot, profile.id, "Эта кнопка устарела. Открой /start.",
        )

    return router
