# app/middlewares.py
from __future__ import annotations

from typing import Any, Callable, Awaitable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from aiogram.utils.chat_action import ChatActionSender
from aiogram.exceptions import TelegramAPIError


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
