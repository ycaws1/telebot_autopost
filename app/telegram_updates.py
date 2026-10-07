from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config import get_settings
from app import db as dbmod
from app.models import SetupCandidate
from app.services import setup as setup_svc
from app.settings_store import (
    KEY_BOT_USERNAME,
    KEY_UPDATES_OFFSET,
    get_setting,
    set_setting,
)

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None
_stop = asyncio.Event()


def _api_base() -> str:
    return f"https://api.telegram.org/bot{get_settings().bot_token}"


async def telegram_api(method: str, **params: Any) -> dict:
    async with httpx.AsyncClient(timeout=60.0) as client:
        if params:
            resp = await client.post(f"{_api_base()}/{method}", json=params)
        else:
            resp = await client.get(f"{_api_base()}/{method}")
        return resp.json()


async def fetch_bot_username(db) -> str:
    cached = get_setting(db, KEY_BOT_USERNAME, "")
    if cached:
        return cached
    body = await telegram_api("getMe")
    if not body.get("ok"):
        return ""
    username = (body.get("result") or {}).get("username") or ""
    if username:
        set_setting(db, KEY_BOT_USERNAME, username)
    return username


async def _send_message(chat_id: str | int, text: str, reply_markup: dict | None = None) -> None:
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    await telegram_api("sendMessage", **payload)


async def _answer_callback(callback_id: str, text: str) -> None:
    await telegram_api(
        "answerCallbackQuery",
        callback_query_id=callback_id,
        text=text,
        show_alert=False,
    )


async def _edit_message(chat_id: str | int, message_id: int, text: str) -> None:
    await telegram_api(
        "editMessageText",
        chat_id=chat_id,
        message_id=message_id,
        text=text,
    )


def _preview_keyboard(candidate_id: int) -> dict:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "Use as my preview DM",
                    "callback_data": f"sel:preview:{candidate_id}",
                }
            ]
        ]
    }


def _channel_keyboard(candidate_id: int) -> dict:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "Add as posting channel",
                    "callback_data": f"sel:channel:{candidate_id}",
                },
                {
                    "text": "Ignore",
                    "callback_data": f"ign:channel:{candidate_id}",
                },
            ]
        ]
    }


async def handle_message(db, message: dict) -> None:
    chat = message.get("chat") or {}
    if chat.get("type") != "private":
        return
    text = (message.get("text") or "").strip()
    from_user = message.get("from") or {}
    tg_uid = str(from_user.get("id") or "")
    if not tg_uid:
        return

    code = ""
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        code = parts[1].strip() if len(parts) > 1 else ""
    elif text.isdigit() and len(text) == 6:
        code = text

    if not code:
        # If already paired elsewhere, ignore politely
        await _send_message(
            tg_uid,
            "Open Setup in Telebot, generate a code, then send /start CODE here.",
        )
        return

    session = setup_svc.find_session_by_code(db, code)
    if session is None:
        await _send_message(tg_uid, "That setup code is invalid or expired. Generate a new one in Setup.")
        return

    setup_svc.pair_session(db, session, tg_uid)
    name = from_user.get("first_name") or from_user.get("username") or tg_uid
    cand = setup_svc.upsert_candidate(
        db,
        session=session,
        kind="preview",
        chat_id=tg_uid,
        title=name,
        username=from_user.get("username"),
        raw_update_id=message.get("message_id"),
    )
    await _send_message(
        tg_uid,
        f"Linked to Telebot setup.\nYour chat id: {tg_uid}\n\n"
        "Tap below to set this as your preview DM (no need to confirm on the web).",
        reply_markup=_preview_keyboard(cand.id),
    )


async def handle_callback(db, callback: dict) -> None:
    data = callback.get("data") or ""
    cb_id = callback.get("id")
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    message_id = message.get("message_id")
    from_user = callback.get("from") or {}
    tg_uid = str(from_user.get("id") or "")

    parts = data.split(":")
    if len(parts) != 3:
        if cb_id:
            await _answer_callback(cb_id, "Unknown action")
        return
    action, kind, cid_s = parts
    try:
        candidate_id = int(cid_s)
    except ValueError:
        if cb_id:
            await _answer_callback(cb_id, "Invalid")
        return

    cand = db.get(SetupCandidate, candidate_id)
    if cand is None:
        if cb_id:
            await _answer_callback(cb_id, "Expired candidate")
        return

    if action == "ign":
        if cb_id:
            await _answer_callback(cb_id, "Ignored")
        if chat_id and message_id:
            await _edit_message(chat_id, message_id, "Ignored. You can discover another channel by posting again.")
        return

    if action == "sel":
        setup_svc.select_candidate(db, candidate_id)
        if kind == "preview":
            from app.settings_store import set_preview_chat_id

            set_preview_chat_id(db, cand.chat_id)
            if cb_id:
                await _answer_callback(cb_id, "Preview DM saved")
            if chat_id and message_id:
                await _edit_message(
                    chat_id,
                    message_id,
                    f"Preview DM saved ({cand.chat_id}). Setup will show it as done.",
                )
            return

        if kind == "channel":
            from app.services import channels as channels_svc

            create_id = f"@{cand.username}" if cand.username else cand.chat_id
            display = (cand.title or cand.username or cand.chat_id or create_id).strip()
            existing = channels_svc.find_channel_by_chat_id(db, create_id, cand.chat_id)
            if existing is None:
                try:
                    existing = channels_svc.create_channel(db, display, create_id)
                except ValueError as exc:
                    if cb_id:
                        await _answer_callback(cb_id, str(exc)[:180])
                    if chat_id and message_id:
                        await _edit_message(chat_id, message_id, f"Could not add channel: {exc}")
                    return
            label = f"{existing.name} ({existing.chat_id})"
            if cb_id:
                await _answer_callback(cb_id, "Channel saved")
            done_text = f"Channel saved: {label}. Setup will show it as in use."
            if chat_id and message_id:
                await _edit_message(chat_id, message_id, done_text)
            if tg_uid and str(chat_id) != tg_uid:
                await _send_message(tg_uid, done_text)
            return


async def handle_channel_post(db, channel_post: dict) -> None:
    chat = channel_post.get("chat") or {}
    if chat.get("type") not in ("channel", "supergroup"):
        return
    chat_id = str(chat.get("id") or "")
    if not chat_id:
        return
    title = chat.get("title")
    username = chat.get("username")
    sessions = setup_svc.active_paired_sessions(db)
    if not sessions:
        return
    for session in sessions:
        if not session.telegram_user_id:
            continue
        cand = setup_svc.upsert_candidate(
            db,
            session=session,
            kind="channel",
            chat_id=chat_id,
            title=title,
            username=username,
            raw_update_id=channel_post.get("message_id"),
        )
        label = title or username or chat_id
        await _send_message(
            session.telegram_user_id,
            f"Found channel: {label}\nId: {chat_id}\n\n"
            "Tap below to save it for posting (no need to confirm on the web).",
            reply_markup=_channel_keyboard(cand.id),
        )


async def process_update(db, update: dict) -> None:
    if "callback_query" in update:
        await handle_callback(db, update["callback_query"])
        return
    if "channel_post" in update:
        await handle_channel_post(db, update["channel_post"])
        return
    if "message" in update:
        await handle_message(db, update["message"])


async def poll_once(db) -> int:
    token = get_settings().bot_token
    if not token:
        return 0
    offset_s = get_setting(db, KEY_UPDATES_OFFSET, "0")
    try:
        offset = int(offset_s or "0")
    except ValueError:
        offset = 0
    # Long-poll up to 25s; httpx read timeout must be higher or empty waits look like errors.
    timeout = httpx.Timeout(connect=10.0, read=40.0, write=10.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.get(
                f"{_api_base()}/getUpdates",
                params={"offset": offset, "timeout": 25},
            )
        except httpx.ReadTimeout:
            # No updates within the long-poll window; normal, retry next loop.
            return 0
        body = resp.json()
    if not body.get("ok"):
        logger.warning("getUpdates failed: %s", body.get("description"))
        return 0
    updates = body.get("result") or []
    for update in updates:
        try:
            await process_update(db, update)
        except Exception:
            logger.exception("Failed processing update %s", update.get("update_id"))
        uid = update.get("update_id")
        if isinstance(uid, int):
            offset = uid + 1
    if updates:
        set_setting(db, KEY_UPDATES_OFFSET, str(offset))
    return len(updates)


async def _poll_loop() -> None:
    _stop.clear()
    while not _stop.is_set():
        dbmod.engine()
        assert dbmod.SessionLocal is not None
        db = dbmod.SessionLocal()
        try:
            await poll_once(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("telegram poll error")
            await asyncio.sleep(3)
        finally:
            db.close()
        try:
            await asyncio.wait_for(_stop.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass


def start_updates_poller() -> None:
    global _task
    if _task is not None and not _task.done():
        return
    settings = get_settings()
    if not settings.telegram_updates_enabled:
        logger.info("Telegram updates poller disabled")
        return
    if not settings.bot_token:
        logger.warning("BOT_TOKEN missing; setup poller not started")
        return
    _task = asyncio.create_task(_poll_loop(), name="telegram-updates")


async def stop_updates_poller() -> None:
    global _task
    _stop.set()
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
