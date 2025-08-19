# app/bot.py
import asyncio, logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from .config import settings
from .logger import setup_logging
from .routers import common as common_router
from .routers import influencers
from .middlewares import TypingMiddleware

async def main() -> None:
    setup_logging()
    log = logging.getLogger("bootstrap")

    if not settings.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is empty — set it in your .env")

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(TypingMiddleware())
    dp.callback_query.middleware(TypingMiddleware())

    dp.include_router(common_router.router)
    dp.include_router(influencers.router)

    log.info("Starting polling… (START_MODE=%s)", settings.START_MODE)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
