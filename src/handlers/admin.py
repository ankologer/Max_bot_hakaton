"""Команды администратора и загрузка банка вопросов с медиа."""

from pathlib import PurePath
from re import fullmatch
from urllib.parse import urlsplit

from loguru import logger
from maxo import Bot, Router
from maxo.routing.filters import Command, SyncFilter
from maxo.types import (
    AudioAttachment,
    FileAttachment,
    MessageCreated,
    PhotoAttachment,
)

from src.game import GameError
from src.media_uploads import (
    MAX_TEXT_BYTES,
    download_bytes,
    upload_media_token,
)
from src.models import Player, Question, Team, User
from src.questions import import_questions, set_question_media

AUDIO_EXTENSIONS = {"mp3", "wav", "ogg", "m4a", "opus"}
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MEDIA_USAGE = (
    "Прикрепи одно аудио с подписью /media 2 N "
    "или одну картинку с подписью /media 3 N. "
    "N — номер вопроса, начиная с 1. "
    "Документы можно отправить без подписи: "
    "r2_N.mp3 или r3_N.jpg."
)


def parse_media_filename(filename):
    """Извлечь раунд и номер вопроса из r2_N.mp3 или r3_N.jpg."""
    match = fullmatch(
        r"r([23])_([1-9][0-9]{0,8})\.([A-Za-z0-9]+)", filename,
    )
    if match is None:
        raise GameError(
            "Название медиа: r2_N.mp3 для аудио "
            "или r3_N.jpg для картинки. N — номер вопроса."
        )
    round_no = int(match[1])
    validate_extension(round_no, filename)
    return round_no, int(match[2])


def validate_extension(round_no, filename):
    extension = PurePath(filename).suffix.lstrip(".").lower()
    allowed = IMAGE_EXTENSIONS
    if round_no == 2:
        allowed = AUDIO_EXTENSIONS
    if extension not in allowed:
        if round_no == 2:
            raise GameError(
                "Для раунда 2 нужны mp3, wav, ogg, m4a или opus."
            )
        raise GameError(
            "Для раунда 3 нужны jpg, jpeg, png или webp."
        )


def parse_media_caption(text):
    parts = text.split()
    if len(parts) != 3 or parts[1] not in {"2", "3"}:
        raise GameError(MEDIA_USAGE)
    number = parts[2]
    if not fullmatch(r"[1-9][0-9]{0,8}", number):
        raise GameError("Номер вопроса должен быть целым от 1.")
    return int(parts[1]), int(number)


def has_attachment(event):
    return bool(event.message.body.attachments)


def native_filename(payload, round_no, position):
    """Сохранить известное расширение URL нативного вложения."""
    extension = PurePath(urlsplit(payload.url).path).suffix
    allowed = IMAGE_EXTENSIONS
    fallback = ".jpg"
    if round_no == 2:
        allowed = AUDIO_EXTENSIONS
        fallback = ".mp3"
    if extension.lstrip(".").lower() not in allowed:
        extension = fallback
    return f"r{round_no}_{position}{extension}"


class AdminHandlers:
    def __init__(self, ui):
        self.ui = ui

    def require_admin(self, user_id):
        if user_id not in self.ui.admin_ids:
            raise GameError(
                "Эта команда и загрузка файлов доступны "
                "только администратору."
            )

    async def next_round(self, bot, user_id, code):
        self.require_admin(user_id)
        if code:
            team = await Team.get_or_none(
                invite_code=code.strip().upper(),
            )
        else:
            team = await self.ui.service.get_team(user_id)
        if team is None:
            raise GameError(
                "Команда не найдена. Укажи её код: "
                "/next_round КОД."
            )
        team = await self.ui.service.advance_round(team.id)
        score = await self.ui.service.team_score(team.id)
        text = "Администратор завершил текущий раунд.\n"
        if score.finished:
            text += "Игра завершена. Открой /results."
        else:
            text += (
                f"Теперь раунд {score.current_round}. "
                "Открой /tasks для задания на сегодня."
            )
        await self.ui.send(bot, user_id, text)
        members = await Player.filter(team_id=team.id)
        for member in members:
            if member.id != user_id:
                await self.ui.notify(bot, member.id, text)

    async def upload(self, event, bot, user_id, target=None):
        # Проверка прав выполняется до разбора файла и скачивания.
        self.require_admin(user_id)
        attachments = event.message.body.attachments or []
        if len(attachments) != 1:
            raise GameError(
                "Отправь один файл за раз. " + MEDIA_USAGE
            )
        attachment = attachments[0]
        filename = None
        size = None

        if isinstance(attachment, FileAttachment):
            filename = attachment.filename
            size = attachment.size
            if filename in {"r1.txt", "r2.txt", "r3.txt"}:
                if target is not None:
                    raise GameError(
                        "TXT с вопросами отправь без команды /media."
                    )
                await self.upload_text(bot, user_id, attachment)
                return
            if target is None:
                target = parse_media_filename(filename)
            else:
                validate_extension(target[0], filename)
        elif isinstance(attachment, AudioAttachment):
            if target is None or target[0] != 2:
                raise GameError(MEDIA_USAGE)
        elif isinstance(attachment, PhotoAttachment):
            if target is None or target[0] != 3:
                raise GameError(MEDIA_USAGE)
        else:
            raise GameError(
                "Нужен TXT, аудио или изображение. " + MEDIA_USAGE
            )

        round_no, position = target
        question = await Question.get_or_none(
            round_no=round_no, position=position,
        )
        if question is None:
            raise GameError(
                f"В раунде {round_no} нет вопроса №{position}. "
                f"Сначала загрузи r{round_no}.txt."
            )
        media_type = "image"
        title = "Изображение"
        if round_no == 2:
            media_type = "audio"
            title = "Аудио"
        if filename is None:
            filename = native_filename(
                attachment.payload, round_no, position,
            )
        token = await upload_media_token(
            bot, attachment.payload, media_type, filename, size,
        )
        await set_question_media(
            round_no, position, media_type, token,
        )
        await self.ui.send(
            bot, user_id,
            f"{title} для раунда {round_no}, "
            f"вопроса №{position} сохранено. "
            "Уже выданные задания сохранены.",
        )

    async def upload_text(self, bot, user_id, attachment):
        content = await download_bytes(
            bot, attachment.payload,
            MAX_TEXT_BYTES, attachment.size,
        )
        round_no, count = await import_questions(
            attachment.filename, content,
        )
        text = (
            f"Вопросы раунда {round_no} обновлены: {count} шт. "
            "Уже выданные задания сохранены."
        )
        if round_no in {2, 3}:
            text += (
                "\nЗагрузи медиа для каждого вопроса этого раунда."
            )
        await self.ui.send(bot, user_id, text)

    async def report_error(self, bot, user_id, error):
        await self.ui.send(bot, user_id, str(error))


def create_router(ui):
    router = Router(name="admin")
    handlers = AdminHandlers(ui)

    @router.message_created(Command("admin", ignore_case=True))
    async def admin(event: MessageCreated, bot: Bot, profile: User):
        try:
            handlers.require_admin(profile.id)
            await ui.show_help(bot, profile.id)
        except GameError as error:
            await handlers.report_error(bot, profile.id, error)

    @router.message_created(Command("next_round", ignore_case=True))
    async def next_round(
        event: MessageCreated, bot: Bot, profile: User,
    ):
        parts = (event.text or "").split(maxsplit=1)
        code = ""
        if len(parts) > 1:
            code = parts[1]
        try:
            await handlers.next_round(bot, profile.id, code)
        except GameError as error:
            await handlers.report_error(bot, profile.id, error)

    @router.message_created(Command("media", ignore_case=True))
    async def media(event: MessageCreated, bot: Bot, profile: User):
        try:
            handlers.require_admin(profile.id)
            target = parse_media_caption(event.text or "")
            await handlers.upload(event, bot, profile.id, target)
        except (GameError, ValueError) as error:
            await handlers.report_error(bot, profile.id, error)
        except Exception:
            logger.exception("Не удалось загрузить медиа вопроса")
            await ui.send(
                bot, profile.id,
                "Не удалось загрузить медиа. Отправь файл ещё раз.",
            )

    @router.message_created(SyncFilter(has_attachment))
    async def upload(event: MessageCreated, bot: Bot, profile: User):
        try:
            await handlers.upload(event, bot, profile.id)
        except (GameError, ValueError) as error:
            await handlers.report_error(bot, profile.id, error)
        except Exception:
            logger.exception("Не удалось загрузить файл вопроса")
            await ui.send(
                bot, profile.id,
                "Не удалось загрузить файл. Отправь его ещё раз.",
            )

    return router
