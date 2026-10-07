from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from urllib.parse import quote

from app.auth import get_current_user
from app.config import get_settings
from app.db import get_db
from app.models import PostMedia
from app.services import channels as channels_svc
from app.services import posts as posts_svc
from app.settings_store import get_preview_chat_id
from app.telegram_client import MediaItem, TelegramError, send_post
from app.timeutil import format_local_display, format_local_input, parse_local_datetime

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["format_local_display"] = format_local_display
templates.env.globals["format_local_input"] = format_local_input


def _user_or_login(request: Request, db: Session):
    user = get_current_user(request, db)
    if user is None:
        return None
    return user


def _parse_scheduled_at(value: str) -> datetime:
    return parse_local_datetime(value)


async def _read_uploads(uploads: list[UploadFile]) -> list[tuple[str, bytes, str]]:
    files = []
    for upload in uploads or []:
        if not upload.filename:
            continue
        content = await upload.read()
        hinted = posts_svc.detect_media_type(upload.filename)
        files.append((upload.filename, content, hinted))
    return files


@router.get("/media/{media_id}")
def serve_media(media_id: int, request: Request, db: Session = Depends(get_db)):
    if _user_or_login(request, db) is None:
        return RedirectResponse("/login", status_code=303)
    row = db.get(PostMedia, media_id)
    if row is None or not Path(row.media_path).is_file():
        return HTMLResponse("Not found", status_code=404)
    return FileResponse(row.media_path)


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
    keep_media: list[int] = Form(default=[]),
    db: Session = Depends(get_db),
):
    wants_json = "application/json" in (request.headers.get("accept") or "")
    user = _user_or_login(request, db)
    if user is None:
        if wants_json:
            return JSONResponse({"ok": False, "error": "Not authenticated"}, status_code=401)
        return RedirectResponse("/login", status_code=303)
    settings = get_settings()
    preview_chat_id = get_preview_chat_id(db)
    if not preview_chat_id:
        msg = "Set preview chat via Setup wizard (or PREVIEW_CHAT_ID in .env)"
        if wants_json:
            return JSONResponse({"ok": False, "error": msg}, status_code=400)
        return RedirectResponse(f"/posts/new?error={quote(msg)}", status_code=303)

    files = await _read_uploads(media or [])
    tmp_dir = settings.media_dir / "_preview"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    items: list[MediaItem] = []
    paths: list[Path] = []
    try:
        # Existing kept media first (same order as edit form)
        for media_id in keep_media or []:
            row = db.get(PostMedia, media_id)
            if row is None or not Path(row.media_path).is_file():
                continue
            items.append(MediaItem(row.media_type, Path(row.media_path)))  # type: ignore[arg-type]

        for idx, (filename, content, media_type) in enumerate(files):
            path = tmp_dir / f"{idx}_{Path(filename).name}"
            path.write_bytes(content)
            paths.append(path)
            items.append(MediaItem(media_type, path))  # type: ignore[arg-type]

        if len(items) > 10:
            raise TelegramError("Maximum 10 media files per post")
        if not items and not (caption or "").strip():
            raise TelegramError("caption is required for text-only posts")

        await send_post(preview_chat_id, caption, items)
    except TelegramError as exc:
        if wants_json:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        return RedirectResponse(
            f"/posts/new?error={quote(str(exc))}", status_code=303
        )
    finally:
        for path in paths:
            path.unlink(missing_ok=True)

    if wants_json:
        return JSONResponse({"ok": True})
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


@router.post("/posts/history/clear")
def clear_history_route(request: Request, db: Session = Depends(get_db)):
    if _user_or_login(request, db) is None:
        return RedirectResponse("/login", status_code=303)
    n = posts_svc.clear_history(db)
    return RedirectResponse(f"/?ok={quote(f'Cleared {n} history post(s).')}", status_code=303)


@router.post("/posts/{post_id}/cancel")
def cancel_post_route(post_id: int, request: Request, db: Session = Depends(get_db)):
    if _user_or_login(request, db) is None:
        return RedirectResponse("/login", status_code=303)
    posts_svc.cancel_post(db, post_id)
    return RedirectResponse(f"/posts/{post_id}", status_code=303)


def _safe_next(next_url: str | None, fallback: str) -> str:
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return fallback


@router.post("/posts/{post_id}/retry")
async def retry_post_route(
    post_id: int,
    request: Request,
    db: Session = Depends(get_db),
    next: str = Form(default=""),
):
    if _user_or_login(request, db) is None:
        return RedirectResponse("/login", status_code=303)
    posts_svc.retry_post(db, post_id)
    return RedirectResponse(_safe_next(next, f"/posts/{post_id}"), status_code=303)


@router.post("/posts/{post_id}/requeue")
async def requeue_post_route(
    post_id: int,
    request: Request,
    db: Session = Depends(get_db),
    next: str = Form(default=""),
):
    if _user_or_login(request, db) is None:
        return RedirectResponse("/login", status_code=303)
    new_post = posts_svc.requeue_post(db, post_id)
    return RedirectResponse(_safe_next(next, f"/posts/{new_post.id}"), status_code=303)
