from datetime import datetime, timezone, timedelta

import pytest

from app.services.channels import create_channel
from app.services import posts as posts_svc
from app.models import PostStatus
from app.scheduler import process_due_posts, reset_stuck_posting


@pytest.mark.asyncio
async def test_due_post_becomes_posted(db):
    ch = create_channel(db, "C", "@c")
    p = posts_svc.create_post(
        db,
        channel_id=ch.id,
        caption="hi",
        scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        files=[],
    )
    sent = []

    async def fake_publish(chat_id, caption, media, **kwargs):
        sent.append((chat_id, caption))

    n = await process_due_posts(lambda: db, publish=fake_publish)
    assert n == 1
    db.refresh(p)
    assert p.status == PostStatus.POSTED
    assert p.posted_at is not None
    assert sent == [("@c", "hi")]


@pytest.mark.asyncio
async def test_send_failure_marks_failed(db):
    ch = create_channel(db, "C", "@c")
    p = posts_svc.create_post(
        db,
        channel_id=ch.id,
        caption="hi",
        scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        files=[],
    )

    async def boom(*a, **k):
        raise Exception("bot not admin")

    await process_due_posts(lambda: db, publish=boom)
    db.refresh(p)
    assert p.status == PostStatus.FAILED
    assert "bot not admin" in p.error
    assert p.attempt_count == 1


def test_reset_stuck_posting(db):
    ch = create_channel(db, "C", "@c")
    p = posts_svc.create_post(
        db,
        channel_id=ch.id,
        caption="hi",
        scheduled_at=datetime.now(timezone.utc),
        files=[],
    )
    p.status = PostStatus.POSTING
    db.commit()
    assert reset_stuck_posting(db) == 1
    db.refresh(p)
    assert p.status == PostStatus.PENDING


@pytest.mark.asyncio
async def test_future_post_not_sent(db):
    ch = create_channel(db, "C", "@c")
    posts_svc.create_post(
        db,
        channel_id=ch.id,
        caption="hi",
        scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
        files=[],
    )

    async def fake_publish(*a, **k):
        raise AssertionError("should not publish")

    n = await process_due_posts(lambda: db, publish=fake_publish)
    assert n == 0
