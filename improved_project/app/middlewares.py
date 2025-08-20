# app/middlewares.py
from __future__ import annotations

from typing import Any, Callable, Awaitable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from aiogram.utils.chat_action import ChatActionSender
from aiogram.exceptions import TelegramAPIError
import logging


class TypingMiddleware(BaseMiddleware):
    """
    Всегда показывает 'печатает…' во время обработки апдейта.
    Работает и для обычных сообщений, и для callback-кнопок.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        bot = data.get("bot")
        chat_id: Optional[int] = None

        if isinstance(event, Message):
            chat_id = event.chat.id
        elif isinstance(event, CallbackQuery) and event.message:
            chat_id = event.message.chat.id

        if bot and chat_id:
            try:
                async with ChatActionSender.typing(bot=bot, chat_id=chat_id):
                    return await handler(event, data)
            except TelegramAPIError:
                # Если action не прошёл (например, слишком часто) — продолжаем без него
                return await handler(event, data)
        else:
            return await handler(event, data)


class LoggingMiddleware(BaseMiddleware):
    """
    Минимальное логирование апдейтов: кто, что сказал и какой callback нажал.
    Полезно для отладки диалогов и состояний.
    """

    def __init__(self) -> None:
        self._log = logging.getLogger("updates")

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        try:
            if isinstance(event, Message):
                self._log.info("MSG from %s (%s): %s", getattr(event.from_user, "id", None), getattr(event.from_user, "username", None), event.text)
            elif isinstance(event, CallbackQuery):
                self._log.info("CB from %s (%s): %s", getattr(event.from_user, "id", None), getattr(event.from_user, "username", None), event.data)
        except Exception:
            pass
        return await handler(event, data)
