from datetime import datetime, timezone

import pytest

from app.services.channels import create_channel, delete_channel
from app.models import Post, PostStatus


def test_create_and_list(auth_client):
    r = auth_client.post("/channels", data={"name": "Main", "chat_id": "@main"})
    assert r.status_code in (200, 302, 303)
    page = auth_client.get("/channels")
    assert b"Main" in page.content
    assert b"@main" in page.content


def test_delete_blocked_when_posts_exist(db):
    ch = create_channel(db, "Main", "@main")
    db.add(
        Post(
            channel_id=ch.id,
            caption="x",
            scheduled_at=datetime.now(timezone.utc),
            status=PostStatus.PENDING,
        )
    )
    db.commit()
    with pytest.raises(ValueError, match="posts"):
        delete_channel(db, ch.id)
