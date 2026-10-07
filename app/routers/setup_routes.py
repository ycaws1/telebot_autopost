from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import get_settings
from app.db import get_db
from app.models import Channel, SetupCandidate
from app.services import channels as channels_svc
from app.services import setup as setup_svc
from app.settings_store import (
    clear_preview_chat_id,
    get_preview_chat_id,
    set_preview_chat_id,
)
from app.telegram_client import TelegramError, send_post
from app.telegram_updates import fetch_bot_username
from app.telegram_user import (
    TelegramUserError,
    clear_api_credentials,
    clear_user_session,
    complete_user_login,
    get_api_hash,
    set_api_credentials,
    start_user_login,
    user_auth_status,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _require_login(request: Request, db: Session):
    return get_current_user(request, db)


def _session_payload(db: Session, user_id: int) -> dict:
    session = setup_svc.get_active_session_for_user(db, user_id)
    existing_channels = [
        {"id": ch.id, "name": ch.name, "chat_id": ch.chat_id}
        for ch in channels_svc.list_channels(db)
    ]
    candidates = []
    if session:
        for c in (
            db.query(SetupCandidate)
            .filter(SetupCandidate.session_id == session.id)
            .order_by(SetupCandidate.id.desc())
            .all()
        ):
            create_id = f"@{c.username}" if c.username else c.chat_id
            already = (
                c.kind == "channel"
                and channels_svc.find_channel_by_chat_id(db, create_id, c.chat_id)
                is not None
            )
            candidates.append(
                {
                    "id": c.id,
                    "kind": c.kind,
                    "chat_id": c.chat_id,
                    "title": c.title,
                    "username": c.username,
                    "selected": bool(c.selected),
                    "already_added": already,
                }
            )
    return {
        "session": None
        if session is None
        else {
            "code": session.code,
            "status": session.status,
            "telegram_user_id": session.telegram_user_id,
            "expires_at": session.expires_at.isoformat() if session.expires_at else None,
        },
        "candidates": candidates,
        "existing_channels": existing_channels,
        "preview_chat_id": get_preview_chat_id(db),
        "channels_count": len(existing_channels),
        "user_auth": user_auth_status(db),
    }


@router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request, db: Session = Depends(get_db)):
    user = _require_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    session = setup_svc.get_active_session_for_user(db, user.id)
    if session is None:
        session = setup_svc.mint_setup_code(db, user.id)
    bot_username = ""
    try:
        bot_username = await fetch_bot_username(db)
    except Exception:
        bot_username = ""
    payload = _session_payload(db, user.id)
    return templates.TemplateResponse(
        request,
        "setup.html",
        {
            "request": request,
            "user": user,
            "bot_username": bot_username,
            "deep_link": (
                f"https://t.me/{bot_username}?start={session.code}" if bot_username else ""
            ),
            "flash_ok": request.query_params.get("ok"),
            "flash_error": request.query_params.get("error"),
            **payload,
        },
    )


@router.post("/setup/code")
async def setup_mint_code(request: Request, db: Session = Depends(get_db)):
    user = _require_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    setup_svc.mint_setup_code(db, user.id)
    return RedirectResponse("/setup", status_code=303)


@router.get("/setup/status")
async def setup_status(request: Request, db: Session = Depends(get_db)):
    user = _require_login(request, db)
    if user is None:
        return JSONResponse({"ok": False, "error": "login required"}, status_code=401)
    bot_username = ""
    try:
        bot_username = await fetch_bot_username(db)
    except Exception:
        bot_username = ""
    payload = _session_payload(db, user.id)
    code = (payload["session"] or {}).get("code")
    payload["ok"] = True
    payload["bot_username"] = bot_username
    payload["deep_link"] = (
        f"https://t.me/{bot_username}?start={code}" if bot_username and code else ""
    )
    return JSONResponse(payload)


@router.post("/setup/preview/save")
async def setup_save_preview(
    request: Request,
    candidate_id: int = Form(...),
    db: Session = Depends(get_db),
):
    user = _require_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    cand = db.get(SetupCandidate, candidate_id)
    if cand is None or cand.kind != "preview":
        return RedirectResponse("/setup?error=Preview+candidate+not+found", status_code=303)
    session = cand.session
    if session is None or session.user_id != user.id:
        return RedirectResponse("/setup?error=Not+your+setup+session", status_code=303)
    setup_svc.select_candidate(db, cand.id)
    set_preview_chat_id(db, cand.chat_id)
    return RedirectResponse(
        f"/setup?ok={quote('Preview chat saved: ' + cand.chat_id)}",
        status_code=303,
    )


@router.post("/setup/channels/add")
async def setup_add_channel(
    request: Request,
    candidate_id: int = Form(...),
    name: str = Form(""),
    db: Session = Depends(get_db),
):
    user = _require_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    cand = db.get(SetupCandidate, candidate_id)
    if cand is None or cand.kind != "channel":
        return RedirectResponse("/setup?error=Channel+candidate+not+found", status_code=303)
    session = cand.session
    if session is None or session.user_id != user.id:
        return RedirectResponse("/setup?error=Not+your+setup+session", status_code=303)
    setup_svc.select_candidate(db, cand.id)
    chat_ref = f"@{cand.username}" if cand.username else cand.chat_id
    ok, message = await channels_svc.verify_chat_id(chat_ref, get_settings().bot_token)
    if not ok:
        return RedirectResponse(f"/setup?error={quote(message)}", status_code=303)
    display = (name or cand.title or cand.username or cand.chat_id).strip()
    # Prefer username when available; otherwise normalized numeric id
    create_id = f"@{cand.username}" if cand.username else cand.chat_id
    existing = channels_svc.find_channel_by_chat_id(db, create_id, cand.chat_id)
    if existing is not None:
        return RedirectResponse(
            f"/setup?ok={quote('Using existing channel: ' + existing.name + ' (' + existing.chat_id + ')')}",
            status_code=303,
        )
    try:
        channels_svc.create_channel(db, display, create_id)
    except ValueError as exc:
        return RedirectResponse(f"/setup?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(f"/setup?ok={quote(message)}", status_code=303)


@router.post("/setup/channels/lookup")
async def setup_lookup_channel(
    request: Request,
    query: str = Form(...),
    name: str = Form(""),
    db: Session = Depends(get_db),
):
    """Resolve public @username or numeric id via getChat and add the channel."""
    user = _require_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    ok, message, info = await channels_svc.lookup_chat(
        query, get_settings().bot_token
    )
    if not ok or info is None:
        hint = (
            f"{message}. Use a public @username or -100… id "
            "(Telegram cannot search by display title alone). "
            "The bot must already be able to see the chat (usually as admin)."
        )
        return RedirectResponse(f"/setup?error={quote(hint)}", status_code=303)
    display = (name or info.get("title") or info["chat_id"]).strip()
    existing = channels_svc.find_channel_by_chat_id(
        db, info["chat_id"], info.get("numeric_id") or ""
    )
    session = setup_svc.get_active_session_for_user(db, user.id)
    if existing is not None:
        if session is not None:
            setup_svc.upsert_candidate(
                db,
                session=session,
                kind="channel",
                chat_id=info.get("numeric_id") or info["chat_id"],
                title=info.get("title") or existing.name,
                username=info.get("username"),
                selected=True,
            )
        return RedirectResponse(
            f"/setup?ok={quote('Using existing channel: ' + existing.name + ' (' + existing.chat_id + ')')}",
            status_code=303,
        )
    try:
        channels_svc.create_channel(db, display, info["chat_id"])
    except ValueError as exc:
        return RedirectResponse(f"/setup?error={quote(str(exc))}", status_code=303)
    # Also stash as candidate when a setup session is active (keeps wizard list in sync)
    if session is not None:
        setup_svc.upsert_candidate(
            db,
            session=session,
            kind="channel",
            chat_id=info.get("numeric_id") or info["chat_id"],
            title=info.get("title"),
            username=info.get("username"),
            selected=True,
        )
    return RedirectResponse(f"/setup?ok={quote(message)}", status_code=303)


@router.post("/setup/test-preview")
async def setup_test_preview(request: Request, db: Session = Depends(get_db)):
    user = _require_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    chat_id = get_preview_chat_id(db)
    if not chat_id:
        return RedirectResponse(
            "/setup?error=Save+a+preview+chat+first",
            status_code=303,
        )
    try:
        await send_post(chat_id, "Setup OK — Telebot can DM you.", [])
    except TelegramError as exc:
        return RedirectResponse(f"/setup?error={quote(str(exc))}", status_code=303)
    except Exception as exc:
        return RedirectResponse(f"/setup?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(
        f"/setup?ok={quote('Test DM sent to ' + chat_id)}",
        status_code=303,
    )


@router.post("/setup/reset")
def setup_reset(request: Request, db: Session = Depends(get_db)):
    user = _require_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    clear_preview_chat_id(db)
    clear_user_session(db)
    clear_api_credentials(db)
    setup_svc.reset_setup(db, user.id)
    return RedirectResponse(
        f"/setup?ok={quote('Setup reset. Enter API credentials, log in, and pair again. Channels were kept.')}",
        status_code=303,
    )


@router.post("/setup/user/api")
def setup_user_api(
    request: Request,
    api_id: str = Form(...),
    api_hash: str = Form(""),
    db: Session = Depends(get_db),
):
    user = _require_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    hash_value = (api_hash or "").strip() or get_api_hash(db)
    try:
        set_api_credentials(db, api_id, hash_value)
    except TelegramUserError as exc:
        return RedirectResponse(f"/setup?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(
        f"/setup?ok={quote('API credentials saved. You can log in with your phone.')}",
        status_code=303,
    )


@router.post("/setup/user/phone")
async def setup_user_phone(
    request: Request,
    phone: str = Form(...),
    db: Session = Depends(get_db),
):
    user = _require_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        await start_user_login(db, phone)
    except TelegramUserError as exc:
        return RedirectResponse(f"/setup?error={quote(str(exc))}", status_code=303)
    except Exception as exc:
        return RedirectResponse(f"/setup?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(
        f"/setup?ok={quote('Code sent. Enter it below.')}",
        status_code=303,
    )


@router.post("/setup/user/code")
async def setup_user_code(
    request: Request,
    code: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    user = _require_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        display = await complete_user_login(db, code=code, password=password)
    except TelegramUserError as exc:
        if str(exc) == "2FA_REQUIRED":
            return RedirectResponse(
                f"/setup?ok={quote('Enter your Telegram 2FA password.')}",
                status_code=303,
            )
        return RedirectResponse(f"/setup?error={quote(str(exc))}", status_code=303)
    except Exception as exc:
        return RedirectResponse(f"/setup?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(
        f"/setup?ok={quote('User account linked: ' + display)}",
        status_code=303,
    )


@router.post("/setup/user/logout")
def setup_user_logout(request: Request, db: Session = Depends(get_db)):
    user = _require_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    clear_user_session(db)
    return RedirectResponse(
        f"/setup?ok={quote('User session cleared. Log in again to publish.')}",
        status_code=303,
    )
