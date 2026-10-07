from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppSetting
from app.settings_store import get_setting, set_setting

if TYPE_CHECKING:
    from app.telegram_client import MediaItem

KEY_API_ID = "telegram_api_id"
KEY_API_HASH = "telegram_api_hash"
KEY_USER_SESSION = "telegram_user_session"
KEY_USER_DISPLAY = "telegram_user_display"
KEY_AUTH_PHONE = "telegram_auth_phone"
KEY_AUTH_HASH = "telegram_auth_phone_code_hash"
KEY_AUTH_PENDING_SESSION = "telegram_auth_pending_session"
KEY_AUTH_NEEDS_PASSWORD = "telegram_auth_needs_password"


class TelegramUserError(Exception):
    pass


def get_api_id(db: Session | None = None) -> int:
    """Prefer DB when the key exists (including empty after clear); else env."""
    if db is not None:
        row = db.get(AppSetting, KEY_API_ID)
        if row is not None:
            raw = (row.value or "").strip()
            if not raw:
                return 0
            try:
                return int(raw)
            except ValueError:
                return 0
    return get_settings().telegram_api_id


def get_api_hash(db: Session | None = None) -> str:
    if db is not None:
        row = db.get(AppSetting, KEY_API_HASH)
        if row is not None:
            return (row.value or "").strip()
    return get_settings().telegram_api_hash


def set_api_credentials(db: Session, api_id: str | int, api_hash: str) -> None:
    api_id_s = str(api_id).strip()
    api_hash_s = (api_hash or "").strip()
    if not api_id_s or not api_id_s.isdigit() or int(api_id_s) <= 0:
        raise TelegramUserError("API id must be a positive number from my.telegram.org")
    if not api_hash_s or len(api_hash_s) < 8:
        raise TelegramUserError("API hash looks invalid — paste the full hash from my.telegram.org")
    set_setting(db, KEY_API_ID, api_id_s)
    set_setting(db, KEY_API_HASH, api_hash_s)


def api_credentials_configured(db: Session | None = None) -> bool:
    return bool(get_api_id(db) and get_api_hash(db))


def get_user_session(db: Session | None = None) -> str:
    """Prefer DB when the key exists (including empty after logout); else env."""
    if db is not None:
        row = db.get(AppSetting, KEY_USER_SESSION)
        if row is not None:
            return row.value or ""
    return get_settings().telegram_session


def user_client_configured(db: Session | None = None) -> bool:
    return api_credentials_configured(db) and bool(get_user_session(db))


def user_auth_status(db: Session) -> dict[str, Any]:
    """State for the Setup UI user-login section."""
    session = get_user_session(db)
    db_session_row = db.get(AppSetting, KEY_USER_SESSION)
    env_session = get_settings().telegram_session
    from_env_only = bool(
        session
        and env_session
        and (db_session_row is None or not (db_session_row.value or ""))
    )
    api_id = get_api_id(db)
    api_hash = get_api_hash(db)
    return {
        "api_ok": bool(api_id and api_hash),
        "api_id": str(api_id) if api_id else "",
        "api_hash_set": bool(api_hash),
        "session_ok": bool(session),
        "display_name": get_setting(db, KEY_USER_DISPLAY, ""),
        "pending_phone": get_setting(db, KEY_AUTH_PHONE, ""),
        "needs_password": get_setting(db, KEY_AUTH_NEEDS_PASSWORD, "") == "1",
        "from_env_only": from_env_only,
    }


def _clear_auth_pending(db: Session) -> None:
    for key in (
        KEY_AUTH_PHONE,
        KEY_AUTH_HASH,
        KEY_AUTH_PENDING_SESSION,
        KEY_AUTH_NEEDS_PASSWORD,
    ):
        set_setting(db, key, "")


def clear_user_session(db: Session) -> None:
    set_setting(db, KEY_USER_SESSION, "")
    set_setting(db, KEY_USER_DISPLAY, "")
    _clear_auth_pending(db)


def clear_api_credentials(db: Session) -> None:
    """Clear saved API id/hash (empty rows override env bootstrap)."""
    set_setting(db, KEY_API_ID, "")
    set_setting(db, KEY_API_HASH, "")


def _peer(chat_id: str):
    value = (chat_id or "").strip()
    if not value:
        raise TelegramUserError("Channel chat id is empty")
    if value.startswith("@"):
        return value
    if value.lstrip("-").isdigit():
        return int(value)
    return value


def _normalize_phone(phone: str) -> str:
    """Strip spaces/dashes; keep leading + and digits only."""
    raw = (phone or "").strip()
    if not raw:
        return ""
    keep_plus = raw.startswith("+")
    digits = "".join(c for c in raw if c.isdigit())
    if not digits:
        return ""
    return ("+" if keep_plus else "") + digits


async def start_user_login(db: Session, phone: str) -> str:
    """Send login code to phone; store pending Telethon session for the next step."""
    if not api_credentials_configured(db):
        raise TelegramUserError(
            "Save API id and API hash in Setup first (from my.telegram.org)"
        )
    phone = _normalize_phone(phone)
    if not phone.startswith("+") or len(phone) < 10:
        raise TelegramUserError(
            "Enter the full number with country code, e.g. +6591234567 "
            "(Singapore mobiles are +65 + 8 digits)"
        )

    from telethon import TelegramClient
    from telethon.errors import PhoneNumberInvalidError
    from telethon.sessions import StringSession

    client = TelegramClient(
        StringSession(),
        get_api_id(db),
        get_api_hash(db),
    )
    await client.connect()
    try:
        try:
            sent = await client.send_code_request(phone)
        except PhoneNumberInvalidError as exc:
            raise TelegramUserError(
                f"Telegram rejected {phone} as invalid. Check country code and digit count "
                "(no spaces). Example: +6591234567"
            ) from exc
        pending = client.session.save()
        set_setting(db, KEY_AUTH_PHONE, phone)
        set_setting(db, KEY_AUTH_HASH, sent.phone_code_hash)
        set_setting(db, KEY_AUTH_PENDING_SESSION, pending)
        set_setting(db, KEY_AUTH_NEEDS_PASSWORD, "")
        return phone
    finally:
        await client.disconnect()


async def complete_user_login(
    db: Session,
    *,
    code: str = "",
    password: str = "",
) -> str:
    """Finish login with SMS/Telegram code and optional 2FA password. Returns display name."""
    if not api_credentials_configured(db):
        raise TelegramUserError("API id / API hash not configured — save them in Setup first")

    phone = get_setting(db, KEY_AUTH_PHONE, "")
    phone_hash = get_setting(db, KEY_AUTH_HASH, "")
    pending = get_setting(db, KEY_AUTH_PENDING_SESSION, "")
    if not phone or not phone_hash or not pending:
        raise TelegramUserError("No login in progress — enter your phone number first")

    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError
    from telethon.sessions import StringSession

    client = TelegramClient(
        StringSession(pending),
        get_api_id(db),
        get_api_hash(db),
    )
    await client.connect()
    try:
        needs_pw = get_setting(db, KEY_AUTH_NEEDS_PASSWORD, "") == "1"
        if needs_pw or password:
            if not password.strip():
                raise TelegramUserError("Two-factor password is required")
            await client.sign_in(password=password.strip())
        else:
            code = (code or "").strip()
            if not code:
                raise TelegramUserError("Login code is required")
            try:
                await client.sign_in(phone, code, phone_code_hash=phone_hash)
            except SessionPasswordNeededError:
                # Keep pending session; ask for 2FA on next submit
                set_setting(db, KEY_AUTH_PENDING_SESSION, client.session.save())
                set_setting(db, KEY_AUTH_NEEDS_PASSWORD, "1")
                raise TelegramUserError("2FA_REQUIRED")

        if not await client.is_user_authorized():
            raise TelegramUserError("Login failed — try again from the phone step")

        me = await client.get_me()
        display = (me.first_name or me.username or str(me.id)).strip()
        set_setting(db, KEY_USER_SESSION, client.session.save())
        set_setting(db, KEY_USER_DISPLAY, display)
        _clear_auth_pending(db)
        return display
    finally:
        await client.disconnect()


async def _load_staged_messages(client, bot_peer, message_ids: list[int]):
    """Resolve Bot API message ids in the user↔bot dialog for forwarding."""
    msgs = await client.get_messages(bot_peer, ids=list(message_ids))
    if not isinstance(msgs, list):
        msgs = [msgs]
    found = [m for m in msgs if m is not None]
    if len(found) == len(message_ids):
        # Preserve request order
        by_id = {m.id: m for m in found}
        return [by_id[i] for i in message_ids]

    # Race / sync: take newest incoming messages from the bot chat
    recent = await client.get_messages(bot_peer, limit=max(len(message_ids) + 5, 10))
    incoming = [m for m in recent if m is not None and not getattr(m, "out", False)]
    incoming = list(reversed(incoming[: len(message_ids)]))
    if len(incoming) < len(message_ids):
        raise TelegramUserError(
            "Could not find the staged bot DM in your account. "
            "Use the same Telegram account for Setup preview and user login, then retry."
        )
    return incoming


async def publish_post_as_user(
    channel_chat_id: str,
    caption: str | None,
    media: list["MediaItem"],
    **kwargs,
) -> None:
    """Bot sends to preview DM (same as preview, no prefix), user forwards to channel.

    Staging DM is deleted only after the channel forward succeeds.
    """
    from app.settings_store import get_preview_chat_id
    from app.telegram_client import delete_messages, send_post
    from app.telegram_updates import fetch_bot_username

    db: Session | None = kwargs.get("db")
    session_str = get_user_session(db)
    if not api_credentials_configured(db) or not session_str:
        raise TelegramUserError(
            "User Telegram session not configured. Open Setup, save API id/hash, "
            "and log in with your phone."
        )

    staging = get_preview_chat_id(db).strip()
    if not staging:
        raise TelegramUserError(
            "Preview chat is not set — open Setup and save your preview DM first"
        )
    dest = (channel_chat_id or "").strip()
    if not dest:
        raise TelegramUserError("Channel chat id is empty")

    for m in media:
        if not Path(m.path).is_file():
            raise TelegramUserError(f"Missing media file: {m.path}")

    message_ids = await send_post(staging, caption, media)
    if not message_ids:
        raise TelegramUserError("Bot did not return message ids for the staging DM")

    from telethon import TelegramClient
    from telethon.sessions import StringSession

    bot_username = ""
    if db is not None:
        try:
            bot_username = await fetch_bot_username(db)
        except Exception:
            bot_username = ""
    if not bot_username:
        raise TelegramUserError(
            "Could not resolve bot username — check BOT_TOKEN and try Setup again"
        )
    from_peer = f"@{bot_username}"

    client = TelegramClient(
        StringSession(session_str),
        get_api_id(db),
        get_api_hash(db),
    )
    cleanup_ids: list[int] = []
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise TelegramUserError(
                "Telegram user session is invalid or expired — log in again on Setup"
            )

        bot_entity = await client.get_entity(from_peer)
        dest_entity = await client.get_entity(_peer(dest))

        # Let the user session see the bot messages before resolving ids.
        await asyncio.sleep(1.0)
        staged = await _load_staged_messages(client, bot_entity, message_ids)
        result = await client.forward_messages(dest_entity, staged)
        if not result:
            raise TelegramUserError(
                "Forward to channel returned nothing — check you can post in the channel "
                "with this user account"
            )
        # Only clear staging after the channel received the forward.
        cleanup_ids = list(message_ids) or [
            m.id for m in staged if getattr(m, "id", None)
        ]
    finally:
        await client.disconnect()

    if cleanup_ids:
        try:
            await delete_messages(staging, cleanup_ids)
        except Exception:
            pass
