"""Выбор роли, заявки и управление командой."""

from maxo import Bot, Router
from maxo.omit import is_defined
from maxo.routing.filters import Command, SyncFilter
from maxo.types import MessageCallback, MessageCreated

from src.game import GameError
from src.handlers.common import show_error
from src.keyboards import (
    BACK_KEYBOARD, GAME_KEYBOARD, TEAM_KEYBOARD,
)
from src.models import Player, User
from src.texts import RULES_TEXT


def is_team_action(event):
    if not is_defined(event.payload):
        return False
    payload = event.payload
    if payload in {
        "game:captain", "game:participant", "game:roles",
        "game:reset", "game:team", "game:requests",
        "game:start_game",
    }:
        return True
    return payload.startswith(("game:approve:", "game:reject:"))


async def decide_request(ui, bot, player, action):
    decision, request_text = action.split(":", 1)
    if not request_text.isascii() or not request_text.isdecimal():
        raise GameError("Эта кнопка устарела. Открой заявки заново.")
    if len(request_text) > 18:
        raise GameError("Эта кнопка устарела. Открой заявки заново.")
    approve = decision == "approve"
    request = await ui.service.decide_join(
        player.id, int(request_text), approve,
    )
    if approve:
        message = "Капитан подтвердил вступление! Ждём начала игры."
        await ui.notify(
            bot, request.player_id, message, TEAM_KEYBOARD,
        )
        prefix = "Заявка принята.\n\n"
    else:
        message = (
            "Капитан отклонил заявку. "
            "Проверь данные и введи код ещё раз."
        )
        await ui.notify(
            bot, request.player_id, message, BACK_KEYBOARD,
        )
        prefix = "Заявка отклонена.\n\n"
    await ui.show_team(bot, player, prefix=prefix)


async def start_game(ui, bot, player):
    team = await ui.service.start_game(player.id)
    await ui.show_team(bot, player, team, "Игра началась!\n\n")
    members = await Player.filter(team_id=team.id)
    for member in members:
        if member.id != player.id:
            await ui.notify(
                bot, member.id,
                "Капитан начал игру!\n\n" + RULES_TEXT,
                GAME_KEYBOARD,
            )


def create_router(ui):
    router = Router(name="teams")

    @router.message_created(Command("team"))
    async def team_command(
        event: MessageCreated, bot: Bot, profile: User,
    ):
        player = await ui.service.ensure_player(profile.id)
        await ui.show_team(bot, player)
        team = await ui.service.get_team(player.id)
        if team is not None:
            if team.captain_id == player.id:
                if team.started_at is None:
                    await ui.show_requests(bot, player)

    @router.message_callback(SyncFilter(is_team_action))
    async def button(
        event: MessageCallback, bot: Bot, profile: User,
    ):
        await event.callback_answer()
        action = event.payload.removeprefix("game:")
        try:
            player = await ui.service.ensure_player(profile.id)
            if action == "captain":
                await ui.service.choose_captain(player.id)
                player = await ui.service.ensure_player(player.id)
                await ui.show_state(bot, player)
            elif action == "participant":
                player = await ui.service.choose_participant(
                    player.id,
                )
                await ui.show_state(bot, player)
            elif action == "roles":
                player = await ui.service.return_to_roles(player.id)
                await ui.show_state(bot, player)
            elif action == "reset":
                player = await ui.service.reset_registration(
                    player.id,
                )
                await ui.show_state(bot, player)
            elif action == "team":
                await ui.show_team(bot, player)
            elif action == "requests":
                await ui.show_requests(bot, player)
            elif action == "start_game":
                await start_game(ui, bot, player)
            else:
                await decide_request(ui, bot, player, action)
        except GameError as error:
            await show_error(ui, bot, profile, error)

    return router
