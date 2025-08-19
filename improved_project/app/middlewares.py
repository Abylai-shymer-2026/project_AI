from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram.utils.chat_action import ChatActionSender


class TypingMiddleware(BaseMiddleware):
    """Send 'typing' action while processing updates."""

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        bot = data.get("bot")
        chat_id = None
        if isinstance(event, Message):
            chat_id = event.chat.id
        elif isinstance(event, CallbackQuery) and event.message:
            chat_id = event.message.chat.id

        if bot and chat_id:
            async with ChatActionSender.typing(bot, chat_id):
                return await handler(event, data)
        return await handler(event, data)
