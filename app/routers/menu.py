from __future__ import annotations

import asyncio

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Message, PreCheckoutQuery

import aiosqlite

from ..keyboards import kb_back_to_menu, kb_menu, kb_task_sponsors_list
from ..repo import (
    add_attempts,
    add_inventory_item,
    get_active_task_sponsors,
    get_setting_int,
    get_ui_state,
    get_unrewarded_task_sponsors,
    is_user_banned,
    mark_sponsor_bonus_granted,
    set_ui_state,
)
from ..ui import edit_or_recreate

router = Router(name="menu")


@router.callback_query(F.data == "menu:home")
async def menu_home(cb: CallbackQuery, bot, conn: aiosqlite.Connection) -> None:
    if not cb.from_user or not cb.message:
        return
    await cb.answer()

    # Бан пользователя
    if await is_user_banned(conn, cb.from_user.id):
        await bot.send_message(
            chat_id=cb.from_user.id,
            text="⛔ Доступ к боту для вас ограничен. Обратитесь к администратору.",
        )
        return
    from ..repo import get_user_attempts, get_ui_state, set_ui_state

    # Если пользователь вышел в меню из игры и у него были незабранные выигрыши,
    # но игра ещё не закончилась поражением, автоматически забираем эти подарки.
    state = await get_ui_state(conn, cb.from_user.id)
    if state and state["screen"] == "game:play" and state["payload_json"]:
        import json

        try:
            payload = json.loads(state["payload_json"])
            pending = payload.get("pending_wins") or []
            finished = payload.get("finished", False)
        except Exception:
            pending = []
            finished = False

        if pending and not finished:
            for w in pending:
                gift_id = int(w["gift_id"])
                await add_inventory_item(conn, cb.from_user.id, gift_id)
            # очищаем pending_wins и помечаем игру завершённой
            payload["pending_wins"] = []
            payload["finished"] = True

            await set_ui_state(
                conn,
                cb.from_user.id,
                state["chat_id"],
                state["message_id"],
                "game:play",
                payload,
            )

    attempts = await get_user_attempts(conn, cb.from_user.id)
    text = (
        f"🎮 Попыток: <b>{attempts}</b>\n\n"
        "Как получить попытки:\n"
        "• 🎯 Задания — +1 за каждое\n"
        "• 🛒 Покупка — 5✨ = 1 попытка\n"
        "• 🤝 Пригласить друга — +4 за каждого\n\n"
        "Выберите действие ниже 👇"
    )
    
    # Проверяем, пришел ли callback из уведомления (сообщение не совпадает с сохраненным в ui_state)
    is_from_reminder = False
    if state:
        saved_chat_id = int(state.get("chat_id", 0))
        saved_message_id = int(state.get("message_id", 0))
        # Если chat_id или message_id не совпадают, значит это уведомление
        if (cb.message.chat.id != saved_chat_id or 
            cb.message.message_id != saved_message_id):
            is_from_reminder = True
    
    if is_from_reminder:
        # Если callback пришел из уведомления, редактируем само уведомление
        try:
            await bot.edit_message_text(
                chat_id=cb.message.chat.id,
                message_id=cb.message.message_id,
                text=text,
                reply_markup=kb_menu(),
                disable_web_page_preview=True,
            )
            # Обновляем ui_state на это уведомление
            await set_ui_state(
                conn,
                cb.from_user.id,
                cb.message.chat.id,
                cb.message.message_id,
                "menu:home",
                None,
            )
        except Exception:
            # Если не удалось отредактировать (например, сообщение уже изменено), используем обычную логику
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
        # Обычная логика для single-message navigation
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


@router.callback_query(F.data == "menu:tasks")
async def menu_tasks(cb: CallbackQuery, bot, conn: aiosqlite.Connection) -> None:
    if not cb.from_user:
        return
    await cb.answer()

    if await is_user_banned(conn, cb.from_user.id):
        await bot.send_message(
            chat_id=cb.from_user.id,
            text="⛔ Доступ к боту для вас ограничен. Обратитесь к администратору.",
        )
        return
    # экрана "минутку, собираем задания..."
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text="Минутку, собираем вам задания...",
        reply_markup=None,
        screen="tasks:loading",
        payload=None,
    )
    await asyncio.sleep(1.5)

    sponsors = await get_active_task_sponsors(conn)
    if not sponsors:
        text = (
            "Не смог найти для вас предложения.\n\n"
            "Загляните попозже, я подготовлю для вас задания."
        )
        await edit_or_recreate(
            bot=bot,
            conn=conn,
            user_id=cb.from_user.id,
            chat_id=cb.message.chat.id,
            text=text,
            reply_markup=kb_back_to_menu(),
            screen="tasks:none",
            payload=None,
        )
        return

    from ..routers.start import sponsor_link

    # Строим список для отображения: показываем все (каналы, боты, сайты),
    # но если нет ни одного канала — не показываем сайты/боты вообще.
    has_channels = any(
        ((s["type"] or "channel").lower() if "type" in s.keys() else "channel") == "channel"
        and int(s["channel_id"]) != 0
        for s in sponsors
    )
    rows = []
    for s in sponsors:
        type_ = (s["type"] or "channel").lower() if "type" in s.keys() else "channel"
        if type_ in ("bot", "link") and not has_channels:
            continue
        rows.append(
            {
                "title": str(s["title"]),
                "link": sponsor_link(s) or "",
            }
        )

    text = "Для вас задания:\n\nПодпишитесь на каналы ниже, чтобы получить попытки."
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=text,
        reply_markup=kb_task_sponsors_list(rows) if rows else kb_back_to_menu(),
        screen="tasks:list",
        payload=None,
    )


@router.callback_query(F.data == "tasks:check_subs")
async def tasks_check_subs(cb: CallbackQuery, bot, conn: aiosqlite.Connection) -> None:
    from ..routers.start import sponsor_link, is_subscribed

    if not cb.from_user:
        return
    await cb.answer()

    # Загружаем все активные спонсоры-задания
    sponsors = await get_active_task_sponsors(conn)
    if not sponsors:
        await bot.send_message(
            chat_id=cb.from_user.id,
            text="Сейчас для вас нет активных заданий.",
        )
        return

    # Проверяем подписку только по каналам
    missing_channels = []
    for s in sponsors:
        type_ = (s["type"] or "channel").lower() if "type" in s.keys() else "channel"
        channel_id = int(s["channel_id"])
        if type_ == "channel" and channel_id != 0:
            ok = await is_subscribed(bot, conn, cb.from_user.id, channel_id)
            if not ok:
                missing_channels.append(s)

    has_channels = any(
        ((s["type"] or "channel").lower() if "type" in s.keys() else "channel") == "channel"
        and int(s["channel_id"]) != 0
        for s in sponsors
    )

    # Перестраиваем список показа (как в menu_tasks)
    rows = []
    for s in sponsors:
        type_ = (s["type"] or "channel").lower() if "type" in s.keys() else "channel"
        if type_ in ("bot", "link") and not has_channels:
            continue
        rows.append(
            {
                "title": str(s["title"]),
                "link": sponsor_link(s) or "",
            }
        )

    if missing_channels:
        text = "❌ Не на все каналы есть подписка.\n\nПодпишитесь на все каналы и проверьте ещё раз."
        await edit_or_recreate(
            bot=bot,
            conn=conn,
            user_id=cb.from_user.id,
            chat_id=cb.message.chat.id,
            text=text,
            reply_markup=kb_task_sponsors_list(rows) if rows else kb_back_to_menu(),
            screen="tasks:list",
            payload=None,
        )
        return

    # Все каналы выполнены — считаем бонусы по ещё не выданным спонсорам
    unrewarded = await get_unrewarded_task_sponsors(conn, cb.from_user.id)
    total_bonus = 0
    for s in unrewarded:
        bonus = int(s["bonus_attempts"])
        total_bonus += bonus
        await mark_sponsor_bonus_granted(conn, cb.from_user.id, int(s["id"]), bonus)

    if total_bonus > 0:
        await add_attempts(conn, cb.from_user.id, total_bonus)
        text = (
            f"✅ Задания выполнены! Вы получили <b>{total_bonus}</b> попыток.\n\n"
            "Чтобы получить новые задания, дождитесь появления новых спонсоров."
        )
    else:
        text = (
            "✅ На данный момент все задания уже были выполнены.\n\n"
            "Новые задания появятся, когда добавятся новые спонсоры."
        )

    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=text,
        reply_markup=kb_back_to_menu(),
        screen="tasks:done",
        payload=None,
    )


@router.callback_query(F.data == "menu:buy1")
async def menu_buy1(cb: CallbackQuery, bot, conn: aiosqlite.Connection) -> None:
    if not cb.from_user:
        return
    await cb.answer()

    if await is_user_banned(conn, cb.from_user.id):
        await bot.send_message(
            chat_id=cb.from_user.id,
            text="⛔ Доступ к боту для вас ограничен. Обратитесь к администратору.",
        )
        return

    # Цена в звёздах (Telegram Stars), задаётся в админке, по умолчанию 1
    price_stars = await get_setting_int(conn, "stars_price_per_attempt", 1)

    text = (
        f"🛒 <b>Покупка попытки</b>\n\n"
        f"Стоимость: <b>{price_stars}⭐</b>\n\n"
        "После оплаты попытка будет автоматически начислена на ваш счёт."
    )
    await bot.send_invoice(
        chat_id=cb.from_user.id,
        title="Paul Du Rove - попытка",
        description="Купите попытку и выиграйте подарки!",
        payload="buy_attempt_1",
        provider_token="",  # для Telegram Stars провайдер не требуется
        currency="XTR",
        prices=[LabeledPrice(label="1 попытка", amount=price_stars)],
        max_tip_amount=0,
        send_email_to_provider=False,
        disable_notification=False,
    )


@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery, bot, conn: aiosqlite.Connection) -> None:
    # Здесь можно добавить дополнительные проверки, если нужно
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message, bot, conn: aiosqlite.Connection) -> None:
    sp = message.successful_payment
    if not sp:
        return
    if sp.currency != "XTR":
        return

    user = message.from_user
    if not user:
        return

    # Сейчас у нас только один тип покупки — 1 попытка
    if sp.invoice_payload == "buy_attempt_1":
        await add_attempts(conn, user.id, 1)
        # Кнопка "Меню" после оплаты должна создавать новое сообщение меню,
        # не редактируя старое, поэтому используем отдельный callback.
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⟵ Меню", callback_data="menu:home_new")]
            ]
        )
        await message.answer(
            "✅ Оплата успешно завершена!\n\n"
            "Вам начислена <b>1 попытка</b>. Удачной игры! 🎮",
            reply_markup=markup,
        )


@router.callback_query(F.data == "menu:home_new")
async def menu_home_new(cb: CallbackQuery, bot, conn: aiosqlite.Connection) -> None:
    """
    Специальный «Меню» после оплаты: не редактирует старое сообщение,
    а создаёт новое и переносит на него single-message UI.
    """
    if not cb.from_user:
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
    text = (
        f"🎮 Попыток: <b>{attempts}</b>\n\n"
        "Как получить попытки:\n"
        "• 🎯 Задания — +1 за каждое\n"
        "• 🛒 Покупка — 5✨ = 1 попытка\n"
        "• 🤝 Пригласить друга — +4 за каждого\n\n"
        "Выберите действие ниже 👇"
    )
    msg = await bot.send_message(
        chat_id=cb.message.chat.id,
        text=text,
        reply_markup=kb_menu(),
    )
    # Переносим single-message UI на новое сообщение
    await set_ui_state(
        conn,
        cb.from_user.id,
        cb.message.chat.id,
        msg.message_id,
        "menu:home",
        None,
    )


@router.callback_query(F.data == "menu:refs_stub")
async def menu_refs(cb: CallbackQuery, bot, conn: aiosqlite.Connection) -> None:
    if not cb.from_user:
        return
    await cb.answer()
    await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text="Реферальная система скоро появится... 🔄",
        reply_markup=kb_back_to_menu(),
        screen="refs:stub",
        payload=None,
    )


