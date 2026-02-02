from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardMarkup

import aiosqlite

from .repo import get_ui_state, set_ui_state


async def edit_or_recreate(
    *,
    bot: Bot,
    conn: aiosqlite.Connection,
    user_id: int,
    chat_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
    screen: str,
    payload: dict[str, Any] | None = None,
) -> int:
    """
    Ensures "single message UI": edits existing stored message if possible,
    otherwise creates a new one and persists (chat_id, message_id).
    Returns message_id of the UI message.
    """
    state = await get_ui_state(conn, user_id)
    if state and int(state["chat_id"]) == int(chat_id):
        message_id = int(state["message_id"])
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
            await set_ui_state(conn, user_id, chat_id, message_id, screen, payload)
            return message_id
        except TelegramBadRequest as e:
            # "message is not modified" should be treated as success.
            if "message is not modified" in str(e).lower():
                await set_ui_state(conn, user_id, chat_id, message_id, screen, payload)
                return message_id
            # message not found / can't be edited / etc -> fallback to recreate
        except TelegramForbiddenError:
            # bot blocked or no rights
            raise

    msg = await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )
    await set_ui_state(conn, user_id, chat_id, msg.message_id, screen, payload)
    return msg.message_id


