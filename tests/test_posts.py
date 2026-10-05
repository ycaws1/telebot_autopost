from datetime import datetime, timezone, timedelta

import pytest

from app.services import posts as posts_svc
from app.services.channels import create_channel
from app.models import PostStatus


def test_create_text_post(db):
    ch = create_channel(db, "C", "@c")
    p = posts_svc.create_post(
        db,
        channel_id=ch.id,
        caption="hi",
        scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1),
        files=[],
    )
    assert p.status == PostStatus.PENDING
    assert p.caption == "hi"


def test_reject_empty_text_only(db):
    ch = create_channel(db, "C", "@c")
    with pytest.raises(ValueError, match="caption"):
        posts_svc.create_post(
            db,
            channel_id=ch.id,
            caption="",
            scheduled_at=datetime.now(timezone.utc),
            files=[],
        )


def test_reject_eleven_files(db):
    ch = create_channel(db, "C", "@c")
    files = [(f"{i}.jpg", b"x", "photo") for i in range(11)]
    with pytest.raises(ValueError, match="10"):
        posts_svc.create_post(
            db,
            channel_id=ch.id,
            caption="c",
            scheduled_at=datetime.now(timezone.utc),
            files=files,
        )


def test_cannot_edit_posted(db):
    ch = create_channel(db, "C", "@c")
    p = posts_svc.create_post(
        db,
        channel_id=ch.id,
        caption="hi",
        scheduled_at=datetime.now(timezone.utc),
        files=[],
    )
    p.status = PostStatus.POSTED
    db.commit()
    with pytest.raises(ValueError, match="edit"):
        posts_svc.update_post(db, p.id, caption="nope")


def test_cancel_and_retry(db):
    ch = create_channel(db, "C", "@c")
    p = posts_svc.create_post(
        db,
        channel_id=ch.id,
        caption="hi",
        scheduled_at=datetime.now(timezone.utc),
        files=[],
    )
    posts_svc.cancel_post(db, p.id)
    assert db.get(type(p), p.id).status == PostStatus.CANCELLED
    p2 = posts_svc.create_post(
        db,
        channel_id=ch.id,
        caption="hi",
        scheduled_at=datetime.now(timezone.utc),
        files=[],
    )
    p2.status = PostStatus.FAILED
    p2.error = "boom"
    db.commit()
    posts_svc.retry_post(db, p2.id)
    p2 = db.get(type(p2), p2.id)
    assert p2.status == PostStatus.PENDING
    assert p2.error is None
