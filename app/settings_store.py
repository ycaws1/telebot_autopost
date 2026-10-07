from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppSetting

KEY_PREVIEW_CHAT_ID = "preview_chat_id"
KEY_UPDATES_OFFSET = "telegram_updates_offset"
KEY_BOT_USERNAME = "bot_username"


def get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.get(AppSetting, key)
    if row is None:
        return default
    return row.value


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    db.commit()


def get_preview_chat_id(db: Session | None = None) -> str:
    """Prefer DB setting when the key exists (including empty after reset).

    Env PREVIEW_CHAT_ID is only used when the DB has never stored a value.
    """
    if db is not None:
        row = db.get(AppSetting, KEY_PREVIEW_CHAT_ID)
        if row is not None:
            return row.value or ""
    return get_settings().preview_chat_id


def set_preview_chat_id(db: Session, chat_id: str) -> None:
    set_setting(db, KEY_PREVIEW_CHAT_ID, str(chat_id).strip())


def clear_preview_chat_id(db: Session) -> None:
    """Clear saved preview so Setup no longer treats it as configured.

    Stores an empty value (instead of deleting) so env PREVIEW_CHAT_ID
    cannot repopulate the checklist after a wizard reset.
    """
    set_setting(db, KEY_PREVIEW_CHAT_ID, "")
