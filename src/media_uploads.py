"""Загрузка документов и создание медиа-вложений MAX."""

from io import BytesIO

from maxo.omit import is_defined
from maxo.types import AudioAttachmentRequest, PhotoAttachmentRequest
from maxo.types.facades.attachments import AttachmentsFacade
from maxo.utils.upload_media import BufferedInputFile

MAX_TEXT_BYTES = 1024 * 1024
MAX_AUDIO_BYTES = 20 * 1024 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class LimitedBuffer(BytesIO):
    """Ограничение проверяется при записи каждого блока загрузки."""

    def __init__(self, limit):
        super().__init__()
        self.limit = limit

    def write(self, content):
        if self.tell() + len(content) > self.limit:
            megabytes = self.limit // (1024 * 1024)
            raise ValueError(
                f"Размер файла не должен превышать {megabytes} МБ."
            )
        return super().write(content)


async def download_bytes(
    bot, payload, max_bytes, declared_size=None,
):
    """Скачать в память с проверкой размера до и во время загрузки."""
    if declared_size is not None and declared_size > max_bytes:
        megabytes = max_bytes // (1024 * 1024)
        raise ValueError(
            f"Размер файла не должен превышать {megabytes} МБ."
        )
    with LimitedBuffer(max_bytes) as destination:
        await bot.download(
            payload, destination=destination, timeout=30,
        )
        content = destination.getvalue()
    if not content:
        raise ValueError("Загруженный файл пуст.")
    return content


async def upload_media_token(
    bot, payload, media_type, filename, declared_size=None,
):
    """Получить токен аудио/фото, пригодный для отправки игрокам."""
    if media_type == "audio":
        limit = MAX_AUDIO_BYTES
        expected_type = AudioAttachmentRequest
    elif media_type == "image":
        limit = MAX_IMAGE_BYTES
        expected_type = PhotoAttachmentRequest
    else:
        raise ValueError("Допустимы только аудио и изображения.")

    content = await download_bytes(
        bot, payload, limit, declared_size,
    )
    if media_type == "audio":
        file = BufferedInputFile.audio(content, filename)
    else:
        file = BufferedInputFile.image(content, filename)

    # Токен документа нельзя использовать как токен аудио или фото.
    # SDK загружает байты в endpoint нужного типа вложения.
    facade = AttachmentsFacade().as_(bot)
    attachments = await facade.build_attachments(
        base=[], files=[file],
    )
    for attachment in attachments:
        if isinstance(attachment, expected_type):
            token = attachment.payload.token
            if is_defined(token) and isinstance(token, str) and token:
                return token
    raise ValueError("MAX не вернул токен загруженного медиа.")
