from __future__ import annotations

from typing import Any, Awaitable, Callable

import aiosqlite
from aiogram import BaseMiddleware
from aiogram.types import Message

from ..repo import get_start_message_id


class UserMessageCleanupMiddleware(BaseMiddleware):
    """
    Enforces: one user message (first /start) + one bot UI message.
    Deletes any subsequent user messages, but still lets handlers run.
    """

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        conn: aiosqlite.Connection | None = data.get("conn")
        user = event.from_user
        if conn and user:
            start_msg_id = await get_start_message_id(conn, user.id)

            # Если первый раз и это /start — ничего не трогаем.
            if start_msg_id is None and (event.text or "").startswith("/start"):
                return await handler(event, data)

            # Если стартовое сообщение уже зафиксировано —
            # оставляем только его, все остальные сообщения пользователя удаляем.
            if start_msg_id is not None and event.message_id != start_msg_id:
                try:
                    await event.delete()
                except Exception:
                    pass

        return await handler(event, data)


