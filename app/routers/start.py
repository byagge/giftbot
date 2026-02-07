from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

import aiosqlite

import asyncio

from ..keyboards import kb_check_subscriptions, kb_menu, kb_sponsors_list, kb_start
from ..repo import (
    add_attempts,
    get_active_start_sponsors,
    get_start_message_id,
    get_user,
    is_user_banned,
    set_start_message_id,
    set_ui_state,
    touch_user_activity,
    upsert_user,
)
from ..ui import edit_or_recreate

router = Router(name="start")


def sponsor_link(row: aiosqlite.Row) -> str | None:
    if row["invite_link"]:
        return str(row["invite_link"])
    if row["channel_username"]:
        u = str(row["channel_username"]).lstrip("@")
        return f"https://t.me/{u}"
    return None


async def is_subscribed(bot: Bot, user_id: int, channel_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ("creator", "administrator", "member")
    except Exception:
        return False


async def ensure_start_sponsors_subscribed(bot: Bot, conn: aiosqlite.Connection, user_id: int) -> tuple[bool, list[aiosqlite.Row], list[aiosqlite.Row]]:
    """
    Проверяем подписку только по каналам, но возвращаем также полный список спонсоров.
    :return: ok, all_sponsors, missing_channel_sponsors
    """
    sponsors = await get_active_start_sponsors(conn)
    missing_channels: list[aiosqlite.Row] = []
    for s in sponsors:
        type_ = (s["type"] or "channel").lower() if "type" in s.keys() else "channel"
        channel_id = int(s["channel_id"])
        # Проверку подписки реально можно сделать только для каналов
        if type_ == "channel" and channel_id != 0:
            ok = await is_subscribed(bot, user_id, channel_id)
            if not ok:
                missing_channels.append(s)
    return (len(missing_channels) == 0), sponsors, missing_channels


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, conn: aiosqlite.Connection) -> None:
    u = message.from_user
    if not u:
        return
    existing = await get_user(conn, u.id)
    await upsert_user(conn, u.id, u.username, u.first_name, u.last_name)

    # Проверка бана
    if await is_user_banned(conn, u.id):
        await message.answer("⛔ Доступ к боту для вас ограничен. Обратитесь к администратору.")
        return

    # Зафиксировать активность (для напоминаний) сразу после регистрации/старта
    await touch_user_activity(conn, u.id)

    # Зафиксировать первое /start как "главное" пользовательское сообщение
    start_msg_id = await get_start_message_id(conn, u.id)
    if start_msg_id is None and (message.text or "").startswith("/start"):
        await set_start_message_id(conn, u.id, message.message_id)

    if existing is None:
        # Новый пользователь — показываем экран "ты выиграл подарок"
        name = u.first_name or u.full_name or "друг"
        text = (
            f"{name}, поздравляю, ты выиграл подарок! 🎁\n\n"
            "Скорее жми на кнопку «🎁 Выбрать подарок» и получай какой захочешь!"
        )
        # Для команд всегда создаем новое сообщение
        msg = await bot.send_message(
            chat_id=message.chat.id,
            text=text,
            reply_markup=kb_start(),
            disable_web_page_preview=True,
        )
        await set_ui_state(conn, u.id, message.chat.id, msg.message_id, "start:hello_new", None)
    else:
        # Уже есть в БД — сразу меню
        from ..repo import get_user_attempts

        attempts = await get_user_attempts(conn, u.id)
        text = (
            f"🎮 Попыток: <b>{attempts}</b>\n\n"
            "Как получить попытки:\n"
            "• 🎯 Задания — +1 за каждое\n"
            "• 🛒 Покупка — 5✨ = 1 попытка\n"
            "• 🤝 Пригласить друга — +4 за каждого\n\n"
            "Выберите действие ниже 👇"
        )
        # Для команд всегда создаем новое сообщение
        msg = await bot.send_message(
            chat_id=message.chat.id,
            text=text,
            reply_markup=kb_menu(),
            disable_web_page_preview=True,
        )
        await set_ui_state(conn, u.id, message.chat.id, msg.message_id, "menu:home", None)


@router.callback_query(F.data == "start:back")
async def start_back(cb: CallbackQuery, bot: Bot, conn: aiosqlite.Connection) -> None:
    if not cb.from_user:
        return
    await cb.answer()
    text = (
        "Привет! Это бот с игрой и подарками.\n\n"
        "Нажми «Выбрать подарок», затем подпишись на стартовых спонсоров."
    )
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=text,
        reply_markup=kb_start(),
        screen="start:hello",
        payload=None,
    )


@router.callback_query(F.data == "start:choose_gift")
async def choose_gift(cb: CallbackQuery, bot: Bot, conn: aiosqlite.Connection) -> None:
    # На этом этапе — упрощённо: сразу ведём к обязательной подписке.
    if not cb.from_user:
        return
    await cb.answer()

    ok, sponsors, _ = await ensure_start_sponsors_subscribed(bot, conn, cb.from_user.id)
    if ok:
        # уже подписан на старт-спонсоров — просто меню
        from ..repo import get_user_attempts

        attempts = await get_user_attempts(conn, cb.from_user.id)
        text = (
            f"🎮 Попыток: <b>{attempts}</b>\n\n"
            "Как получить попытки:\n"
            "• 🎯 Задания — +1 за каждое\n"
            "• 🛒 Покупка — 5✨ = 1 попытка\n"
            "• 🤝 Пригласить друга — +4 за каждого\n\n"
            "Выберите действие ниже 👇"
        )
        await edit_or_recreate(
            bot=bot,
            conn=conn,
            user_id=cb.from_user.id,
            chat_id=cb.message.chat.id,
            text=text,
            reply_markup=kb_menu(),
            screen="menu:home",
            payload=None,
        )
        return

    # не подписан — показываем задания со стартовыми спонсорами
    # Показываем и каналы, и ботов/сайты, но проверка идёт только по каналам.
    from ..keyboards import kb_sponsors_list

    has_channels = any(
        ((s["type"] or "channel").lower() if "type" in s.keys() else "channel") == "channel"
        and int(s["channel_id"]) != 0
        for s in sponsors
    )
    rows: list[dict] = []
    for s in sponsors:
        type_ = (s["type"] or "channel").lower() if "type" in s.keys() else "channel"
        # Если вообще нет каналов — сайты/боты не отображаем
        if type_ in ("bot", "link") and not has_channels:
            continue
        link = sponsor_link(s) or ""
        if link:
            rows.append({"title": str(s["title"]), "link": link})

    text = "🎁 Выберите свой подарок!\n\nНиже список спонсоров. Подпишитесь на все каналы, затем нажмите «Проверить подписки»."
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=text,
        reply_markup=kb_sponsors_list(rows) if rows else kb_check_subscriptions(),
        screen="start:subs",
        payload=None,
    )


@router.callback_query(F.data == "start:check_subs")
async def check_subs(cb: CallbackQuery, bot: Bot, conn: aiosqlite.Connection) -> None:
    if not cb.from_user:
        return
    await cb.answer()

    ok, sponsors, _ = await ensure_start_sponsors_subscribed(bot, conn, cb.from_user.id)
    if ok:
        # имитация "собираем задания"
        await edit_or_recreate(
            bot=bot,
            conn=conn,
            user_id=cb.from_user.id,
            chat_id=cb.message.chat.id,
            text="Секунду, собираем задания для вас....",
            reply_markup=None,
            screen="start:loading_tasks",
            payload=None,
        )
        await asyncio.sleep(1.5)

        text = (
            "✨ Чтобы забрать подарок 🎁\n\n"
            "Тебе нужно выполнить все задания со спонсорами (подписаться на все каналы).\n\n"
        )
        # выдаём 3 попытки и отправляем меню
        await add_attempts(conn, cb.from_user.id, 3)
        from ..repo import get_user_attempts

        attempts = await get_user_attempts(conn, cb.from_user.id)
        text = (
            text
            + "\n\n"
            f"🎮 Попыток: <b>{attempts}</b>\n\n"
            "Как получить попытки:\n"
            "• 🎯 Задания — +1 за каждое\n"
            "• 🛒 Покупка — 5✨ = 1 попытка\n"
            "• 🤝 Пригласить друга — +4 за каждого\n\n"
            "Выберите действие ниже 👇"
        )
        await edit_or_recreate(
            bot=bot,
            conn=conn,
            user_id=cb.from_user.id,
            chat_id=cb.message.chat.id,
            text=text,
            reply_markup=kb_menu(),
            screen="menu:home",
            payload=None,
        )
    else:
        from ..keyboards import kb_sponsors_list

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

        text = "❌ Не на все каналы есть подписка.\n\nПодпишись на все каналы и проверь ещё раз."
        await edit_or_recreate(
            bot=bot,
            conn=conn,
            user_id=cb.from_user.id,
            chat_id=cb.message.chat.id,
            text=text,
            reply_markup=kb_sponsors_list(rows) if rows else kb_check_subscriptions(),
            screen="start:subs",
            payload=None,
        )


