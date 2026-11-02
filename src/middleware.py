"""Первичный обработка событий (middleware)"""

from asyncio import Lock, get_running_loop
from typing import Any
from weakref import WeakValueDictionary

from loguru import logger
from maxo.routing.ctx import Ctx
from maxo.routing.interfaces.middleware import NextMiddleware
from maxo.routing.sentinels import UNHANDLED
from maxo.types import BotStarted, MessageCreated

from src.users import save_user

PROCESSED_UPDATE_TTL = 60 * 60 # 1 час


class ProcessingMiddleware:
    def __init__(self) -> None:
        # Неактивные блокировки удаляются после последней задачи.
        self._locks: WeakValueDictionary[
            tuple[int, int], Lock
        ] = WeakValueDictionary()
        self._processed: dict[str, float] = {}

    def _forget_processed(self, key: str, expires_at: float) -> None:
        if self._processed.get(key) == expires_at:
            self._processed.pop(key)

    async def __call__(
        self,
        update: MessageCreated | BotStarted,
        ctx: Ctx,
        next: NextMiddleware[Any],
    ) -> Any:
        bot_id: int = ctx["bot"].state.info.user_id
        if isinstance(update, MessageCreated):
            user_id = update.message.unsafe_sender.user_id
            message_id = update.message.body.mid
            chat_id = update.message.recipient.chat_id
            key = f"{bot_id}:message:{chat_id}:{message_id}"
        else:
            user_id = update.user.user_id
            key = (
                f"{bot_id}:started:{update.chat_id}:{user_id}:"
                f"{update.timestamp.isoformat()}"
            )

        lock_key = (bot_id, user_id)
        # Между поиском и добавлением нет await:
        # две задачи не создадут разные lock для одного пользователя.
        lock = self._locks.get(lock_key)
        if lock is None:
            lock = Lock()
            self._locks[lock_key] = lock

        async with lock:
            loop = get_running_loop()
            expires_at = self._processed.get(key, 0.0)
            if expires_at > loop.time():
                logger.info(
                    "Повтор события пропущен: user_id={} key={}",
                    user_id,
                    key,
                )
                return None

            logger.info(
                "Обработка события: user_id={} key={}", user_id, key
            )
            result = await next(ctx)
            if result is not UNHANDLED:
                # При исключении или отмене до этой точки
                # событие не помечается обработанным.
                expires_at = loop.time() + PROCESSED_UPDATE_TTL
                self._processed[key] = expires_at
                loop.call_later(
                    PROCESSED_UPDATE_TTL,
                    self._forget_processed,
                    key,
                    expires_at,
                )
                logger.info(
                    "Событие обработано: user_id={} key={}",
                    user_id,
                    key,
                )
            return result


class UserContextMiddleware:
    async def __call__(
        self,
        update: MessageCreated | BotStarted,
        ctx: Ctx,
        next: NextMiddleware[Any],
    ) -> Any:
        if isinstance(update, MessageCreated):
            user = update.message.unsafe_sender
        else:
            user = update.user
        ctx["profile"] = await save_user(user)
        return await next(ctx)
