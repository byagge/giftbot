from __future__ import annotations

import re

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup

from ..config import Config
from ..keyboards import kb_admin_menu, kb_admin_back
from ..repo import (
    add_attempts,
    delete_gift,
    delete_start_sponsor,
    delete_task_sponsor,
    get_gift,
    get_start_sponsor,
    get_task_sponsor,
    list_gifts,
    list_start_sponsors,
    list_task_sponsors,
    list_users,
    set_attempts,
    set_inventory_status,
    set_setting,
    set_ui_state,
    set_user_ban,
    upsert_user,
)
from ..ui import edit_or_recreate

router = Router(name="admin")


class AdminFlow(StatesGroup):
    add_start_sponsor = State()
    add_task_sponsor = State()
    add_gift = State()
    set_global_chance = State()
    edit_user_attempts = State()
    edit_start_sponsor = State()
    edit_task_sponsor = State()
    edit_gift = State()
    edit_user = State()
    broadcast = State()
    set_stars_price = State()


def _is_admin(cfg: Config, user_id: int) -> bool:
    return user_id in cfg.admin_ids


def _bool_emoji(v: int) -> str:
    return "✅" if v else "❌"


@router.message(Command("admin"))
async def admin_cmd(message: Message, bot, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not message.from_user:
        return
    if not _is_admin(config, message.from_user.id):
        return
    await state.clear()
    await upsert_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
    # Для команд всегда создаем новое сообщение
    msg = await bot.send_message(
        chat_id=message.chat.id,
        text="Админ-панель:",
        reply_markup=kb_admin_menu(),
        disable_web_page_preview=True,
    )
    await set_ui_state(conn, message.from_user.id, message.chat.id, msg.message_id, "admin:menu", None)


@router.callback_query(F.data == "admin:menu")
async def admin_menu_cb(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    await state.clear()
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text="Админ-панель:",
        reply_markup=kb_admin_menu(),
        screen="admin:menu",
        payload=None,
    )


@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    await state.set_state(AdminFlow.broadcast)
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=(
            "📨 <b>Рассылка</b>\n\n"
            "Отправь текст сообщения, которое будет разослано <b>всем пользователям</b>.\n"
            "Можно использовать HTML-разметку.\n\n"
            "Внимание: рассылка может занять некоторое время."
        ),
        reply_markup=kb_admin_back(),
        screen="admin:broadcast",
        payload=None,
    )


@router.callback_query(F.data == "admin:add_start_sponsor")
async def admin_add_start_sponsor(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    await state.set_state(AdminFlow.add_start_sponsor)
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=(
            "Отправь старт-спонсора в формате:\n\n"
            "<code>Название | тип(channel/bot/link) | channel_id(для channel, иначе 0) | @username(опц) | invite_link(опц)</code>\n\n"
            "Пример канала:\n"
            "<code>Спонсор 1 | channel | -1001234567890 | @mychannel | https://t.me/+xxxx</code>\n\n"
            "Пример бота:\n"
            "<code>Бот 1 | bot | 0 | @mybot | https://t.me/mybot</code>\n\n"
            "Пример ссылки:\n"
            "<code>Сайт | link | 0 | | https://example.com</code>"
        ),
        reply_markup=kb_admin_back(),
        screen="admin:add_start_sponsor",
        payload=None,
    )


@router.message(AdminFlow.add_start_sponsor)
async def admin_add_start_sponsor_msg(message: Message, bot, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not message.from_user or not _is_admin(config, message.from_user.id):
        return
    parts = [p.strip() for p in (message.text or "").split("|")]
    if len(parts) < 3:
        await message.answer("Формат неверный. Нужно минимум: Название | тип | channel_id")
        return
    title = parts[0]
    type_ = (parts[1] or "channel").lower()
    if type_ not in ("channel", "bot", "link"):
        await message.answer("Тип должен быть одним из: channel, bot, link")
        return
    try:
        channel_id = int(parts[2])
    except Exception:
        await message.answer("channel_id должен быть числом (для bot/link можно 0)")
        return
    username = parts[3] if len(parts) >= 4 and parts[3] else None
    invite_link = parts[4] if len(parts) >= 5 and parts[4] else None
    await conn.execute(
        "INSERT INTO start_sponsors(title, type, channel_id, channel_username, invite_link, is_active) VALUES(?, ?, ?, ?, ?, 1)",
        (title, type_, channel_id, username, invite_link),
    )
    await conn.commit()
    await state.clear()
    await message.answer(
        "✅ Старт-спонсор добавлен. Открой /admin для продолжения.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✖ Закрыть", callback_data="admin:close_notice")]
            ]
        ),
    )


@router.callback_query(F.data == "admin:add_task_sponsor")
async def admin_add_task_sponsor(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    await state.set_state(AdminFlow.add_task_sponsor)
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=(
            "Отправь спонсора (задание) в формате:\n\n"
            "<code>Название | тип(channel/bot/link) | channel_id(для channel, иначе 0) | бонус_попыток | @username(опц) | invite_link(опц)</code>\n\n"
            "Пример канала:\n"
            "<code>Спонсор 2 | channel | -1001234567890 | 1 | @mychannel |</code>\n\n"
            "Пример бота:\n"
            "<code>Бот 2 | bot | 0 | 1 | @mybot | https://t.me/mybot</code>\n\n"
            "Пример ссылки:\n"
            "<code>Сайт | link | 0 | 1 | | https://example.com</code>"
        ),
        reply_markup=kb_admin_back(),
        screen="admin:add_task_sponsor",
        payload=None,
    )


@router.message(AdminFlow.add_task_sponsor)
async def admin_add_task_sponsor_msg(message: Message, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not message.from_user or not _is_admin(config, message.from_user.id):
        return
    parts = [p.strip() for p in (message.text or "").split("|")]
    if len(parts) < 4:
        await message.answer("Формат неверный. Нужно минимум: Название | тип | channel_id | бонус_попыток")
        return
    title = parts[0]
    type_ = (parts[1] or "channel").lower()
    if type_ not in ("channel", "bot", "link"):
        await message.answer("Тип должен быть одним из: channel, bot, link")
        return
    try:
        channel_id = int(parts[2])
    except Exception:
        await message.answer("channel_id должен быть числом (для bot/link можно 0)")
        return
    try:
        bonus_attempts = int(parts[3])
    except Exception:
        await message.answer("bonus_попыток должен быть целым числом")
        return
    username = parts[4] if len(parts) >= 5 and parts[4] else None
    invite_link = parts[5] if len(parts) >= 6 and parts[5] else None
    await conn.execute(
        "INSERT INTO sponsors(title, type, channel_id, bonus_attempts, channel_username, invite_link, is_active) VALUES(?, ?, ?, ?, ?, ?, 1)",
        (title, type_, channel_id, bonus_attempts, username, invite_link),
    )
    await conn.commit()
    await state.clear()
    await message.answer(
        "✅ Спонсор (задание) добавлен. Открой /admin для продолжения.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✖ Закрыть", callback_data="admin:close_notice")]
            ]
        ),
    )


@router.callback_query(F.data == "admin:add_gift")
async def admin_add_gift(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    await state.set_state(AdminFlow.add_gift)
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text="Отправь подарок в формате:\n\n<code>Название | цена | шанс(0..1)</code>\n\nПример:\n<code>AirPods | 10000 | 0.05</code>\n\nФото добавим следующим шагом (через file_id).",
        reply_markup=kb_admin_back(),
        screen="admin:add_gift",
        payload=None,
    )


@router.message(AdminFlow.add_gift)
async def admin_add_gift_msg(message: Message, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not message.from_user or not _is_admin(config, message.from_user.id):
        return
    parts = [p.strip() for p in (message.text or "").split("|")]
    if len(parts) < 3:
        await message.answer("Формат неверный. Нужно: Название | цена | шанс(0..1)")
        return
    title = parts[0]
    price = int(parts[1])
    chance = float(parts[2])
    await conn.execute(
        "INSERT INTO gifts(title, price, drop_chance, is_active) VALUES(?, ?, ?, 1)",
        (title, price, chance),
    )
    await conn.commit()
    await state.clear()
    await message.answer(
        "✅ Подарок добавлен. Открой /admin для продолжения.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✖ Закрыть", callback_data="admin:close_notice")]
            ]
        ),
    )


@router.callback_query(F.data == "admin:list_start_sponsors")
async def admin_list_start_sponsors(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    sponsors = await list_start_sponsors(conn)
    buttons: list[list[InlineKeyboardButton]] = []
    for s in sponsors:
        sid = int(s["id"])
        title = str(s["title"])
        is_active = int(s["is_active"])
        type_ = (s["type"] or "channel").lower() if "type" in s.keys() else "channel"
        btn_text = f"{_bool_emoji(is_active)} [{type_}] {title} (#{sid})"
        buttons.append(
            [InlineKeyboardButton(text=btn_text, callback_data=f"admin:start_sponsor:{sid}")]
        )
    buttons.append([InlineKeyboardButton(text="➕ Добавить", callback_data="admin:add_start_sponsor")])
    buttons.append([InlineKeyboardButton(text="⟵ Админ-меню", callback_data="admin:menu")])
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text="📢 Старт-спонсоры:",
        reply_markup=markup,
        screen="admin:list_start_sponsors",
        payload=None,
    )


@router.callback_query(F.data.startswith("admin:start_sponsor:"))
async def admin_start_sponsor_detail(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    try:
        sid = int(cb.data.split(":")[-1])
    except Exception:
        return
    s = await get_start_sponsor(conn, sid)
    if not s:
        await cb.answer("Спонсор не найден.", show_alert=True)
        return
    type_ = (s["type"] or "channel").lower() if "type" in s.keys() else "channel"
    text = (
        f"📢 <b>Старт-спонсор #{s['id']}</b>\n\n"
        f"Название: <b>{s['title']}</b>\n"
        f"Тип: <b>{type_}</b>\n"
        f"channel_id: <code>{s['channel_id']}</code>\n"
        f"username: <code>{s['channel_username'] or '-'}</code>\n"
        f"link: <code>{s['invite_link'] or '-'}</code>\n"
        f"Активен: <b>{'да' if s['is_active'] else 'нет'}</b>\n"
    )
    buttons = [
        [
            InlineKeyboardButton(
                text="✏ Изменить", callback_data=f"admin:edit_start_sponsor:{sid}"
            )
        ],
        [
            InlineKeyboardButton(
                text=("🔕 Выключить" if s["is_active"] else "🔔 Включить"),
                callback_data=f"admin:toggle_start_sponsor:{sid}",
            )
        ],
        [
            InlineKeyboardButton(
                text="🗑 Удалить", callback_data=f"admin:delete_start_sponsor:{sid}"
            )
        ],
        [InlineKeyboardButton(text="⟵ К списку", callback_data="admin:list_start_sponsors")],
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=text,
        reply_markup=markup,
        screen="admin:start_sponsor_detail",
        payload={"id": sid},
    )


@router.callback_query(F.data.startswith("admin:edit_start_sponsor:"))
async def admin_edit_start_sponsor(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    try:
        sid = int(cb.data.split(":")[-1])
    except Exception:
        return
    s = await get_start_sponsor(conn, sid)
    if not s:
        await cb.answer("Спонсор не найден.", show_alert=True)
        return
    await state.set_state(AdminFlow.edit_start_sponsor)
    await state.update_data(edit_start_sponsor_id=sid)
    type_ = (s["type"] or "channel").lower() if "type" in s.keys() else "channel"
    text = (
        f"✏ Редактирование старт-спонсора <code>#{sid}</code>.\n\n"
        "Отправь данные в формате:\n"
        "<code>Название | тип(channel/bot/link) | channel_id(для channel, иначе 0) | @username(опц) | invite_link(опц)</code>\n\n"
        "Текущее значение:\n"
        f"<code>{s['title']} | {type_} | {s['channel_id']} | {s['channel_username'] or ''} | {s['invite_link'] or ''}</code>"
    )
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=text,
        reply_markup=kb_admin_back(),
        screen="admin:edit_start_sponsor",
        payload={"id": sid},
    )


@router.callback_query(F.data.startswith("admin:toggle_start_sponsor:"))
async def admin_toggle_start_sponsor(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    try:
        sid = int(cb.data.split(":")[-1])
    except Exception:
        return
    s = await get_start_sponsor(conn, sid)
    if not s:
        await cb.answer("Спонсор не найден.", show_alert=True)
        return
    new_active = 0 if s["is_active"] else 1
    from ..repo import update_start_sponsor

    await update_start_sponsor(
        conn,
        sid,
        title=str(s["title"]),
        type_=(s["type"] or "channel"),
        channel_id=int(s["channel_id"]),
        channel_username=s["channel_username"],
        invite_link=s["invite_link"],
        is_active=new_active,
    )
    await admin_start_sponsor_detail(cb, bot, conn, config, state)


@router.callback_query(F.data.startswith("admin:delete_start_sponsor:"))
async def admin_delete_start_sponsor_cb(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer("Удалено.", show_alert=False)
    try:
        sid = int(cb.data.split(":")[-1])
    except Exception:
        return
    await delete_start_sponsor(conn, sid)
    # Вернёмся к списку
    await admin_list_start_sponsors(cb, bot, conn, config)


@router.callback_query(F.data == "admin:list_task_sponsors")
async def admin_list_task_sponsors_cb(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    sponsors = await list_task_sponsors(conn)
    buttons: list[list[InlineKeyboardButton]] = []
    for s in sponsors:
        sid = int(s["id"])
        title = str(s["title"])
        is_active = int(s["is_active"])
        type_ = (s["type"] or "channel").lower() if "type" in s.keys() else "channel"
        bonus = int(s["bonus_attempts"])
        btn_text = f"{_bool_emoji(is_active)} [{type_}] {title} (+{bonus}) (#{sid})"
        buttons.append(
            [InlineKeyboardButton(text=btn_text, callback_data=f"admin:task_sponsor:{sid}")]
        )
    buttons.append([InlineKeyboardButton(text="➕ Добавить", callback_data="admin:add_task_sponsor")])
    buttons.append([InlineKeyboardButton(text="⟵ Админ-меню", callback_data="admin:menu")])
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text="🎯 Спонсоры (задания):",
        reply_markup=markup,
        screen="admin:list_task_sponsors",
        payload=None,
    )


@router.callback_query(F.data.startswith("admin:task_sponsor:"))
async def admin_task_sponsor_detail(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    try:
        sid = int(cb.data.split(":")[-1])
    except Exception:
        return
    s = await get_task_sponsor(conn, sid)
    if not s:
        await cb.answer("Спонсор не найден.", show_alert=True)
        return
    type_ = (s["type"] or "channel").lower() if "type" in s.keys() else "channel"
    text = (
        f"🎯 <b>Спонсор (задание) #{s['id']}</b>\n\n"
        f"Название: <b>{s['title']}</b>\n"
        f"Тип: <b>{type_}</b>\n"
        f"channel_id: <code>{s['channel_id']}</code>\n"
        f"username: <code>{s['channel_username'] or '-'}</code>\n"
        f"link: <code>{s['invite_link'] or '-'}</code>\n"
        f"Бонус попыток: <b>{s['bonus_attempts']}</b>\n"
        f"Активен: <b>{'да' if s['is_active'] else 'нет'}</b>\n"
    )
    buttons = [
        [
            InlineKeyboardButton(
                text="✏ Изменить", callback_data=f"admin:edit_task_sponsor:{sid}"
            )
        ],
        [
            InlineKeyboardButton(
                text=("🔕 Выключить" if s["is_active"] else "🔔 Включить"),
                callback_data=f"admin:toggle_task_sponsor:{sid}",
            )
        ],
        [
            InlineKeyboardButton(
                text="🗑 Удалить", callback_data=f"admin:delete_task_sponsor:{sid}"
            )
        ],
        [InlineKeyboardButton(text="⟵ К списку", callback_data="admin:list_task_sponsors")],
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=text,
        reply_markup=markup,
        screen="admin:task_sponsor_detail",
        payload={"id": sid},
    )


@router.callback_query(F.data.startswith("admin:edit_task_sponsor:"))
async def admin_edit_task_sponsor(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    try:
        sid = int(cb.data.split(":")[-1])
    except Exception:
        return
    s = await get_task_sponsor(conn, sid)
    if not s:
        await cb.answer("Спонсор не найден.", show_alert=True)
        return
    await state.set_state(AdminFlow.edit_task_sponsor)
    await state.update_data(edit_task_sponsor_id=sid)
    type_ = (s["type"] or "channel").lower() if "type" in s.keys() else "channel"
    text = (
        f"✏ Редактирование спонсора (задания) <code>#{sid}</code>.\n\n"
        "Отправь данные в формате:\n"
        "<code>Название | тип(channel/bot/link) | channel_id(для channel, иначе 0) | бонус_попыток | @username(опц) | invite_link(опц)</code>\n\n"
        "Текущее значение:\n"
        f"<code>{s['title']} | {type_} | {s['channel_id']} | {s['bonus_attempts']} | {s['channel_username'] or ''} | {s['invite_link'] or ''}</code>"
    )
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=text,
        reply_markup=kb_admin_back(),
        screen="admin:edit_task_sponsor",
        payload={"id": sid},
    )


@router.callback_query(F.data.startswith("admin:toggle_task_sponsor:"))
async def admin_toggle_task_sponsor(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    try:
        sid = int(cb.data.split(":")[-1])
    except Exception:
        return
    s = await get_task_sponsor(conn, sid)
    if not s:
        await cb.answer("Спонсор не найден.", show_alert=True)
        return
    new_active = 0 if s["is_active"] else 1
    from ..repo import update_task_sponsor

    await update_task_sponsor(
        conn,
        sid,
        title=str(s["title"]),
        type_=(s["type"] or "channel"),
        channel_id=int(s["channel_id"]),
        channel_username=s["channel_username"],
        invite_link=s["invite_link"],
        bonus_attempts=int(s["bonus_attempts"]),
        is_active=new_active,
    )
    await admin_task_sponsor_detail(cb, bot, conn, config)


@router.callback_query(F.data.startswith("admin:delete_task_sponsor:"))
async def admin_delete_task_sponsor_cb(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer("Удалено.", show_alert=False)
    try:
        sid = int(cb.data.split(":")[-1])
    except Exception:
        return
    await delete_task_sponsor(conn, sid)
    await admin_list_task_sponsors_cb(cb, bot, conn, config)


@router.callback_query(F.data == "admin:set_global_chance")
async def admin_set_global_chance(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    await state.set_state(AdminFlow.set_global_chance)
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text="Отправь глобальный шанс выпадения подарка при открытии клетки (0..1), например:\n<code>0.10</code>",
        reply_markup=kb_admin_menu(),
        screen="admin:set_global_chance",
        payload=None,
    )


@router.message(AdminFlow.set_global_chance)
async def admin_set_global_chance_msg(message: Message, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not message.from_user or not _is_admin(config, message.from_user.id):
        return
    try:
        v = float((message.text or "").strip().replace(",", "."))
    except Exception:
        await message.answer("Нужно число 0..1")
        return
    v = max(0.0, min(1.0, v))
    await set_setting(conn, "game_cell_gift_chance", f"{v:.6f}")
    await state.clear()
    await message.answer(
        f"✅ Установлено: {v:.2%}. Открой /admin для продолжения.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✖ Закрыть", callback_data="admin:close_notice")]
            ]
        ),
    )


@router.callback_query(F.data == "admin:set_stars_price")
async def admin_set_stars_price(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    await state.set_state(AdminFlow.set_stars_price)
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=(
            "⭐ <b>Цена попытки в Telegram Stars</b>\n\n"
            "Отправь целое число — сколько звёзд нужно за 1 попытку.\n\n"
            "Например:\n<code>1</code> или <code>5</code>"
        ),
        reply_markup=kb_admin_back(),
        screen="admin:set_stars_price",
        payload=None,
    )


@router.message(AdminFlow.set_stars_price)
async def admin_set_stars_price_msg(message: Message, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not message.from_user or not _is_admin(config, message.from_user.id):
        return
    txt = (message.text or "").strip()
    try:
        v = int(txt)
    except Exception:
        await message.answer("Нужно целое число >= 1 (количество звёзд).")
        return
    if v < 1:
        await message.answer("Число должно быть не меньше 1.")
        return
    await set_setting(conn, "stars_price_per_attempt", str(v))
    await state.clear()
    await message.answer(
        f"✅ Цена попытки установлена: <b>{v}⭐</b>.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✖ Закрыть", callback_data="admin:close_notice")]
            ]
        ),
    )


@router.message(AdminFlow.edit_gift)
async def admin_edit_gift_msg(message: Message, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    from ..repo import update_gift, get_gift

    if not message.from_user or not _is_admin(config, message.from_user.id):
        return
    data = await state.get_data()
    gid = int(data.get("edit_gift_id", 0) or 0)
    if not gid:
        await message.answer("Неизвестный подарок в состоянии, попробуйте ещё раз.")
        await state.clear()
        return
    parts = [p.strip() for p in (message.text or "").split("|")]
    if len(parts) < 3:
        await message.answer("Формат неверный. Нужно минимум: Название | цена | шанс(0..1) | emoji(опц)")
        return
    title = parts[0]
    try:
        price = int(parts[1])
    except Exception:
        await message.answer("Цена должна быть целым числом.")
        return
    try:
        chance = float(parts[2].replace(",", "."))
    except Exception:
        await message.answer("Шанс должен быть числом 0..1.")
        return
    chance = max(0.0, min(1.0, chance))
    emoji = parts[3] if len(parts) >= 4 and parts[3] else None

    g = await get_gift(conn, gid)
    if not g:
        await message.answer("Подарок не найден.")
        await state.clear()
        return

    await update_gift(
        conn,
        gid,
        title=title,
        price=price,
        drop_chance=chance,
        emoji=emoji,
        is_active=int(g["is_active"]),
    )
    await state.clear()
    await message.answer(
        "✅ Подарок обновлён. Открой /admin → Подарки.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✖ Закрыть", callback_data="admin:close_notice")]
            ]
        ),
    )


@router.message(AdminFlow.edit_start_sponsor)
async def admin_edit_start_sponsor_msg(message: Message, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    from ..repo import update_start_sponsor, get_start_sponsor

    if not message.from_user or not _is_admin(config, message.from_user.id):
        return
    data = await state.get_data()
    sid = int(data.get("edit_start_sponsor_id", 0) or 0)
    if not sid:
        await message.answer("Неизвестный спонсор в состоянии, попробуйте ещё раз.")
        await state.clear()
        return
    parts = [p.strip() for p in (message.text or "").split("|")]
    if len(parts) < 3:
        await message.answer("Формат неверный. Нужно минимум: Название | тип | channel_id | ...")
        return
    title = parts[0]
    type_ = (parts[1] or "channel").lower()
    if type_ not in ("channel", "bot", "link"):
        await message.answer("Тип должен быть одним из: channel, bot, link")
        return
    try:
        channel_id = int(parts[2])
    except Exception:
        await message.answer("channel_id должен быть числом (для bot/link можно 0)")
        return
    username = parts[3] if len(parts) >= 4 and parts[3] else None
    invite_link = parts[4] if len(parts) >= 5 and parts[4] else None

    s = await get_start_sponsor(conn, sid)
    if not s:
        await message.answer("Спонсор не найден.")
        await state.clear()
        return

    await update_start_sponsor(
        conn,
        sid,
        title=title,
        type_=type_,
        channel_id=channel_id,
        channel_username=username,
        invite_link=invite_link,
        is_active=int(s["is_active"]),
    )
    await state.clear()
    await message.answer(
        "✅ Старт-спонсор обновлён. Открой /admin → Старт-спонсоры.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✖ Закрыть", callback_data="admin:close_notice")]
            ]
        ),
    )


@router.message(AdminFlow.edit_task_sponsor)
async def admin_edit_task_sponsor_msg(message: Message, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    from ..repo import update_task_sponsor, get_task_sponsor

    if not message.from_user or not _is_admin(config, message.from_user.id):
        return
    data = await state.get_data()
    sid = int(data.get("edit_task_sponsor_id", 0) or 0)
    if not sid:
        await message.answer("Неизвестный спонсор в состоянии, попробуйте ещё раз.")
        await state.clear()
        return
    parts = [p.strip() for p in (message.text or "").split("|")]
    if len(parts) < 4:
        await message.answer("Формат неверный. Нужно минимум: Название | тип | channel_id | бонус_попыток | ...")
        return
    title = parts[0]
    type_ = (parts[1] or "channel").lower()
    if type_ not in ("channel", "bot", "link"):
        await message.answer("Тип должен быть одним из: channel, bot, link")
        return
    try:
        channel_id = int(parts[2])
    except Exception:
        await message.answer("channel_id должен быть числом (для bot/link можно 0)")
        return
    try:
        bonus_attempts = int(parts[3])
    except Exception:
        await message.answer("бонус_попыток должен быть целым числом")
        return
    username = parts[4] if len(parts) >= 5 and parts[4] else None
    invite_link = parts[5] if len(parts) >= 6 and parts[5] else None

    s = await get_task_sponsor(conn, sid)
    if not s:
        await message.answer("Спонсор не найден.")
        await state.clear()
        return

    await update_task_sponsor(
        conn,
        sid,
        title=title,
        type_=type_,
        channel_id=channel_id,
        channel_username=username,
        invite_link=invite_link,
        bonus_attempts=bonus_attempts,
        is_active=int(s["is_active"]),
    )
    await state.clear()
    await message.answer(
        "✅ Спонсор (задание) обновлён. Открой /admin → Спонсоры (задания).",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✖ Закрыть", callback_data="admin:close_notice")]
            ]
        ),
    )


@router.callback_query(F.data == "admin:list_gifts")
async def admin_list_gifts(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    gifts = await list_gifts(conn)
    buttons: list[list[InlineKeyboardButton]] = []
    for g in gifts:
        gid = int(g["id"])
        title = str(g["title"])
        is_active = int(g["is_active"])
        emoji = g["emoji"] or "🎁"
        btn_text = f"{_bool_emoji(is_active)} {emoji} {title} (#{gid})"
        buttons.append(
            [InlineKeyboardButton(text=btn_text, callback_data=f"admin:gift:{gid}")]
        )
    buttons.append([InlineKeyboardButton(text="➕ Добавить", callback_data="admin:add_gift")])
    buttons.append([InlineKeyboardButton(text="⟵ Админ-меню", callback_data="admin:menu")])
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text="🎁 Подарки:",
        reply_markup=markup,
        screen="admin:list_gifts",
        payload=None,
    )


@router.callback_query(F.data.startswith("admin:gift:"))
async def admin_gift_detail(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    try:
        gid = int(cb.data.split(":")[-1])
    except Exception:
        return
    g = await get_gift(conn, gid)
    if not g:
        await cb.answer("Подарок не найден.", show_alert=True)
        return
    text = (
        f"🎁 <b>Подарок #{g['id']}</b>\n\n"
        f"Название: <b>{g['title']}</b>\n"
        f"Цена: <b>{g['price']}</b>\n"
        f"Шанс: <b>{g['drop_chance']}</b>\n"
        f"Emoji: <code>{g['emoji'] or '-'}</code>\n"
        f"is_active: <b>{'да' if g['is_active'] else 'нет'}</b>\n"
    )
    buttons = [
        [InlineKeyboardButton(text="✏ Изменить", callback_data=f"admin:edit_gift:{gid}")],
        [
            InlineKeyboardButton(
                text=("🔕 Выключить" if g["is_active"] else "🔔 Включить"),
                callback_data=f"admin:toggle_gift:{gid}",
            )
        ],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin:delete_gift:{gid}")],
        [InlineKeyboardButton(text="⟵ К списку", callback_data="admin:list_gifts")],
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=text,
        reply_markup=markup,
        screen="admin:gift_detail",
        payload={"id": gid},
    )


@router.callback_query(F.data.startswith("admin:edit_gift:"))
async def admin_edit_gift(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    try:
        gid = int(cb.data.split(":")[-1])
    except Exception:
        return
    g = await get_gift(conn, gid)
    if not g:
        await cb.answer("Подарок не найден.", show_alert=True)
        return
    await state.set_state(AdminFlow.edit_gift)
    await state.update_data(edit_gift_id=gid)
    text = (
        f"✏ Редактирование подарка <code>#{gid}</code>.\n\n"
        "Отправь данные в формате:\n"
        "<code>Название | цена | шанс(0..1) | emoji(опц)</code>\n\n"
        f"Текущее значение:\n"
        f"<code>{g['title']} | {g['price']} | {g['drop_chance']} | {g['emoji'] or ''}</code>"
    )
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=text,
        reply_markup=kb_admin_back(),
        screen="admin:edit_gift",
        payload={"id": gid},
    )


@router.callback_query(F.data.startswith("admin:toggle_gift:"))
async def admin_toggle_gift(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    try:
        gid = int(cb.data.split(":")[-1])
    except Exception:
        return
    g = await get_gift(conn, gid)
    if not g:
        await cb.answer("Подарок не найден.", show_alert=True)
        return
    from ..repo import update_gift

    new_active = 0 if g["is_active"] else 1
    await update_gift(
        conn,
        gid,
        title=str(g["title"]),
        price=int(g["price"]),
        drop_chance=float(g["drop_chance"]),
        emoji=g["emoji"],
        is_active=new_active,
    )
    await admin_gift_detail(cb, bot, conn, config, state)


@router.callback_query(F.data.startswith("admin:delete_gift:"))
async def admin_delete_gift_cb(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer("Удалено.", show_alert=False)
    try:
        gid = int(cb.data.split(":")[-1])
    except Exception:
        return
    await delete_gift(conn, gid)
    await admin_list_gifts(cb, bot, conn, config)


@router.callback_query(F.data == "admin:edit_user_attempts")
async def admin_edit_user_attempts(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    await state.set_state(AdminFlow.edit_user_attempts)
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text="Отправь команду в формате:\n\n<code>user_id delta</code>\n\nПример:\n<code>123456789 10</code>\nили\n<code>123456789 -5</code>",
        reply_markup=kb_admin_menu(),
        screen="admin:edit_user_attempts",
        payload=None,
    )


@router.message(AdminFlow.edit_user_attempts)
async def admin_edit_user_attempts_msg(message: Message, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not message.from_user or not _is_admin(config, message.from_user.id):
        return
    m = re.match(r"^\s*(\d+)\s+(-?\d+)\s*$", message.text or "")
    if not m:
        await message.answer("Формат неверный. Нужно: user_id delta")
        return
    user_id = int(m.group(1))
    delta = int(m.group(2))
    await add_attempts(conn, user_id, delta)
    await state.clear()
    await message.answer(
        "✅ Готово. Открой /admin для продолжения.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✖ Закрыть", callback_data="admin:close_notice")]
            ]
        ),
    )


@router.callback_query(F.data == "admin:list_users")
async def admin_list_users_cb(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    users = await list_users(conn, limit=50, offset=0)
    buttons: list[list[InlineKeyboardButton]] = []
    for u in users:
        uid = int(u["user_id"])
        name = u["first_name"] or u["username"] or str(uid)
        banned = int(u["is_banned"]) if "is_banned" in u.keys() else 0
        btn_text = f"{'🚫' if banned else '👤'} {name} (ID {uid})"
        buttons.append(
            [InlineKeyboardButton(text=btn_text, callback_data=f"admin:user:{uid}")]
        )
    buttons.append([InlineKeyboardButton(text="⟵ Админ-меню", callback_data="admin:menu")])
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text="👥 Пользователи (последние 50):",
        reply_markup=markup,
        screen="admin:list_users",
        payload=None,
    )


@router.callback_query(F.data.startswith("admin:user:"))
async def admin_user_detail(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    from ..repo import get_user, get_user_attempts

    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    try:
        uid = int(cb.data.split(":")[-1])
    except Exception:
        return
    u = await get_user(conn, uid)
    if not u:
        await cb.answer("Пользователь не найден.", show_alert=True)
        return
    attempts = await get_user_attempts(conn, uid)
    banned = int(u["is_banned"]) if "is_banned" in u.keys() else 0
    text = (
        f"👤 <b>Пользователь {uid}</b>\n\n"
        f"Username: <code>{u['username'] or '-'}</code>\n"
        f"Имя: <code>{u['first_name'] or '-'}</code>\n"
        f"Фамилия: <code>{u['last_name'] or '-'}</code>\n"
        f"Попытки: <b>{attempts}</b>\n"
        f"Забанен: <b>{'да' if banned else 'нет'}</b>\n"
    )
    buttons = [
        [
            InlineKeyboardButton(
                text="✏ Попытки", callback_data=f"admin:edit_user:{uid}"
            )
        ],
        [
            InlineKeyboardButton(
                text=("✅ Разбанить" if banned else "🚫 Забанить"),
                callback_data=f"admin:toggle_ban_user:{uid}",
            )
        ],
        [InlineKeyboardButton(text="⟵ К списку", callback_data="admin:list_users")],
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=text,
        reply_markup=markup,
        screen="admin:user_detail",
        payload={"id": uid},
    )


@router.callback_query(F.data.startswith("admin:toggle_ban_user:"))
async def admin_toggle_ban_user(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    from ..repo import get_user

    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    try:
        uid = int(cb.data.split(":")[-1])
    except Exception:
        return
    u = await get_user(conn, uid)
    if not u:
        await cb.answer("Пользователь не найден.", show_alert=True)
        return
    banned = int(u["is_banned"]) if "is_banned" in u.keys() else 0
    await set_user_ban(conn, uid, not banned)
    await admin_user_detail(cb, bot, conn, config, state)


@router.callback_query(F.data.startswith("admin:edit_user:"))
async def admin_edit_user(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()
    try:
        uid = int(cb.data.split(":")[-1])
    except Exception:
        return
    await state.set_state(AdminFlow.edit_user)
    await state.update_data(edit_user_id=uid)
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=(
            f"✏ Редактирование попыток пользователя <code>{uid}</code>.\n\n"
            "Отправь новое количество попыток (целое число >= 0)."
        ),
        reply_markup=kb_admin_back(),
        screen="admin:edit_user",
        payload={"id": uid},
    )


@router.callback_query(F.data == "admin:stats")
async def admin_stats(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config) -> None:
    if not cb.from_user or not cb.message or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer()

    # простая агрегированная статистика по основным таблицам
    cur = await conn.execute("SELECT COUNT(1) AS c FROM users")
    users_total = int((await cur.fetchone())["c"])
    cur = await conn.execute("SELECT COUNT(1) AS c FROM users WHERE is_banned=1")
    users_banned = int((await cur.fetchone())["c"])
    cur = await conn.execute("SELECT SUM(attempts) AS s FROM users")
    attempts_sum_row = await cur.fetchone()
    attempts_sum = int(attempts_sum_row["s"] or 0)

    cur = await conn.execute("SELECT COUNT(1) AS c FROM gifts")
    gifts_total = int((await cur.fetchone())["c"])
    cur = await conn.execute("SELECT COUNT(1) AS c FROM gifts WHERE is_active=1")
    gifts_active = int((await cur.fetchone())["c"])

    cur = await conn.execute("SELECT COUNT(1) AS c FROM start_sponsors")
    ss_total = int((await cur.fetchone())["c"])
    cur = await conn.execute("SELECT COUNT(1) AS c FROM start_sponsors WHERE is_active=1")
    ss_active = int((await cur.fetchone())["c"])

    cur = await conn.execute("SELECT COUNT(1) AS c FROM sponsors")
    ts_total = int((await cur.fetchone())["c"])
    cur = await conn.execute("SELECT COUNT(1) AS c FROM sponsors WHERE is_active=1")
    ts_active = int((await cur.fetchone())["c"])

    cur = await conn.execute("SELECT COUNT(1) AS c FROM inventory")
    inv_total = int((await cur.fetchone())["c"])
    cur = await conn.execute("SELECT COUNT(1) AS c FROM inventory WHERE status='withdrawn'")
    inv_withdrawn = int((await cur.fetchone())["c"])

    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Пользователи: <b>{users_total}</b>\n"
        f"🚫 Забанено: <b>{users_banned}</b>\n"
        f"🎮 Суммарно попыток: <b>{attempts_sum}</b>\n\n"
        f"🎁 Подарки: всего <b>{gifts_total}</b>, активных <b>{gifts_active}</b>\n"
        f"📦 Инвентарь: всего <b>{inv_total}</b>, выведено <b>{inv_withdrawn}</b>\n\n"
        f"📢 Старт-спонсоры: всего <b>{ss_total}</b>, активных <b>{ss_active}</b>\n"
        f"🎯 Спонсоры (задания): всего <b>{ts_total}</b>, активных <b>{ts_active}</b>\n"
    )
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=text,
        reply_markup=kb_admin_back(),
        screen="admin:stats",
        payload=None,
    )


@router.message(AdminFlow.edit_user)
async def admin_edit_user_msg(message: Message, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not message.from_user or not _is_admin(config, message.from_user.id):
        return
    data = await state.get_data()
    uid = int(data.get("edit_user_id", 0) or 0)
    if not uid:
        await message.answer("Неизвестный пользователь в состоянии, попробуйте ещё раз.")
        await state.clear()
        return
    try:
        attempts = int((message.text or "").strip())
    except Exception:
        await message.answer("Нужно целое число попыток (>= 0).")
        return
    attempts = max(0, attempts)
    await set_attempts(conn, uid, attempts)
    await state.clear()
    await message.answer(
        "✅ Попытки обновлены. Открой /admin для продолжения.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✖ Закрыть", callback_data="admin:close_notice")]
            ]
        ),
    )


@router.message(AdminFlow.broadcast)
async def admin_broadcast_msg(message: Message, bot, conn: aiosqlite.Connection, config: Config, state: FSMContext) -> None:
    if not message.from_user or not _is_admin(config, message.from_user.id):
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Текст рассылки не может быть пустым.")
        return

    # Получаем всех незабаненных пользователей
    cur = await conn.execute(
        "SELECT user_id FROM users WHERE is_banned=0 OR is_banned IS NULL"
    )
    rows = await cur.fetchall()
    total = len(rows)
    sent = 0

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✖ Закрыть", callback_data="admin:close_notice")]
        ]
    )

    for r in rows:
        uid = int(r["user_id"])
        try:
            await bot.send_message(
                chat_id=uid,
                text=text,
                disable_web_page_preview=True,
                reply_markup=markup,
            )
            sent += 1
        except Exception:
            # Игнорируем ошибки (бот заблокирован и т.п.)
            continue

    await state.clear()
    await message.answer(
        f"✅ Рассылка завершена. Успешно отправлено: <b>{sent}</b> из <b>{total}</b> пользователей.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✖ Закрыть", callback_data="admin:close_notice")]
            ]
        ),
    )


@router.callback_query(F.data == "admin:close_notice")
async def admin_close_notice(cb: CallbackQuery) -> None:
    await cb.answer()
    try:
        if cb.message:
            await cb.message.delete()
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin:withdraw_done:"))
async def admin_withdraw_done(cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config) -> None:
    if not cb.from_user or not _is_admin(config, cb.from_user.id):
        return
    await cb.answer("Статус обновлён.", show_alert=False)
    try:
        _, _, inv_id_str, user_id_str = cb.data.split(":")
        inv_id = int(inv_id_str)
        user_id = int(user_id_str)
    except Exception:
        return

    # Обновляем статус подарка
    await set_inventory_status(conn, inv_id, "withdrawn", withdrawn=True)

    # Уведомляем пользователя
    text_user = (
        "✅ Ваш подарок был отмечен как выведенный и отправлен в ваш профиль.\n\n"
        "Спасибо, что пользуетесь ботом!"
    )
    await bot.send_message(
        chat_id=user_id,
        text=text_user,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✖ Закрыть", callback_data="profile:close_notice")]
            ]
        ),
    )



