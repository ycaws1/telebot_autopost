from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Channel, Post, PostMedia, PostStatus

PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXT = {".mp4", ".mov", ".m4v"}


def detect_media_type(filename: str, hinted: str | None = None) -> str:
    if hinted in ("photo", "video"):
        return hinted
    ext = Path(filename).suffix.lower()
    if ext in PHOTO_EXT:
        return "photo"
    if ext in VIDEO_EXT:
        return "video"
    raise ValueError(f"Unsupported media type for {filename}")


def get_post(db: Session, post_id: int) -> Post:
    post = db.get(Post, post_id)
    if post is None:
        raise ValueError("Post not found")
    return post


def create_post(
    db: Session,
    *,
    channel_id: int,
    caption: str | None,
    scheduled_at: datetime,
    files: list[tuple[str, bytes, str]],
) -> Post:
    if db.get(Channel, channel_id) is None:
        raise ValueError("Channel not found")
    if len(files) > 10:
        raise ValueError("Maximum 10 media files per post")
    caption_clean = (caption or "").strip()
    if not files and not caption_clean:
        raise ValueError("caption is required for text-only posts")

    post = Post(
        channel_id=channel_id,
        caption=caption_clean or None,
        scheduled_at=scheduled_at,
        status=PostStatus.PENDING,
    )
    db.add(post)
    db.flush()

    media_root = get_settings().media_dir / str(post.id)
    media_root.mkdir(parents=True, exist_ok=True)
    for idx, (filename, content, hinted) in enumerate(files):
        media_type = detect_media_type(filename, hinted)
        dest = media_root / f"{idx:02d}_{Path(filename).name}"
        dest.write_bytes(content)
        db.add(
            PostMedia(
                post_id=post.id,
                media_type=media_type,
                media_path=str(dest),
                sort_order=idx,
            )
        )
    db.commit()
    db.refresh(post)
    return post


def update_post(
    db: Session,
    post_id: int,
    *,
    channel_id: int | None = None,
    caption: str | None = None,
    scheduled_at: datetime | None = None,
    keep_media_ids: list[int] | None = None,
    new_files: list[tuple[str, bytes, str]] | None = None,
) -> Post:
    post = get_post(db, post_id)
    if post.status not in (PostStatus.PENDING, PostStatus.FAILED):
        raise ValueError("Cannot edit this post")

    if channel_id is not None:
        if db.get(Channel, channel_id) is None:
            raise ValueError("Channel not found")
        post.channel_id = channel_id
    if caption is not None:
        post.caption = caption.strip() or None
    if scheduled_at is not None:
        post.scheduled_at = scheduled_at

    existing = list(post.media)
    if keep_media_ids is not None:
        keep = set(keep_media_ids)
        for m in existing:
            if m.id not in keep:
                path = Path(m.media_path)
                if path.is_file():
                    path.unlink(missing_ok=True)
                db.delete(m)
        db.flush()
        existing = [m for m in post.media if m.id in keep]

    new_files = new_files or []
    total = len(existing) + len(new_files)
    if total > 10:
        raise ValueError("Maximum 10 media files per post")

    caption_val = post.caption or ""
    if total == 0 and not caption_val.strip():
        raise ValueError("caption is required for text-only posts")

    media_root = get_settings().media_dir / str(post.id)
    media_root.mkdir(parents=True, exist_ok=True)
    start = max((m.sort_order for m in existing), default=-1) + 1
    for offset, (filename, content, hinted) in enumerate(new_files):
        media_type = detect_media_type(filename, hinted)
        dest = media_root / f"{start + offset:02d}_{Path(filename).name}"
        dest.write_bytes(content)
        db.add(
            PostMedia(
                post_id=post.id,
                media_type=media_type,
                media_path=str(dest),
                sort_order=start + offset,
            )
        )

    if post.status == PostStatus.FAILED:
        post.error = None
        post.status = PostStatus.PENDING

    db.commit()
    db.refresh(post)
    return post


def cancel_post(db: Session, post_id: int) -> Post:
    post = get_post(db, post_id)
    if post.status != PostStatus.PENDING:
        raise ValueError("Only pending posts can be cancelled")
    post.status = PostStatus.CANCELLED
    db.commit()
    db.refresh(post)
    return post


def retry_post(db: Session, post_id: int) -> Post:
    post = get_post(db, post_id)
    if post.status != PostStatus.FAILED:
        raise ValueError("Only failed posts can be retried")
    post.status = PostStatus.PENDING
    post.error = None
    db.commit()
    db.refresh(post)
    return post
