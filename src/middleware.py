"""Последовательная обработка событий и сохранение пользователей."""

from asyncio import Lock
from time import monotonic

from loguru import logger
from maxo.routing.sentinels import UNHANDLED
from maxo.types import MessageCallback, MessageCreated

from src.users import save_user

PROCESSED_UPDATE_TTL = 60 * 60  # 1 час


class ProcessingMiddleware:
    def __init__(self):
        self.locks = {}
        self.processed = {}

    async def __call__(self, update, ctx, next):
        bot_id = ctx["bot"].state.info.user_id
        if isinstance(update, MessageCreated):
            user_id = update.message.unsafe_sender.user_id
            message_id = update.message.body.mid
            chat_id = update.message.recipient.chat_id
            key = f"{bot_id}:message:{chat_id}:{message_id}"
        elif isinstance(update, MessageCallback):
            user_id = update.user.user_id
            key = f"{bot_id}:callback:{update.callback_id}"
        else:
            user_id = update.user.user_id
            key = (
                f"{bot_id}:started:{update.chat_id}:{user_id}:"
                f"{update.timestamp.isoformat()}"
            )

        # События одного игрока меняют БД по очереди.
        lock_key = (bot_id, user_id)
        if lock_key not in self.locks:
            self.locks[lock_key] = Lock()
        async with self.locks[lock_key]:
            now = monotonic()
            for old_key in list(self.processed):
                if self.processed[old_key] <= now:
                    del self.processed[old_key]
            if key in self.processed:
                logger.info("Повтор события пропущен: {}", key)
                return None

            logger.info("Обработка события: {}", key)
            result = await next(ctx)
            if result is not UNHANDLED:
                # При ошибке событие можно обработать повторно.
                expires_at = monotonic() + PROCESSED_UPDATE_TTL
                self.processed[key] = expires_at
                logger.info("Событие обработано: {}", key)
            return result


class UserContextMiddleware:
    async def __call__(self, update, ctx, next):
        if isinstance(update, MessageCreated):
            user = update.message.unsafe_sender
        else:
            user = update.user
        ctx["profile"] = await save_user(user)
        return await next(ctx)
