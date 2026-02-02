from __future__ import annotations

from datetime import datetime

import aiosqlite
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from ..config import Config
from ..keyboards import kb_back_to_menu, kb_profile_menu
from ..repo import get_inventory_item, list_inventory, set_inventory_status, is_user_banned
from ..ui import edit_or_recreate

router = Router(name="profile")


def _status_label(status: str) -> str:
    if status == "won":
        return "Выиграно 🎉"
    if status == "withdraw_pending":
        return "В ожидании вывода ⌛"
    if status == "withdrawn":
        return "Выведено ✅"
    return status


def _fmt_dt(ts: int | None) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")


@router.callback_query(F.data == "menu:profile")
async def open_profile(cb: CallbackQuery, bot, conn: aiosqlite.Connection) -> None:
    if not cb.from_user or not cb.message:
        return
    await cb.answer()

    if await is_user_banned(conn, cb.from_user.id):
        await bot.send_message(
            chat_id=cb.from_user.id,
            text="⛔ Доступ к боту для вас ограничен. Обратитесь к администратору.",
        )
        return
    from ..repo import get_user_attempts

    attempts = await get_user_attempts(conn, cb.from_user.id)
    items = await list_inventory(conn, cb.from_user.id)
    total = len(items)
    withdrawn = sum(1 for i in items if i["status"] == "withdrawn")

    text = (
        "👤 <b>Профиль</b>\n\n"
        f"🎮 Попыток: <b>{attempts}</b>\n"
        f"🎁 Подарков в инвентаре: <b>{total}</b>\n"
        f"✅ Выведено подарков: <b>{withdrawn}</b>\n\n"
        "Выберите действие ниже 👇"
    )
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=text,
        reply_markup=kb_profile_menu(),
        screen="profile:home",
        payload=None,
    )


@router.callback_query(F.data == "profile:inventory")
async def profile_inventory(cb: CallbackQuery, bot, conn: aiosqlite.Connection) -> None:
    if not cb.from_user or not cb.message:
        return
    await cb.answer()

    if await is_user_banned(conn, cb.from_user.id):
        await bot.send_message(
            chat_id=cb.from_user.id,
            text="⛔ Доступ к боту для вас ограничен. Обратитесь к администратору.",
        )
        return

    items = await list_inventory(conn, cb.from_user.id)
    if not items:
        text = "🎁 Инвентарь пуст.\n\nВыигрывайте подарки в игре и они появятся здесь."
        await edit_or_recreate(
            bot=bot,
            conn=conn,
            user_id=cb.from_user.id,
            chat_id=cb.message.chat.id,
            text=text,
            reply_markup=kb_profile_menu(),
            screen="profile:inventory_empty",
            payload=None,
        )
        return

    buttons: list[list[InlineKeyboardButton]] = []
    for it in items:
        inv_id = int(it["id"])
        emoji = it["gift_emoji"] or "🎁"
        title = it["gift_title"]
        status_label = _status_label(str(it["status"]))
        btn_text = f"{emoji} {title} ({status_label})"
        buttons.append(
            [InlineKeyboardButton(text=btn_text, callback_data=f"profile:item:{inv_id}")]
        )
    # add back row
    buttons.append(
        [
            InlineKeyboardButton(text="⟵ Профиль", callback_data="menu:profile"),
            InlineKeyboardButton(text="⟵ Меню", callback_data="menu:home"),
        ]
    )
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    text = "🎁 <b>Ваш инвентарь</b>\n\nНажмите на подарок, чтобы посмотреть детали и вывести."
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=text,
        reply_markup=markup,
        screen="profile:inventory",
        payload=None,
    )


@router.callback_query(F.data.startswith("profile:item:"))
async def profile_item(cb: CallbackQuery, bot, conn: aiosqlite.Connection) -> None:
    if not cb.from_user or not cb.message:
        return
    await cb.answer()

    if await is_user_banned(conn, cb.from_user.id):
        await bot.send_message(
            chat_id=cb.from_user.id,
            text="⛔ Доступ к боту для вас ограничен. Обратитесь к администратору.",
        )
        return
    try:
        inv_id = int(cb.data.split(":")[-1])
    except Exception:
        return

    item = await get_inventory_item(conn, inv_id, cb.from_user.id)
    if not item:
        await cb.answer("Подарок не найден.", show_alert=True)
        return

    emoji = item["gift_emoji"] or "🎁"
    status = str(item["status"])
    status_label = _status_label(status)

    text = (
        f"{emoji} <b>{item['gift_title']}</b>\n\n"
        f"💲 Цена: <b>{item['price']}</b>\n"
        f"🆔 ID выигрыша: <code>{item['id']}</code>\n"
        f"📅 Выиграно: <b>{_fmt_dt(item['won_at'])}</b>\n"
        f"📦 Статус: <b>{status_label}</b>\n"
    )

    buttons: list[list[InlineKeyboardButton]] = []
    if status == "won":
        buttons.append(
            [
                InlineKeyboardButton(
                    text="📤 Вывести", callback_data=f"profile:withdraw:{inv_id}"
                )
            ]
        )
    buttons.append(
        [
            InlineKeyboardButton(
                text="🎁 Инвентарь", callback_data="profile:inventory"
            ),
            InlineKeyboardButton(text="⟵ Меню", callback_data="menu:home"),
        ]
    )
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=text,
        reply_markup=markup,
        screen="profile:item",
        payload={"inventory_id": inv_id},
    )


@router.callback_query(F.data.startswith("profile:withdraw:"))
async def profile_withdraw(cb: CallbackQuery, bot, conn: aiosqlite.Connection) -> None:
    if not cb.from_user or not cb.message:
        return
    await cb.answer()

    if await is_user_banned(conn, cb.from_user.id):
        await bot.send_message(
            chat_id=cb.from_user.id,
            text="⛔ Доступ к боту для вас ограничен. Обратитесь к администратору.",
        )
        return
    try:
        inv_id = int(cb.data.split(":")[-1])
    except Exception:
        return

    item = await get_inventory_item(conn, inv_id, cb.from_user.id)
    if not item or item["status"] != "won":
        await cb.answer("Этот подарок нельзя вывести.", show_alert=True)
        return

    emoji = item["gift_emoji"] or "🎁"
    text = (
        f"{emoji} <b>{item['gift_title']}</b>\n\n"
        "Вы уверены, что хотите отправить этот подарок на вывод?\n\n"
        "После подтверждения заявка уйдёт в поддержку, обычно обработка занимает до 24 часов."
    )
    buttons = [
        [
            InlineKeyboardButton(
                text="✅ Подтвердить вывод",
                callback_data=f"profile:confirm_withdraw:{inv_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Отмена", callback_data=f"profile:item:{inv_id}"
            )
        ],
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=text,
        reply_markup=markup,
        screen="profile:confirm_withdraw",
        payload={"inventory_id": inv_id},
    )


@router.callback_query(F.data.startswith("profile:confirm_withdraw:"))
async def profile_confirm_withdraw(
    cb: CallbackQuery, bot, conn: aiosqlite.Connection, config: Config
) -> None:
    if not cb.from_user or not cb.message:
        return
    await cb.answer()

    if await is_user_banned(conn, cb.from_user.id):
        await bot.send_message(
            chat_id=cb.from_user.id,
            text="⛔ Доступ к боту для вас ограничен. Обратитесь к администратору.",
        )
        return
    try:
        inv_id = int(cb.data.split(":")[-1])
    except Exception:
        return

    item = await get_inventory_item(conn, inv_id, cb.from_user.id)
    if not item or item["status"] != "won":
        await cb.answer("Этот подарок нельзя вывести.", show_alert=True)
        return

    # помечаем как "в ожидании вывода"
    await set_inventory_status(conn, inv_id, "withdraw_pending", withdraw_requested=True)

    # отправляем сообщение в чат поддержки
    if config.withdraw_review_chat_id:
        emoji = item["gift_emoji"] or "🎁"
        text = (
            f"📥 <b>Новая заявка на вывод подарка</b>\n\n"
            f"👤 Пользователь: <a href=\"tg://user?id={cb.from_user.id}\">{cb.from_user.full_name}</a> (ID: <code>{cb.from_user.id}</code>)\n"
            f"🎁 Подарок: {emoji} <b>{item['gift_title']}</b>\n"
            f"💲 Цена: <b>{item['price']}</b>\n"
            f"🆔 ID выигрыша: <code>{item['id']}</code>\n"
            f"📅 Выиграно: <b>{_fmt_dt(item['won_at'])}</b>\n"
        )
        buttons = [
            [
                InlineKeyboardButton(
                    text="✅ Выведено",
                    callback_data=f"admin:withdraw_done:{inv_id}:{cb.from_user.id}",
                )
            ]
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        await bot.send_message(
            chat_id=config.withdraw_review_chat_id,
            text=text,
            reply_markup=markup,
            disable_web_page_preview=True,
        )

    # сообщение пользователю
    text_user = (
        "✅ Заявка на вывод подарка отправлена.\n\n"
        "Обычно это занимает до 24 часов. После обработки подарок будет отправлен на ваш профиль."
    )
    close_markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✖ Закрыть", callback_data="profile:close_notice"
                )
            ]
        ]
    )
    await bot.send_message(
        chat_id=cb.from_user.id,
        text=text_user,
        reply_markup=close_markup,
    )

    # Обновляем основной UI (вернёмся к карточке подарка с новым статусом)
    await profile_item(cb, bot, conn)


@router.callback_query(F.data == "profile:close_notice")
async def profile_close_notice(cb: CallbackQuery) -> None:
    await cb.answer()
    try:
        await cb.message.delete()
    except Exception:
        pass


