from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from .config import load_config
from .db import connect, init_db
from .middlewares.user_message_cleanup import UserMessageCleanupMiddleware
from .routers.admin import router as admin_router
from .routers.game import router as game_router
from .routers.menu import router as menu_router
from .routers.start import router as start_router
from .routers.profile import router as profile_router


async def _run() -> None:
    cfg = load_config()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    bot = Bot(
        token=cfg.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    conn = await connect("bot.sqlite3")
    await init_db(conn)

    dp = Dispatcher(storage=MemoryStorage())

    # Inject db connection as dependency
    dp["conn"] = conn
    dp["config"] = cfg

    # Оставляем только первое /start от пользователя, все остальные его сообщения чистим.
    dp.message.middleware(UserMessageCleanupMiddleware())

    dp.include_router(start_router)
    dp.include_router(menu_router)
    dp.include_router(game_router)
    dp.include_router(profile_router)
    dp.include_router(admin_router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, conn=conn, config=cfg)


def main() -> None:
    asyncio.run(_run())


