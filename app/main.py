from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth import bootstrap_admin, get_current_user
from app.config import get_settings
from app import db as dbmod
from app.db import get_db, init_db
from app.models import Channel, Post, PostStatus
from app.routers import auth_routes, channel_routes, post_routes, setup_routes
from app.scheduler import reset_stuck_posting, start_scheduler, stop_scheduler
from app.settings_store import get_preview_chat_id
from app.telegram_updates import start_updates_poller, stop_updates_poller
from app.timeutil import format_local_display, format_local_input


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    dbmod.engine()
    assert dbmod.SessionLocal is not None
    db = dbmod.SessionLocal()
    try:
        bootstrap_admin(db)
        reset_stuck_posting(db)
    finally:
        db.close()
    start_scheduler()
    start_updates_poller()
    yield
    await stop_updates_poller()
    stop_scheduler()


app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=get_settings().secret_key)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(auth_routes.router)
app.include_router(channel_routes.router)
app.include_router(post_routes.router)
app.include_router(setup_routes.router)

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["format_local_display"] = format_local_display
templates.env.globals["format_local_input"] = format_local_input


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db=Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    pending = (
        db.query(Post)
        .filter(Post.status.in_([PostStatus.PENDING, PostStatus.POSTING]))
        .order_by(Post.scheduled_at.asc())
        .limit(50)
        .all()
    )
    recent = (
        db.query(Post)
        .filter(Post.status.in_([PostStatus.POSTED, PostStatus.FAILED, PostStatus.CANCELLED]))
        .order_by(Post.updated_at.desc())
        .limit(50)
        .all()
    )
    preview_ok = bool(get_preview_chat_id(db))
    channels_ok = db.query(Channel).count() > 0
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "pending": pending,
            "recent": recent,
            "setup_incomplete": not (preview_ok and channels_ok),
            "preview_ok": preview_ok,
            "channels_ok": channels_ok,
            "flash_ok": request.query_params.get("ok"),
        },
    )
