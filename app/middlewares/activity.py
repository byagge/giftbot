from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

import aiosqlite
from aiogram import BaseMiddleware

from ..config import Config
from ..repo import touch_user_activity


class ActivityMiddleware(BaseMiddleware):
    """
    Отслеживает любую активность пользователя (сообщения, callback) и обновляет
    последнюю активность для системы напоминаний.
    Админы игнорируются.
    """

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        conn: aiosqlite.Connection | None = data.get("conn")
        config: Config | None = data.get("config")

        from_user = getattr(event, "from_user", None)
        if conn and from_user:
            is_admin = bool(config and from_user.id in config.admin_ids)
            if not is_admin:
                await touch_user_activity(conn, from_user.id)

        return await handler(event, data)


