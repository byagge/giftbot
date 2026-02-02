from __future__ import annotations

from dataclasses import dataclass
from os import getenv

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: set[int]
    withdraw_review_chat_id: int | None


def load_config() -> Config:
    load_dotenv()
    bot_token = getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is not set in environment (.env).")

    admin_ids_raw = getenv("ADMIN_IDS", "").strip()
    admin_ids: set[int] = set()
    if admin_ids_raw:
        for x in admin_ids_raw.split(","):
            x = x.strip()
            if x:
                admin_ids.add(int(x))

    withdraw_chat_raw = getenv("WITHDRAW_REVIEW_CHAT_ID", "").strip()
    withdraw_review_chat_id = int(withdraw_chat_raw) if withdraw_chat_raw else None

    return Config(
        bot_token=bot_token,
        admin_ids=admin_ids,
        withdraw_review_chat_id=withdraw_review_chat_id,
    )


