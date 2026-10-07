from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.services.channels import create_channel, normalize_chat_id
from app.services import posts as posts_svc
from app.models import PostStatus
from app.scheduler import process_due_posts
from app.timeutil import assume_utc, parse_local_datetime


def test_normalize_chat_id_adds_at():
    assert normalize_chat_id("my_channel") == "@my_channel"
    assert normalize_chat_id("@already") == "@already"
    assert normalize_chat_id("-100123") == "-100123"
    assert normalize_chat_id("1004357582053") == "-1004357582053"


def test_parse_local_datetime_to_utc(monkeypatch):
    monkeypatch.setenv("TIMEZONE", "Asia/Singapore")
    from app.config import get_settings

    get_settings.cache_clear()
    dt = parse_local_datetime("2026-10-05T11:54")
    assert dt == datetime(2026, 10, 5, 3, 54, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_local_schedule_is_due_against_utc(db, monkeypatch):
    monkeypatch.setenv("TIMEZONE", "Asia/Singapore")
    from app.config import get_settings

    get_settings.cache_clear()
    ch = create_channel(db, "C", "@c")
    local = datetime(2026, 10, 5, 11, 54, tzinfo=ZoneInfo("Asia/Singapore"))
    p = posts_svc.create_post(
        db,
        channel_id=ch.id,
        caption="hi",
        scheduled_at=local,
        files=[],
    )
    assert assume_utc(p.scheduled_at) == datetime(
        2026, 10, 5, 3, 54, tzinfo=timezone.utc
    )

    sent = []

    async def fake_send(chat_id, caption, media, **kwargs):
        sent.append(chat_id)

    class _FrozenDateTime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 5, 3, 55, tzinfo=timezone.utc)

    monkeypatch.setattr("app.scheduler.datetime", _FrozenDateTime)
    n = await process_due_posts(lambda: db, send=fake_send)
    assert n == 1
    db.refresh(p)
    assert p.status == PostStatus.POSTED
    assert sent == ["@c"]
