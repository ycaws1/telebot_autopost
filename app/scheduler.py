from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session, joinedload

from app.models import Post, PostStatus
from app.telegram_client import MediaItem, send_post as default_send

_scheduler: AsyncIOScheduler | None = None


def reset_stuck_posting(db: Session) -> int:
    rows = db.query(Post).filter(Post.status == PostStatus.POSTING).all()
    for post in rows:
        post.status = PostStatus.PENDING
    db.commit()
    return len(rows)


async def process_due_posts(
    db_factory: Callable[[], Session],
    send=default_send,
) -> int:
    """Claim and send all due pending posts. Uses the session from db_factory.

    For tests, pass `lambda: db` with a shared session.
    For production tick, pass a factory that opens a new session each call.
    """
    processed = 0
    db = db_factory()
    while True:
        now = datetime.now(timezone.utc)
        post = (
            db.query(Post)
            .options(joinedload(Post.channel), joinedload(Post.media))
            .filter(Post.status == PostStatus.PENDING, Post.scheduled_at <= now)
            .order_by(Post.scheduled_at.asc())
            .first()
        )
        if post is None:
            break

        post.status = PostStatus.POSTING
        db.commit()
        db.refresh(post)

        items = [
            MediaItem(m.media_type, Path(m.media_path))  # type: ignore[arg-type]
            for m in sorted(post.media, key=lambda m: m.sort_order)
        ]
        try:
            for item in items:
                if not item.path.is_file():
                    raise FileNotFoundError(f"Missing media file: {item.path}")
            await send(post.channel.chat_id, post.caption, items)
            post.status = PostStatus.POSTED
            post.posted_at = datetime.now(timezone.utc)
            post.error = None
        except Exception as exc:
            post.status = PostStatus.FAILED
            post.error = str(exc)
        db.commit()
        processed += 1
    return processed


async def _tick() -> None:
    from app import db as dbmod

    dbmod.engine()
    assert dbmod.SessionLocal is not None
    db = dbmod.SessionLocal()
    try:
        await process_due_posts(lambda: db)
    finally:
        db.close()


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(_tick, "interval", seconds=30, id="due_posts")
    _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
