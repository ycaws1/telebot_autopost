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


@lru_cache
def get_settings() -> Settings:
    data_dir = Path(os.environ.get("DATA_DIR", "data"))
    media_dir = Path(os.environ.get("MEDIA_DIR", "media"))
    database_url = os.environ.get(
        "DATABASE_URL", f"sqlite:///{data_dir / 'telebot.db'}"
    )
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
    )
