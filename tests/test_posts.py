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


def test_clear_history_keeps_pending(auth_client, db):
    from datetime import datetime, timezone, timedelta
    from app.models import Post, PostStatus
    from app.services.channels import create_channel
    from app.services import posts as posts_svc

    ch = create_channel(db, "C", "@c")
    pending = posts_svc.create_post(
        db,
        channel_id=ch.id,
        caption="keep-me",
        scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1),
        files=[],
    )
    done = posts_svc.create_post(
        db,
        channel_id=ch.id,
        caption="gone",
        scheduled_at=datetime.now(timezone.utc) - timedelta(hours=1),
        files=[],
    )
    done.status = PostStatus.POSTED
    db.commit()
    pending_id, done_id = pending.id, done.id

    r = auth_client.post("/posts/history/clear", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/?ok=")
    db.expire_all()
    assert db.get(Post, pending_id) is not None
    assert db.get(Post, done_id) is None


def test_requeue_posted_for_resend(db):
    from app.models import Post
    from app.timeutil import assume_utc

    ch = create_channel(db, "C", "@c")
    p = posts_svc.create_post(
        db,
        channel_id=ch.id,
        caption="hi",
        scheduled_at=datetime.now(timezone.utc) - timedelta(hours=1),
        files=[],
    )
    p.status = PostStatus.POSTED
    p.posted_at = datetime.now(timezone.utc)
    db.commit()
    old_id = p.id
    new_post = posts_svc.requeue_post(db, old_id)
    db.expire_all()
    original = db.get(Post, old_id)
    assert original is not None
    assert original.status == PostStatus.POSTED
    assert new_post.id != old_id
    assert new_post.status == PostStatus.PENDING
    assert new_post.caption == "hi"
    assert new_post.posted_at is None
    assert assume_utc(new_post.scheduled_at) <= datetime.now(timezone.utc) + timedelta(
        seconds=2
    )
