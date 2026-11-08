"""Отправка сообщений с учётом ограничений MAX."""

from asyncio import Lock, sleep
from pathlib import Path
from time import monotonic

from loguru import logger
from maxo.types import (
    AudioAttachmentRequest,
    InlineKeyboardAttachmentRequest,
    PhotoAttachmentRequest,
)
from maxo.types.facades.attachments import AttachmentsFacade
from maxo.utils.upload_media import FSInputFile

from src.keyboards import with_help


class MessageSender:
    def __init__(self):
        self.locks = {}
        self.last_sent = {}

    async def send(
        self, bot, user_id, text, buttons=None, image_path=None,
        media_type=None, media_token=None,
    ):
        buttons = with_help(buttons)
        menu = InlineKeyboardAttachmentRequest.factory(buttons)
        attachments = [menu]
        if media_token:
            if media_type == "audio":
                audio = AudioAttachmentRequest.factory(media_token)
                attachments = [audio]
            elif media_type == "image":
                image = PhotoAttachmentRequest.factory(
                    token=media_token,
                )
                attachments.append(image)
        elif image_path:
            # Совместимость с уже выданными старыми заданиями.
            image = Path(image_path)
            if image.is_file():
                facade = AttachmentsFacade().as_(bot)
                attachments = await facade.build_attachments(
                    base=attachments,
                    files=[FSInputFile.image(image)],
                )
            else:
                text += (
                    "\nИзображение временно недоступно. "
                    "Сообщи капитану."
                )

        parts = []
        while len(text) > 4000:
            end = text.rfind("\n", 0, 4000)
            if end < 1:
                end = 4000
            parts.append(text[:end])
            text = text[end:].lstrip("\n")
        parts.append(text)

        messages = []
        for number, part in enumerate(parts):
            message_attachments = []
            if number == len(parts) - 1:
                message_attachments = list(attachments)
            messages.append((part, message_attachments))
        if media_type == "audio" and media_token:
            # Аудио должно быть единственным вложением сообщения.
            messages.append((
                "Введи свой ответ текстовым сообщением.", [menu],
            ))

        if user_id not in self.locks:
            self.locks[user_id] = Lock()
        async with self.locks[user_id]:
            for part, message_attachments in messages:
                delay = self.last_sent.get(user_id, 0)
                delay = delay + 0.55 - monotonic()
                if delay > 0:
                    await sleep(delay)
                await bot.send_message(
                    user_id=user_id,
                    text=part,
                    attachments=message_attachments,
                    format=None,
                )
                self.last_sent[user_id] = monotonic()

    async def notify(self, bot, user_id, text, buttons=None):
        try:
            await self.send(bot, user_id, text, buttons)
        except Exception:
            logger.exception(
                "Не доставлено уведомление игроку {}", user_id,
            )
