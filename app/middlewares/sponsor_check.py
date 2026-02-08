from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

import aiosqlite
from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message

from ..config import Config
from ..routers.start import ensure_start_sponsors_subscribed, sponsor_link
from ..keyboards import kb_sponsors_list, kb_check_subscriptions
from ..ui import edit_or_recreate


class SponsorCheckMiddleware(BaseMiddleware):
    """
    Проверяет подписку на старт-спонсоры при любом взаимодействии с ботом.
    Если пользователь не подписан и нет заявки - показывает экран с требованием подписки.
    Админы игнорируются.
    """

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        bot: Bot | None = data.get("bot")
        conn: aiosqlite.Connection | None = data.get("conn")
        config: Config | None = data.get("config")

        from_user = getattr(event, "from_user", None)
        if not bot or not conn or not from_user:
            return await handler(event, data)

        # Админы пропускаются
        is_admin = bool(config and from_user.id in config.admin_ids)
        if is_admin:
            return await handler(event, data)

        # Проверяем подписку на старт-спонсоры
        ok, sponsors, missing_channels = await ensure_start_sponsors_subscribed(bot, conn, from_user.id)
        
        # Если нет старт-спонсоров, пропускаем проверку
        if not sponsors or len(sponsors) == 0:
            return await handler(event, data)
        
        # Если пользователь не подписан на все каналы - блокируем доступ
        # Проверяем есть ли каналы для подписки
        has_channels_to_check = any(
            ((s["type"] or "channel").lower() if "type" in s.keys() else "channel") == "channel"
            and int(s["channel_id"]) != 0
            for s in sponsors
        )
        
        # Если есть каналы для проверки и пользователь не подписан - блокируем
        if has_channels_to_check and not ok:
            # Пользователь не подписан - показываем экран с требованием подписки
            # Но не блокируем команду /start и callback'и проверки подписок
            if isinstance(event, Message):
                # Для команд /start не показываем это (там своя логика)
                if event.text and event.text.startswith("/start"):
                    return await handler(event, data)
            elif isinstance(event, CallbackQuery):
                # Не блокируем callback'и проверки подписок, выбора подарка и навигации по экрану подписки
                callback_data = getattr(event, "data", "")
                allowed_callbacks = (
                    "start:check_subs", 
                    "start:choose_gift", 
                    "start:back",
                    "tasks:check_subs"
                )
                if callback_data in allowed_callbacks:
                    return await handler(event, data)
            
            # Определяем chat_id из события
            chat_id = None
            if isinstance(event, Message):
                chat_id = event.chat.id
            elif isinstance(event, CallbackQuery) and event.message:
                chat_id = event.message.chat.id
            
            if chat_id:
                # Строим список спонсоров для отображения
                has_channels = any(
                    ((s["type"] or "channel").lower() if "type" in s.keys() else "channel") == "channel"
                    and int(s["channel_id"]) != 0
                    for s in sponsors
                )
                rows: list[dict] = []
                for s in sponsors:
                    type_ = (s["type"] or "channel").lower() if "type" in s.keys() else "channel"
                    if type_ in ("bot", "link") and not has_channels:
                        continue
                    link = sponsor_link(s) or ""
                    if link:
                        rows.append({"title": str(s["title"]), "link": link})

                text = (
                    "🎁 Выберите свой подарок!\n\n"
                    "Ниже список спонсоров. Подпишитесь на все каналы (или отправьте заявку на вступление), "
                    "затем нажмите «Проверить подписки»."
                )
                
                # Если это callback - редактируем сообщение, если message - отправляем новое
                if isinstance(event, CallbackQuery):
                    await event.answer()
                    await edit_or_recreate(
                        bot=bot,
                        conn=conn,
                        user_id=from_user.id,
                        chat_id=chat_id,
                        text=text,
                        reply_markup=kb_sponsors_list(rows) if rows else kb_check_subscriptions(),
                        screen="start:subs",
                        payload=None,
                    )
                    return  # Прерываем выполнение обработчика
                elif isinstance(event, Message):
                    # Для других сообщений показываем требование подписки
                    await edit_or_recreate(
                        bot=bot,
                        conn=conn,
                        user_id=from_user.id,
                        chat_id=chat_id,
                        text=text,
                        reply_markup=kb_sponsors_list(rows) if rows else kb_check_subscriptions(),
                        screen="start:subs",
                        payload=None,
                    )
                    return  # Прерываем выполнение обработчика

        return await handler(event, data)

