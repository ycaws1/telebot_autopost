from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session, joinedload

from app.models import Post, PostStatus
from app.telegram_client import MediaItem
from app.telegram_user import publish_post_as_user as default_publish
from app.timeutil import assume_utc

_scheduler: AsyncIOScheduler | None = None


def reset_stuck_posting(db: Session) -> int:
    rows = db.query(Post).filter(Post.status == PostStatus.POSTING).all()
    for post in rows:
        post.status = PostStatus.PENDING
    db.commit()
    return len(rows)


def _is_due(post: Post, now: datetime) -> bool:
    return assume_utc(post.scheduled_at) <= now


async def process_due_posts(
    db_factory: Callable[[], Session],
    publish=default_publish,
) -> int:
    """Claim and publish all due pending posts. Uses the session from db_factory.

    Default publish path: bot sends to preview DM (no [Preview] prefix), then
    the user account forwards into the channel. For tests, pass a fake `publish`.
    """
    processed = 0
    db = db_factory()
    while True:
        now = datetime.now(timezone.utc)
        # Fetch pending oldest-first, then filter due in Python so SQLite
        # naive/aware comparison cannot treat local wall-clock as UTC.
        candidates = (
            db.query(Post)
            .options(joinedload(Post.channel), joinedload(Post.media))
            .filter(Post.status == PostStatus.PENDING)
            .order_by(Post.scheduled_at.asc())
            .all()
        )
        post = next((p for p in candidates if _is_due(p, now)), None)
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
            await publish(post.channel.chat_id, post.caption, items, db=db)
            post.status = PostStatus.POSTED
            post.posted_at = datetime.now(timezone.utc)
            post.error = None
        except Exception as exc:
            post.status = PostStatus.FAILED
            post.error = str(exc)
            post.attempt_count = int(post.attempt_count or 0) + 1
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
