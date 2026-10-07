from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import get_settings
from app.db import get_db
from app.models import Channel
from app.services import channels as channels_svc

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _require_login(request: Request, db: Session):
    user = get_current_user(request, db)
    if user is None:
        return None
    return user


@router.get("/channels", response_class=HTMLResponse)
def channels_page(request: Request, db: Session = Depends(get_db)):
    user = _require_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "channels.html",
        {
            "request": request,
            "user": user,
            "channels": channels_svc.list_channels(db),
            "error": request.query_params.get("error"),
            "ok": request.query_params.get("ok"),
        },
    )


@router.post("/channels")
async def channels_create(
    request: Request,
    name: str = Form(...),
    chat_id: str = Form(...),
    db: Session = Depends(get_db),
):
    user = _require_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    ok, message = await channels_svc.verify_chat_id(chat_id, get_settings().bot_token)
    if not ok:
        detail = (
            f"{message}. Add the bot as channel admin, then use @username "
            "or the -100… chat id from @userinfobot / @getidsbot."
        )
        return RedirectResponse(f"/channels?error={quote(detail)}", status_code=303)
    try:
        channels_svc.create_channel(db, name, chat_id)
    except ValueError as exc:
        return RedirectResponse(f"/channels?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(f"/channels?ok={quote(message)}", status_code=303)


@router.post("/channels/{channel_id}/verify")
async def channels_verify(
    channel_id: int, request: Request, db: Session = Depends(get_db)
):
    user = _require_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    channel = db.get(Channel, channel_id)
    if channel is None:
        return RedirectResponse("/channels?error=Channel+not+found", status_code=303)
    ok, message = await channels_svc.verify_chat_id(
        channel.chat_id, get_settings().bot_token
    )
    if ok:
        normalized = channels_svc.normalize_chat_id(channel.chat_id)
        if normalized != channel.chat_id:
            channel.chat_id = normalized
            db.commit()
        return RedirectResponse(f"/channels?ok={quote(message)}", status_code=303)
    return RedirectResponse(f"/channels?error={quote(message)}", status_code=303)


@router.post("/channels/{channel_id}/delete")
def channels_delete(
    channel_id: int,
    request: Request,
    db: Session = Depends(get_db),
    cascade: str = Form(default=""),
):
    user = _require_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        channels_svc.delete_channel(db, channel_id, cascade=cascade in ("1", "true", "on"))
    except ValueError as exc:
        return RedirectResponse(
            f"/channels?error={quote(str(exc))}", status_code=303
        )
    return RedirectResponse("/channels", status_code=303)
