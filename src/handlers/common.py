"""Начало работы, справка и профиль."""

from datetime import UTC

from maxo import Router
from maxo.routing.filters import Command, CommandStart
from maxo.types import BotCommand, BotStarted, MessageCreated

from src.models import User

COMMANDS: list[BotCommand] = [
    BotCommand(name="start", description="Начать работу"),
    BotCommand(name="help", description="Показать справку"),
    BotCommand(name="me", description="Показать мой профиль"),
]

WELCOME_TEXT = (
    "Привет! Я повторяю текстовые сообщения.\n"
    "Команды: /help — справка, /me — мой профиль."
)
HELP_TEXT = (
    "/start — начать работу\n"
    "/help — показать справку\n"
    "/me — показать профиль и дату регистрации\n\n"
    "Отправь текст, и я повторю его."
)


def create_router() -> Router:
    """Создать обработчики команд и кнопки запуска."""
    router = Router(name="common")

    @router.bot_started()
    async def bot_started(event: BotStarted) -> None:
        await event.send_message(WELCOME_TEXT, format=None)

    @router.message_created(CommandStart())
    async def start(event: MessageCreated) -> None:
        await event.answer(WELCOME_TEXT, format=None)

    @router.message_created(Command("help"))
    async def help_command(event: MessageCreated) -> None:
        await event.answer(HELP_TEXT, format=None)

    @router.message_created(Command("me"))
    async def me(event: MessageCreated, profile: User) -> None:
        registered_at = profile.created_at.astimezone(UTC).strftime(
            "%d.%m.%Y %H:%M:%S UTC",
        )
        username = (
            f"@{profile.username}" if profile.username else "не задан"
        )
        await event.answer(
            f"ID: {profile.id}\n"
            f"Имя: {profile.first_name}\n"
            f"Username: {username}\n"
            f"Регистрация: {registered_at}",
            format=None,
        )

    return router
