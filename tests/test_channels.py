from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.services.channels import (
    create_channel,
    delete_channel,
    lookup_chat,
    normalize_chat_id,
)
from app.models import Channel, Post, PostStatus


def test_create_and_list(auth_client):
    with patch(
        "app.routers.channel_routes.channels_svc.verify_chat_id",
        new=AsyncMock(return_value=(True, "OK — Main (@main)")),
    ):
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
    with pytest.raises(ValueError, match="post"):
        delete_channel(db, ch.id)


def test_delete_cascade_removes_posts(db):
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
    delete_channel(db, ch.id, cascade=True)
    assert db.get(Channel, ch.id) is None
    assert db.query(Post).count() == 0


def test_normalize_chat_id():
    assert normalize_chat_id("my_channel") == "@my_channel"
    assert normalize_chat_id("1004357582053") == "-1004357582053"


@pytest.mark.asyncio
async def test_lookup_chat_returns_info(monkeypatch):
    class FakeResp:
        def json(self):
            return {
                "ok": True,
                "result": {
                    "id": -100123,
                    "type": "channel",
                    "title": "News",
                    "username": "newsroom",
                },
            }

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            return FakeResp()

    monkeypatch.setattr("httpx.AsyncClient", FakeClient)
    ok, msg, info = await lookup_chat("newsroom", "token")
    assert ok is True
    assert info["chat_id"] == "@newsroom"
    assert info["title"] == "News"
    assert "News" in msg
