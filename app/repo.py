from __future__ import annotations

import json
from typing import Any

import aiosqlite

from .timeutil import now_ts


async def upsert_user(conn: aiosqlite.Connection, user_id: int, username: str | None, first_name: str | None, last_name: str | None) -> None:
    ts = now_ts()
    await conn.execute(
        """
        INSERT INTO users(user_id, username, first_name, last_name, created_at, updated_at)
        VALUES(?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
          username=excluded.username,
          first_name=excluded.first_name,
          last_name=excluded.last_name,
          updated_at=excluded.updated_at
        """,
        (user_id, username, first_name, last_name, ts, ts),
    )
    await conn.commit()


async def set_start_message_id(conn: aiosqlite.Connection, user_id: int, message_id: int) -> None:
    await conn.execute(
        "UPDATE users SET start_message_id=?, updated_at=? WHERE user_id=?",
        (message_id, now_ts(), user_id),
    )
    await conn.commit()


async def get_start_message_id(conn: aiosqlite.Connection, user_id: int) -> int | None:
    cur = await conn.execute("SELECT start_message_id FROM users WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    if not row or row["start_message_id"] is None:
        return None
    return int(row["start_message_id"])


async def get_user(conn: aiosqlite.Connection, user_id: int) -> aiosqlite.Row | None:
    cur = await conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return await cur.fetchone()


async def is_user_banned(conn: aiosqlite.Connection, user_id: int) -> bool:
    cur = await conn.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    return bool(row and int(row["is_banned"]) == 1)


async def list_users(conn: aiosqlite.Connection, limit: int = 50, offset: int = 0) -> list[aiosqlite.Row]:
    cur = await conn.execute(
        """
        SELECT *
        FROM users
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    )
    return list(await cur.fetchall())


async def set_user_ban(conn: aiosqlite.Connection, user_id: int, banned: bool) -> None:
    await conn.execute(
        "UPDATE users SET is_banned=?, updated_at=? WHERE user_id=?",
        (1 if banned else 0, now_ts(), user_id),
    )
    await conn.commit()


async def get_user_attempts(conn: aiosqlite.Connection, user_id: int) -> int:
    cur = await conn.execute("SELECT attempts FROM users WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    return int(row["attempts"]) if row else 0


async def add_attempts(conn: aiosqlite.Connection, user_id: int, delta: int) -> None:
    await conn.execute(
        "UPDATE users SET attempts = MAX(0, attempts + ?), updated_at=? WHERE user_id=?",
        (delta, now_ts(), user_id),
    )
    await conn.commit()


async def set_attempts(conn: aiosqlite.Connection, user_id: int, attempts: int) -> None:
    await conn.execute(
        "UPDATE users SET attempts=?, updated_at=? WHERE user_id=?",
        (max(0, attempts), now_ts(), user_id),
    )
    await conn.commit()


async def get_setting_float(conn: aiosqlite.Connection, key: str, default: float) -> float:
    cur = await conn.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = await cur.fetchone()
    if not row:
        return default
    try:
        return float(row["value"])
    except Exception:
        return default


async def set_setting(conn: aiosqlite.Connection, key: str, value: str) -> None:
    await conn.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    await conn.commit()


async def get_active_start_sponsors(conn: aiosqlite.Connection) -> list[aiosqlite.Row]:
    cur = await conn.execute(
        "SELECT * FROM start_sponsors WHERE is_active=1 ORDER BY sort_order ASC, id ASC"
    )
    return list(await cur.fetchall())


async def get_active_task_sponsors(conn: aiosqlite.Connection) -> list[aiosqlite.Row]:
    cur = await conn.execute(
        "SELECT * FROM sponsors WHERE is_active=1 ORDER BY sort_order ASC, id ASC"
    )
    return list(await cur.fetchall())


async def get_active_gifts(conn: aiosqlite.Connection) -> list[aiosqlite.Row]:
    cur = await conn.execute(
        "SELECT * FROM gifts WHERE is_active=1 ORDER BY sort_order ASC, id ASC"
    )
    return list(await cur.fetchall())


async def list_start_sponsors(conn: aiosqlite.Connection) -> list[aiosqlite.Row]:
    cur = await conn.execute(
        "SELECT * FROM start_sponsors ORDER BY is_active DESC, sort_order ASC, id ASC"
    )
    return list(await cur.fetchall())


async def list_task_sponsors(conn: aiosqlite.Connection) -> list[aiosqlite.Row]:
    cur = await conn.execute(
        "SELECT * FROM sponsors ORDER BY is_active DESC, sort_order ASC, id ASC"
    )
    return list(await cur.fetchall())


async def get_start_sponsor(conn: aiosqlite.Connection, sponsor_id: int) -> aiosqlite.Row | None:
    cur = await conn.execute("SELECT * FROM start_sponsors WHERE id=?", (sponsor_id,))
    return await cur.fetchone()


async def get_task_sponsor(conn: aiosqlite.Connection, sponsor_id: int) -> aiosqlite.Row | None:
    cur = await conn.execute("SELECT * FROM sponsors WHERE id=?", (sponsor_id,))
    return await cur.fetchone()


async def update_start_sponsor(
    conn: aiosqlite.Connection,
    sponsor_id: int,
    *,
    title: str,
    type_: str,
    channel_id: int,
    channel_username: str | None,
    invite_link: str | None,
    is_active: int,
) -> None:
    await conn.execute(
        """
        UPDATE start_sponsors
        SET title=?, type=?, channel_id=?, channel_username=?, invite_link=?, is_active=?
        WHERE id=?
        """,
        (title, type_, channel_id, channel_username, invite_link, is_active, sponsor_id),
    )
    await conn.commit()


async def update_task_sponsor(
    conn: aiosqlite.Connection,
    sponsor_id: int,
    *,
    title: str,
    type_: str,
    channel_id: int,
    channel_username: str | None,
    invite_link: str | None,
    bonus_attempts: int,
    is_active: int,
) -> None:
    await conn.execute(
        """
        UPDATE sponsors
        SET title=?, type=?, channel_id=?, channel_username=?, invite_link=?, bonus_attempts=?, is_active=?
        WHERE id=?
        """,
        (
            title,
            type_,
            channel_id,
            channel_username,
            invite_link,
            bonus_attempts,
            is_active,
            sponsor_id,
        ),
    )
    await conn.commit()


async def delete_start_sponsor(conn: aiosqlite.Connection, sponsor_id: int) -> None:
    await conn.execute("DELETE FROM start_sponsors WHERE id=?", (sponsor_id,))
    await conn.commit()


async def delete_task_sponsor(conn: aiosqlite.Connection, sponsor_id: int) -> None:
    await conn.execute("DELETE FROM sponsors WHERE id=?", (sponsor_id,))
    await conn.commit()


async def get_gift_count_active(conn: aiosqlite.Connection) -> int:
    cur = await conn.execute("SELECT COUNT(1) AS c FROM gifts WHERE is_active=1")
    row = await cur.fetchone()
    return int(row["c"]) if row else 0


async def get_gift(conn: aiosqlite.Connection, gift_id: int) -> aiosqlite.Row | None:
    cur = await conn.execute("SELECT * FROM gifts WHERE id=?", (gift_id,))
    return await cur.fetchone()


async def list_gifts(conn: aiosqlite.Connection) -> list[aiosqlite.Row]:
    cur = await conn.execute(
        "SELECT * FROM gifts ORDER BY is_active DESC, sort_order ASC, id ASC"
    )
    return list(await cur.fetchall())


async def add_inventory_item(conn: aiosqlite.Connection, user_id: int, gift_id: int) -> int:
    ts = now_ts()
    cur = await conn.execute(
        "INSERT INTO inventory(user_id, gift_id, won_at, status) VALUES(?, ?, ?, 'won')",
        (user_id, gift_id, ts),
    )
    await conn.commit()
    return int(cur.lastrowid)


async def list_inventory(conn: aiosqlite.Connection, user_id: int) -> list[aiosqlite.Row]:
    cur = await conn.execute(
        """
        SELECT i.*, g.title AS gift_title, g.emoji AS gift_emoji
        FROM inventory i
        JOIN gifts g ON g.id=i.gift_id
        WHERE i.user_id=?
        ORDER BY i.id DESC
        """,
        (user_id,),
    )
    return list(await cur.fetchall())


async def get_inventory_item(conn: aiosqlite.Connection, inventory_id: int, user_id: int) -> aiosqlite.Row | None:
    cur = await conn.execute(
        """
        SELECT i.*, g.title AS gift_title, g.emoji AS gift_emoji, g.photo_file_id, g.price
        FROM inventory i
        JOIN gifts g ON g.id=i.gift_id
        WHERE i.id=? AND i.user_id=?
        """,
        (inventory_id, user_id),
    )
    return await cur.fetchone()


async def set_ui_state(conn: aiosqlite.Connection, user_id: int, chat_id: int, message_id: int, screen: str, payload: dict[str, Any] | None) -> None:
    ts = now_ts()
    payload_json = json.dumps(payload or {}, ensure_ascii=False)
    await conn.execute(
        """
        INSERT INTO ui_state(user_id, chat_id, message_id, screen, payload_json, updated_at)
        VALUES(?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
          chat_id=excluded.chat_id,
          message_id=excluded.message_id,
          screen=excluded.screen,
          payload_json=excluded.payload_json,
          updated_at=excluded.updated_at
        """,
        (user_id, chat_id, message_id, screen, payload_json, ts),
    )
    await conn.commit()


async def get_ui_state(conn: aiosqlite.Connection, user_id: int) -> aiosqlite.Row | None:
    cur = await conn.execute("SELECT * FROM ui_state WHERE user_id=?", (user_id,))
    return await cur.fetchone()


async def set_inventory_status(
    conn: aiosqlite.Connection,
    inventory_id: int,
    status: str,
    *,
    withdraw_requested: bool = False,
    withdrawn: bool = False,
) -> None:
    ts = now_ts()
    fields = ["status=?", "won_at=won_at"]
    params: list[Any] = [status]
    if withdraw_requested:
        fields.append("withdraw_requested_at=?")
        params.append(ts)
    if withdrawn:
        fields.append("withdrawn_at=?")
        params.append(ts)
    params.append(inventory_id)
    await conn.execute(
        f"UPDATE inventory SET {', '.join(fields)} WHERE id=?",
        params,
    )
    await conn.commit()


async def get_unrewarded_task_sponsors(conn: aiosqlite.Connection, user_id: int) -> list[aiosqlite.Row]:
    """
    Список активных спонсоров-заданий, по которым ещё не был выдан бонус user_id.
    """
    cur = await conn.execute(
        """
        SELECT s.*
        FROM sponsors s
        LEFT JOIN sponsor_bonus_grants g
          ON g.user_id = ? AND g.sponsor_id = s.id
        WHERE s.is_active = 1 AND g.id IS NULL
        ORDER BY s.sort_order ASC, s.id ASC
        """,
        (user_id,),
    )
    return list(await cur.fetchall())


async def mark_sponsor_bonus_granted(conn: aiosqlite.Connection, user_id: int, sponsor_id: int, attempts: int) -> None:
    ts = now_ts()
    await conn.execute(
        """
        INSERT INTO sponsor_bonus_grants(user_id, sponsor_id, granted_attempts, granted_at)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(user_id, sponsor_id) DO UPDATE SET
          granted_attempts = excluded.granted_attempts,
          granted_at = excluded.granted_at,
          is_revoked = 0,
          revoked_at = NULL
        """,
        (user_id, sponsor_id, attempts, ts),
    )
    await conn.commit()


async def update_gift(
    conn: aiosqlite.Connection,
    gift_id: int,
    *,
    title: str,
    price: int,
    drop_chance: float,
    emoji: str | None,
    is_active: int,
) -> None:
    await conn.execute(
        """
        UPDATE gifts
        SET title=?, price=?, drop_chance=?, emoji=?, is_active=?
        WHERE id=?
        """,
        (title, price, drop_chance, emoji, is_active, gift_id),
    )
    await conn.commit()


async def delete_gift(conn: aiosqlite.Connection, gift_id: int) -> None:
    await conn.execute("DELETE FROM gifts WHERE id=?", (gift_id,))
    await conn.commit()


