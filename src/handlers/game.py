"""Задания и результаты раундов."""

from maxo import Bot, Router
from maxo.omit import is_defined
from maxo.routing.filters import Command, SyncFilter
from maxo.types import MessageCallback, MessageCreated

from src.game import GameError
from src.handlers.common import show_error
from src.keyboards import GAME_KEYBOARD
from src.models import User
from src.texts import DONE_TEXT


def is_game_action(event):
    if not is_defined(event.payload):
        return False
    return event.payload in {"game:tasks", "game:results"}


async def read_answer(ui, bot, player, text):
    if player.answer_assignment_id is None:
        await ui.show_task(bot, player)
        return
    solved = await ui.service.submit_answer(
        player.id, text,
        assignment_id=player.answer_assignment_id,
    )
    answer = DONE_TEXT
    if not solved:
        answer = (
            "Пока неверно. Попробуй ещё раз: "
            "ответ можно исправлять до конца раунда."
        )
    await ui.send(bot, player.id, answer, GAME_KEYBOARD)


def create_router(ui):
    router = Router(name="game")

    @router.message_created(Command("tasks"))
    async def tasks(
        event: MessageCreated, bot: Bot, profile: User,
    ):
        player = await ui.service.ensure_player(profile.id)
        await ui.show_task(bot, player)

    @router.message_created(Command("results"))
    async def results(
        event: MessageCreated, bot: Bot, profile: User,
    ):
        player = await ui.service.ensure_player(profile.id)
        await ui.show_results(bot, player)

    @router.message_callback(SyncFilter(is_game_action))
    async def button(
        event: MessageCallback, bot: Bot, profile: User,
    ):
        await event.callback_answer()
        try:
            player = await ui.service.ensure_player(profile.id)
            if event.payload == "game:tasks":
                await ui.show_task(bot, player)
            else:
                await ui.show_results(bot, player)
        except GameError as error:
            await show_error(ui, bot, profile, error)

    return router
