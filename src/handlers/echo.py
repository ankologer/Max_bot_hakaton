"""Повторение остальных сообщений."""

from maxo import Router
from maxo.types import MessageCreated


def create_router() -> Router:
    """Создать эхо, подключаемое после команд."""
    router = Router(name="echo")

    @router.message_created()
    async def echo(event: MessageCreated) -> None:
        text = event.text
        await event.answer(
            text if text else (
                "Отправь текстовое сообщение, и я повторю его."
            ),
            format=None,
        )

    return router
