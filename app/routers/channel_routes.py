from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
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
        },
    )


@router.post("/channels")
def channels_create(
    request: Request,
    name: str = Form(...),
    chat_id: str = Form(...),
    db: Session = Depends(get_db),
):
    user = _require_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    channels_svc.create_channel(db, name, chat_id)
    return RedirectResponse("/channels", status_code=303)


@router.post("/channels/{channel_id}/delete")
def channels_delete(
    channel_id: int, request: Request, db: Session = Depends(get_db)
):
    user = _require_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        channels_svc.delete_channel(db, channel_id)
    except ValueError as exc:
        return RedirectResponse(
            f"/channels?error={str(exc)}", status_code=303
        )
    return RedirectResponse("/channels", status_code=303)
