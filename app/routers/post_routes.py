from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import get_settings
from app.db import get_db
from app.services import channels as channels_svc
from app.services import posts as posts_svc
from app.telegram_client import MediaItem, send_post

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _user_or_login(request: Request, db: Session):
    user = get_current_user(request, db)
    if user is None:
        return None
    return user


def _parse_scheduled_at(value: str) -> datetime:
    tz = ZoneInfo(get_settings().timezone)
    # datetime-local: YYYY-MM-DDTHH:MM
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt


async def _read_uploads(uploads: list[UploadFile]) -> list[tuple[str, bytes, str]]:
    files = []
    for upload in uploads or []:
        if not upload.filename:
            continue
        content = await upload.read()
        hinted = posts_svc.detect_media_type(upload.filename)
        files.append((upload.filename, content, hinted))
    return files


@router.get("/posts/new", response_class=HTMLResponse)
def new_post_page(request: Request, db: Session = Depends(get_db)):
    user = _user_or_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "post_form.html",
        {
            "request": request,
            "user": user,
            "channels": channels_svc.list_channels(db),
            "post": None,
            "error": None,
        },
    )


@router.post("/posts")
async def create_post_route(
    request: Request,
    channel_id: int = Form(...),
    caption: str = Form(""),
    scheduled_at: str = Form(...),
    media: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    user = _user_or_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        files = await _read_uploads(media)
        post = posts_svc.create_post(
            db,
            channel_id=channel_id,
            caption=caption,
            scheduled_at=_parse_scheduled_at(scheduled_at),
            files=files,
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "post_form.html",
            {
                "request": request,
                "user": user,
                "channels": channels_svc.list_channels(db),
                "post": None,
                "error": str(exc),
            },
            status_code=400,
        )
    return RedirectResponse(f"/posts/{post.id}", status_code=303)


@router.post("/posts/preview")
async def preview_post(
    request: Request,
    caption: str = Form(""),
    media: list[UploadFile] | None = File(None),
    db: Session = Depends(get_db),
):
    user = _user_or_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    settings = get_settings()
    if not settings.preview_chat_id:
        return RedirectResponse("/posts/new?error=Set+PREVIEW_CHAT_ID", status_code=303)
    files = await _read_uploads(media or [])
    tmp_dir = settings.media_dir / "_preview"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    items: list[MediaItem] = []
    paths = []
    try:
        for idx, (filename, content, media_type) in enumerate(files):
            path = tmp_dir / f"{idx}_{Path(filename).name}"
            path.write_bytes(content)
            paths.append(path)
            items.append(MediaItem(media_type, path))  # type: ignore[arg-type]
        await send_post(settings.preview_chat_id, caption, items)
    finally:
        for path in paths:
            path.unlink(missing_ok=True)
    return RedirectResponse("/posts/new?preview=1", status_code=303)


@router.get("/posts/{post_id}", response_class=HTMLResponse)
def post_detail(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = _user_or_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    post = posts_svc.get_post(db, post_id)
    return templates.TemplateResponse(
        request,
        "post_detail.html",
        {"request": request, "user": user, "post": post},
    )


@router.get("/posts/{post_id}/edit", response_class=HTMLResponse)
def edit_post_page(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = _user_or_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    post = posts_svc.get_post(db, post_id)
    return templates.TemplateResponse(
        request,
        "post_form.html",
        {
            "request": request,
            "user": user,
            "channels": channels_svc.list_channels(db),
            "post": post,
            "error": None,
        },
    )


@router.post("/posts/{post_id}")
async def update_post_route(
    post_id: int,
    request: Request,
    channel_id: int = Form(...),
    caption: str = Form(""),
    scheduled_at: str = Form(...),
    keep_media: list[int] = Form(default=[]),
    media: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    user = _user_or_login(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        files = await _read_uploads(media)
        posts_svc.update_post(
            db,
            post_id,
            channel_id=channel_id,
            caption=caption,
            scheduled_at=_parse_scheduled_at(scheduled_at),
            keep_media_ids=keep_media,
            new_files=files,
        )
    except ValueError as exc:
        post = posts_svc.get_post(db, post_id)
        return templates.TemplateResponse(
            request,
            "post_form.html",
            {
                "request": request,
                "user": user,
                "channels": channels_svc.list_channels(db),
                "post": post,
                "error": str(exc),
            },
            status_code=400,
        )
    return RedirectResponse(f"/posts/{post_id}", status_code=303)


@router.post("/posts/{post_id}/cancel")
def cancel_post_route(post_id: int, request: Request, db: Session = Depends(get_db)):
    if _user_or_login(request, db) is None:
        return RedirectResponse("/login", status_code=303)
    posts_svc.cancel_post(db, post_id)
    return RedirectResponse(f"/posts/{post_id}", status_code=303)


@router.post("/posts/{post_id}/retry")
def retry_post_route(post_id: int, request: Request, db: Session = Depends(get_db)):
    if _user_or_login(request, db) is None:
        return RedirectResponse("/login", status_code=303)
    posts_svc.retry_post(db, post_id)
    return RedirectResponse(f"/posts/{post_id}", status_code=303)
