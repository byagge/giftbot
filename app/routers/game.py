from __future__ import annotations

import json
import random
from typing import Any

import aiosqlite
from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.types import InlineKeyboardMarkup

from ..keyboards import kb_back_to_menu, kb_game_board, kb_game_controls
from ..repo import (
    add_attempts,
    add_inventory_item,
    get_active_gifts,
    get_gift_count_active,
    get_setting_float,
    get_ui_state,
    get_user_attempts,
    is_user_banned,
    set_ui_state,
)
from ..ui import edit_or_recreate

router = Router(name="game")

GRID_SIZE = 6
CELL_COUNT = GRID_SIZE * GRID_SIZE


def _new_game_payload(cell_gifts: list[Any]) -> dict[str, Any]:
    return {
        "cells": [0] * CELL_COUNT,
        "cell_gifts": cell_gifts,  # list[None | {"gift_id", "title", "emoji"}]
        "pending_wins": [],  # list[{"gift_id": int, "title": str}]
        "finished": False,
    }


def _render_text(attempts: int, pending: list[dict[str, Any]]) -> str:
    wins = len(pending)
    return (
        "Выиграйте подарок!\n\n"
        f"Попытки: <b>{attempts}</b>\n"
        f"Выигрыши (не забраны): <b>{wins}</b>\n\n"
        "Выберите клетку для её раскрытия. Если вы выбрали правильно — выиграете подарок.\n"
        "Если нажмёшь «Забрать», выигрыши попадут в инвентарь.\n"
        "Если попытки закончатся — незабранные выигрыши сгорят."
    )


def _pick_gift_weighted(gifts: list[aiosqlite.Row]) -> aiosqlite.Row:
    weights = [max(0.0, float(g["drop_chance"])) for g in gifts]
    total = sum(weights)
    if total <= 0:
        return random.choice(gifts)
    r = random.random() * total
    acc = 0.0
    for g, w in zip(gifts, weights):
        acc += w
        if r <= acc:
            return g
    return gifts[-1]


async def _load_game_payload(conn: aiosqlite.Connection, user_id: int) -> dict[str, Any]:
    state = await get_ui_state(conn, user_id)
    if not state or not state["payload_json"]:
        # при отсутствии состояния создаём пустую доску без подарков
        return _new_game_payload([None] * CELL_COUNT)
    try:
        payload = json.loads(state["payload_json"])
        if "cells" not in payload or "pending_wins" not in payload or "cell_gifts" not in payload:
            return _new_game_payload([None] * CELL_COUNT)
        if not isinstance(payload["cells"], list) or len(payload["cells"]) != CELL_COUNT:
            return _new_game_payload([None] * CELL_COUNT)
        if not isinstance(payload["cell_gifts"], list) or len(payload["cell_gifts"]) != CELL_COUNT:
            return _new_game_payload([None] * CELL_COUNT)
        if "finished" not in payload:
            payload["finished"] = False
        return payload
    except Exception:
        return _new_game_payload([None] * CELL_COUNT)


def _build_symbols(cells: list[int], cell_gifts: list[Any]) -> list[str]:
    symbols: list[str] = []
    for i in range(CELL_COUNT):
        opened = cells[i] == 1
        gift = cell_gifts[i]
        if not opened:
            symbols.append("⬜")
        else:
            if gift:
                emoji = gift.get("emoji") or "🎁"
                symbols.append(str(emoji))
            else:
                symbols.append("❌")
    return symbols


async def _save_game_payload(conn: aiosqlite.Connection, user_id: int, chat_id: int, message_id: int, payload: dict[str, Any]) -> None:
    await set_ui_state(conn, user_id, chat_id, message_id, "game:play", payload)


@router.callback_query(F.data == "menu:play")
async def open_game(cb: CallbackQuery, bot, conn: aiosqlite.Connection) -> None:
    if not cb.from_user:
        return
    await cb.answer()

    if await is_user_banned(conn, cb.from_user.id):
        await bot.send_message(
            chat_id=cb.from_user.id,
            text="⛔ Доступ к боту для вас ограничен. Обратитесь к администратору.",
        )
        return

    attempts = await get_user_attempts(conn, cb.from_user.id)
    if attempts <= 0:
        await edit_or_recreate(
            bot=bot,
            conn=conn,
            user_id=cb.from_user.id,
            chat_id=cb.message.chat.id,
            text=(
                "Чтобы играть, нужны попытки.\n\n"
                "Их можно получить за подписки на спонсоров (раздел «Задания») "
                "или купить (пока заглушка)."
            ),
            reply_markup=kb_back_to_menu(),
            screen="game:no_attempts",
            payload=None,
        )
        return

    # подготавливаем поле с подарками на клетках
    gifts = await get_active_gifts(conn)
    cell_gifts: list[Any] = [None] * CELL_COUNT
    if gifts:
        base_chance = await get_setting_float(conn, "game_cell_gift_chance", 0.10)
        base_chance = max(0.0, min(1.0, base_chance))
        for i in range(CELL_COUNT):
            if random.random() < base_chance:
                g = _pick_gift_weighted(gifts)
                cell_gifts[i] = {
                    "gift_id": int(g["id"]),
                    "title": str(g["title"]),
                    "emoji": g["emoji"],
                }

    payload = _new_game_payload(cell_gifts)
    text = _render_text(attempts, payload["pending_wins"])
    symbols = _build_symbols(payload["cells"], payload["cell_gifts"])
    markup = kb_game_board(symbols)
    msg_id = await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=text,
        reply_markup=markup,
        screen="game:play",
        payload=payload,
    )
    await _save_game_payload(conn, cb.from_user.id, cb.message.chat.id, msg_id, payload)


@router.callback_query(F.data == "game:noop")
async def game_noop(cb: CallbackQuery) -> None:
    await cb.answer()


@router.callback_query(F.data.startswith("game:cell:"))
async def game_cell(cb: CallbackQuery, bot, conn: aiosqlite.Connection) -> None:
    if not cb.from_user or not cb.message:
        return
    await cb.answer()

    if await is_user_banned(conn, cb.from_user.id):
        await bot.send_message(
            chat_id=cb.from_user.id,
            text="⛔ Доступ к боту для вас ограничен. Обратитесь к администратору.",
        )
        return

    attempts = await get_user_attempts(conn, cb.from_user.id)
    if attempts <= 0:
        # if user somehow clicks old keyboard
        await edit_or_recreate(
            bot=bot,
            conn=conn,
            user_id=cb.from_user.id,
            chat_id=cb.message.chat.id,
            text="Попытки закончились. Вернись в меню.",
            reply_markup=kb_back_to_menu(),
            screen="game:no_attempts",
            payload=None,
        )
        return

    try:
        idx = int(cb.data.split(":")[-1])
    except Exception:
        return
    if idx < 0 or idx >= CELL_COUNT:
        return

    payload = await _load_game_payload(conn, cb.from_user.id)
    if payload.get("finished"):
        await cb.answer("Игра уже завершена. Вернитесь в меню и начните новую игру.", show_alert=True)
        return
    if payload["cells"][idx] == 1:
        return

    payload["cells"][idx] = 1
    cell_gifts = payload.get("cell_gifts") or [None] * CELL_COUNT
    cell_gift = cell_gifts[idx]

    # Spend attempt per opened cell
    await add_attempts(conn, cb.from_user.id, -1)
    attempts = attempts - 1

    won = False
    won_gift: aiosqlite.Row | None = None

    if cell_gift:
        won = True
        payload["pending_wins"].append(
            {"gift_id": int(cell_gift["gift_id"]), "title": str(cell_gift["title"])}
        )

    # If attempts ended -> раскрываем все клетки с подарками и сжигаем незабранные выигрыши
    lose_msg = ""
    if attempts <= 0:
        # помечаем все клетки, где были подарки
        for i in range(CELL_COUNT):
            if payload["cells"][i] == 0 and cell_gifts[i]:
                payload["cells"][i] = 1
        if payload["pending_wins"]:
            payload["pending_wins"] = []
            lose_msg = "\n\n<b>Поражение:</b> попытки закончились — незабранные выигрыши сгорели."
        payload["finished"] = True

    text = _render_text(max(0, attempts), payload["pending_wins"])
    if won and won_gift:
        text = (
            f"🎉 Ты выиграл(а) подарок: <b>{won_gift['title']}</b>\n\n"
            "Хочешь забрать или продолжить? Если продолжишь и закончатся попытки — всё сгорит.\n\n"
            + _render_text(max(0, attempts), payload["pending_wins"])
        )
    if lose_msg:
        text += lose_msg + "\n\nВот где прятались подарки."

    symbols = _build_symbols(payload["cells"], cell_gifts)
    board = kb_game_board(symbols)
    controls = kb_game_controls(can_take=len(payload["pending_wins"]) > 0)
    # Combine: board + controls rows
    markup = InlineKeyboardMerge.merge(board, controls)

    msg_id = await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=text,
        reply_markup=markup,
        screen="game:play",
        payload=payload,
    )
    await _save_game_payload(conn, cb.from_user.id, cb.message.chat.id, msg_id, payload)


@router.callback_query(F.data == "game:take")
async def game_take(cb: CallbackQuery, bot, conn: aiosqlite.Connection) -> None:
    if not cb.from_user or not cb.message:
        return
    await cb.answer()

    if await is_user_banned(conn, cb.from_user.id):
        await bot.send_message(
            chat_id=cb.from_user.id,
            text="⛔ Доступ к боту для вас ограничен. Обратитесь к администратору.",
        )
        return

    payload = await _load_game_payload(conn, cb.from_user.id)
    if payload.get("finished"):
        await cb.answer("Игра уже завершена. Вернитесь в меню и начните новую игру.", show_alert=True)
        return
    pending = payload.get("pending_wins") or []
    if not pending:
        await cb.answer("Нет выигрышей для забора.", show_alert=False)
        return

    for w in pending:
        gift_id = int(w["gift_id"])
        await add_inventory_item(conn, cb.from_user.id, gift_id)

    payload["pending_wins"] = []
    payload["finished"] = True
    text = "✅ Выигрыши добавлены в инвентарь.\n\n" + _render_text(
        await get_user_attempts(conn, cb.from_user.id),
        payload["pending_wins"],
    )
    symbols = _build_symbols(payload["cells"], payload.get("cell_gifts") or [None] * CELL_COUNT)
    board = kb_game_board(symbols)
    controls = kb_game_controls(can_take=False)
    markup = InlineKeyboardMerge.merge(board, controls)

    msg_id = await edit_or_recreate(
        bot=bot,
        conn=conn,
        user_id=cb.from_user.id,
        chat_id=cb.message.chat.id,
        text=text,
        reply_markup=markup,
        screen="game:play",
        payload=payload,
    )
    await _save_game_payload(conn, cb.from_user.id, cb.message.chat.id, msg_id, payload)


class InlineKeyboardMerge:
    @staticmethod
    def merge(*markups) -> InlineKeyboardMarkup:
        inline_keyboard = []
        for m in markups:
            if not m:
                continue
            if isinstance(m, InlineKeyboardMarkup):
                inline_keyboard.extend(m.inline_keyboard)
        return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


