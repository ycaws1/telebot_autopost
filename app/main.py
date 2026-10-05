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
from app.models import Post, PostStatus
from app.routers import auth_routes, channel_routes, post_routes
from app.scheduler import reset_stuck_posting, start_scheduler, stop_scheduler


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
    yield
    stop_scheduler()


app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=get_settings().secret_key)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(auth_routes.router)
app.include_router(channel_routes.router)
app.include_router(post_routes.router)

templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db=Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    pending = (
        db.query(Post)
        .filter(Post.status == PostStatus.PENDING)
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
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"request": request, "user": user, "pending": pending, "recent": recent},
    )
