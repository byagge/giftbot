from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def kb_start() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🎁 Выбрать подарок", callback_data="start:choose_gift")
    b.adjust(1)
    return b.as_markup()


def kb_back_to_menu() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⟵ Меню", callback_data="menu:home")
    return b.as_markup()


def kb_menu() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🎮 Играть", callback_data="menu:play")
    b.button(text="🎯 Задания", callback_data="menu:tasks")
    b.button(text="🛒 Покупка", callback_data="menu:buy1")
    b.button(text="🤝 Пригласить друга", callback_data="menu:refs_stub")
    b.button(text="👤 Профиль", callback_data="menu:profile")
    b.adjust(2, 1, 1, 1, 1)
    return b.as_markup()


def kb_check_subscriptions() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Я подписался(лась)", callback_data="start:check_subs")
    b.button(text="⟵ Назад", callback_data="start:back")
    b.adjust(1)
    return b.as_markup()


def kb_sponsors_list(rows: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for r in rows:
        title = r.get("title") or "Спонсор"
        link = r.get("link") or ""
        if link:
            b.row(InlineKeyboardButton(text=f"📢 {title}", url=link))
    b.button(text="✅ Проверить подписки", callback_data="start:check_subs")
    b.button(text="⟵ Назад", callback_data="start:back")
    b.adjust(1)
    return b.as_markup()


def kb_task_sponsors_list(rows: list[dict]) -> InlineKeyboardMarkup:
    """
    Клавиатура для раздела «Задания» (спонсоры).
    Проверка идёт через callback data tasks:check_subs.
    """
    b = InlineKeyboardBuilder()
    for r in rows:
        title = r.get("title") or "Спонсор"
        link = r.get("link") or ""
        if link:
            b.row(InlineKeyboardButton(text=f"📢 {title}", url=link))
    b.button(text="✅ Проверить задания", callback_data="tasks:check_subs")
    b.button(text="⟵ Назад", callback_data="menu:home")
    b.adjust(1)
    return b.as_markup()


def kb_game_controls(can_take: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if can_take:
        b.button(text="🎁 Забрать", callback_data="game:take")
    b.button(text="⟵ Меню", callback_data="menu:home")
    b.adjust(1)
    return b.as_markup()


def kb_game_board(symbols: list[str]) -> InlineKeyboardMarkup:
    """
    symbols: тексты для 36 клеток (6×6).
    """
    b = InlineKeyboardBuilder()
    for r in range(6):
        row_buttons = []
        for c in range(6):
            i = r * 6 + c
            text = symbols[i]
            cb = f"game:cell:{i}" if text == "⬜" else "game:noop"
            row_buttons.append(InlineKeyboardButton(text=text, callback_data=cb))
        b.row(*row_buttons)
    return b.as_markup()


def kb_admin_menu() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    # Спонсоры
    b.button(text="📢 Старт-спонсоры", callback_data="admin:list_start_sponsors")
    b.button(text="🎯 Спонсоры (задания)", callback_data="admin:list_task_sponsors")
    # Подарки
    b.button(text="🎁 Подарки", callback_data="admin:list_gifts")
    # Пользователи
    b.button(text="👥 Пользователи", callback_data="admin:list_users")
    # Настройки / статистика
    b.button(text="📨 Рассылка", callback_data="admin:broadcast")
    b.button(text="⭐ Цена попытки (Stars)", callback_data="admin:set_stars_price")
    b.button(text="📊 Статистика", callback_data="admin:stats")
    b.button(text="⚙️ Шанс подарка (глоб.)", callback_data="admin:set_global_chance")
    b.adjust(1, 1, 1, 1, 1, 2)
    return b.as_markup()


def kb_admin_back() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⟵ Админ-меню", callback_data="admin:menu")
    return b.as_markup()


def kb_profile_menu() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🎁 Инвентарь", callback_data="profile:inventory")
    b.row(InlineKeyboardButton(text="💬 Поддержка", url="https://t.me/DuRoveSupportBot"))
    b.button(text="⟵ Меню", callback_data="menu:home")
    b.adjust(1, 1, 1)
    return b.as_markup()



