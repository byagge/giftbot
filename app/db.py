from __future__ import annotations

import aiosqlite


async def connect(db_path: str) -> aiosqlite.Connection:
    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA foreign_keys = ON;")
    await conn.execute("PRAGMA journal_mode = WAL;")
    await conn.execute("PRAGMA synchronous = NORMAL;")
    conn.row_factory = aiosqlite.Row
    return conn


async def init_db(conn: aiosqlite.Connection) -> None:
    # Users + single-message UI state
    await conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
          user_id           INTEGER PRIMARY KEY,
          username          TEXT,
          first_name        TEXT,
          last_name         TEXT,
          created_at        INTEGER NOT NULL,
          updated_at        INTEGER NOT NULL,
          attempts          INTEGER NOT NULL DEFAULT 0,
          start_message_id  INTEGER
        );

        CREATE TABLE IF NOT EXISTS ui_state (
          user_id           INTEGER PRIMARY KEY,
          chat_id           INTEGER NOT NULL,
          message_id        INTEGER NOT NULL,
          screen            TEXT NOT NULL,
          payload_json      TEXT,
          updated_at        INTEGER NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );

        -- Sponsors
        -- type: 'channel' | 'bot' | 'link'
        CREATE TABLE IF NOT EXISTS start_sponsors (
          id                INTEGER PRIMARY KEY AUTOINCREMENT,
          title             TEXT NOT NULL,
          type              TEXT NOT NULL DEFAULT 'channel',
          channel_id        INTEGER NOT NULL,
          channel_username  TEXT,
          invite_link       TEXT,
          is_active         INTEGER NOT NULL DEFAULT 1,
          sort_order        INTEGER NOT NULL DEFAULT 0
        );

        -- type: 'channel' | 'bot' | 'link'
        CREATE TABLE IF NOT EXISTS sponsors (
          id                INTEGER PRIMARY KEY AUTOINCREMENT,
          title             TEXT NOT NULL,
          type              TEXT NOT NULL DEFAULT 'channel',
          channel_id        INTEGER NOT NULL,
          channel_username  TEXT,
          invite_link       TEXT,
          bonus_attempts    INTEGER NOT NULL DEFAULT 1,
          is_active         INTEGER NOT NULL DEFAULT 1,
          sort_order        INTEGER NOT NULL DEFAULT 0
        );

        -- Gifts catalog (used by the game)
        CREATE TABLE IF NOT EXISTS gifts (
          id                INTEGER PRIMARY KEY AUTOINCREMENT,
          title             TEXT NOT NULL,
          emoji             TEXT,
          photo_file_id     TEXT,
          price             INTEGER NOT NULL DEFAULT 0,
          drop_chance       REAL NOT NULL DEFAULT 0.10,
          is_active         INTEGER NOT NULL DEFAULT 1,
          sort_order        INTEGER NOT NULL DEFAULT 0
        );

        -- Inventory (won gifts)
        CREATE TABLE IF NOT EXISTS inventory (
          id                INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id           INTEGER NOT NULL,
          gift_id           INTEGER NOT NULL,
          won_at            INTEGER NOT NULL,
          status            TEXT NOT NULL DEFAULT 'won', -- won | withdraw_pending | withdrawn
          withdraw_requested_at INTEGER,
          withdrawn_at      INTEGER,
          FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
          FOREIGN KEY(gift_id) REFERENCES gifts(id) ON DELETE RESTRICT
        );

        -- Track sponsor bonus grants and possible penalty (unsubscribe -> warning -> deduct within 24h)
        CREATE TABLE IF NOT EXISTS sponsor_bonus_grants (
          id                INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id           INTEGER NOT NULL,
          sponsor_id        INTEGER NOT NULL,
          granted_attempts  INTEGER NOT NULL,
          granted_at        INTEGER NOT NULL,
          is_revoked        INTEGER NOT NULL DEFAULT 0,
          revoked_at        INTEGER,
          revoke_scheduled_at INTEGER,
          warned_at         INTEGER,
          FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
          FOREIGN KEY(sponsor_id) REFERENCES sponsors(id) ON DELETE CASCADE,
          UNIQUE(user_id, sponsor_id)
        );

        -- Withdrawal requests (for admin/mod chat)
        CREATE TABLE IF NOT EXISTS withdraw_requests (
          id                INTEGER PRIMARY KEY AUTOINCREMENT,
          inventory_id      INTEGER NOT NULL,
          user_id           INTEGER NOT NULL,
          created_at        INTEGER NOT NULL,
          status            TEXT NOT NULL DEFAULT 'pending', -- pending | approved | rejected
          processed_at      INTEGER,
          processed_by      INTEGER,
          note             TEXT,
          FOREIGN KEY(inventory_id) REFERENCES inventory(id) ON DELETE CASCADE,
          FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );

        -- Settings (single row)
        CREATE TABLE IF NOT EXISTS settings (
          key               TEXT PRIMARY KEY,
          value             TEXT NOT NULL
        );

        -- User reminders (follow-up / inactivity notifications)
        CREATE TABLE IF NOT EXISTS user_reminders (
          user_id           INTEGER PRIMARY KEY,
          last_activity_ts  INTEGER NOT NULL,
          next_reminder_ts  INTEGER,
          stage             INTEGER NOT NULL DEFAULT 0,
          first_sequence_done INTEGER NOT NULL DEFAULT 0,
          FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
        """
    )

    # Soft-migrations for existing DBs
    cur = await conn.execute("PRAGMA table_info(users)")
    cols = {row["name"] for row in await cur.fetchall()}
    if "start_message_id" not in cols:
        await conn.execute("ALTER TABLE users ADD COLUMN start_message_id INTEGER;")
    # бан пользователя: 0 / 1
    if "is_banned" not in cols:
        await conn.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER NOT NULL DEFAULT 0;")

    cur = await conn.execute("PRAGMA table_info(gifts)")
    cols_g = {row["name"] for row in await cur.fetchall()}
    if "emoji" not in cols_g:
        await conn.execute("ALTER TABLE gifts ADD COLUMN emoji TEXT;")

    # soft‑migration для типов спонсоров
    cur = await conn.execute("PRAGMA table_info(start_sponsors)")
    cols_ss = {row["name"] for row in await cur.fetchall()}
    if "type" not in cols_ss:
        await conn.execute("ALTER TABLE start_sponsors ADD COLUMN type TEXT NOT NULL DEFAULT 'channel';")

    cur = await conn.execute("PRAGMA table_info(sponsors)")
    cols_s = {row["name"] for row in await cur.fetchall()}
    if "type" not in cols_s:
        await conn.execute("ALTER TABLE sponsors ADD COLUMN type TEXT NOT NULL DEFAULT 'channel';")

    # Default settings
    await conn.execute(
        "INSERT OR IGNORE INTO settings(key, value) VALUES('game_cell_gift_chance', '0.10');"
    )
    await conn.execute(
        "INSERT OR IGNORE INTO settings(key, value) VALUES('stars_price_per_attempt', '1');"
    )
    await conn.commit()


