from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    secret_key: str
    timezone: str
    admin_username: str
    admin_password: str
    preview_chat_id: str
    database_url: str
    media_dir: Path
    data_dir: Path
    telegram_updates_enabled: bool
    telegram_api_id: int
    telegram_api_hash: str
    telegram_session: str


@lru_cache
def get_settings() -> Settings:
    data_dir = Path(os.environ.get("DATA_DIR", "data"))
    media_dir = Path(os.environ.get("MEDIA_DIR", "media"))
    database_url = os.environ.get(
        "DATABASE_URL", f"sqlite:///{data_dir / 'telebot.db'}"
    )
    updates_flag = os.environ.get("TELEGRAM_UPDATES_ENABLED", "1").strip().lower()
    api_id_raw = os.environ.get("TELEGRAM_API_ID", "").strip()
    try:
        api_id = int(api_id_raw) if api_id_raw else 0
    except ValueError:
        api_id = 0
    return Settings(
        bot_token=os.environ.get("BOT_TOKEN", ""),
        secret_key=os.environ.get("SECRET_KEY", "change-me"),
        timezone=os.environ.get("TIMEZONE", "Asia/Singapore"),
        admin_username=os.environ.get("ADMIN_USERNAME", "admin"),
        admin_password=os.environ.get("ADMIN_PASSWORD", "change-me"),
        preview_chat_id=os.environ.get("PREVIEW_CHAT_ID", ""),
        database_url=database_url,
        media_dir=media_dir,
        data_dir=data_dir,
        telegram_updates_enabled=updates_flag not in ("0", "false", "no", "off"),
        telegram_api_id=api_id,
        telegram_api_hash=os.environ.get("TELEGRAM_API_HASH", "").strip(),
        telegram_session=os.environ.get("TELEGRAM_SESSION", "").strip(),
    )
