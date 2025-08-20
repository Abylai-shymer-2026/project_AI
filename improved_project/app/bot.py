# app/bot.py
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from .config import settings
from .logger import setup_logging
from .routers import common as common_router
from .routers import influencers
from .middlewares import TypingMiddleware, LoggingMiddleware


async def main() -> None:
    setup_logging()
    log = logging.getLogger("bot")

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # Middlewares для логирования и "печатает..."
    dp.message.middleware(LoggingMiddleware())
    dp.callback_query.middleware(LoggingMiddleware())
    dp.message.middleware(TypingMiddleware())
    dp.callback_query.middleware(TypingMiddleware())

    # ПРАВИЛЬНЫЙ ПОРЯДОК:
    # Сначала подключаем роутер с состояниями (FSM)
    dp.include_router(influencers.router)
    # А затем - общий роутер для сообщений без состояния
    dp.include_router(common_router.router)

    log.info("Starting polling… (START_MODE=%s)", settings.START_MODE)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass