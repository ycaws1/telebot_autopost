from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.models import Channel, SetupCandidate, SetupSession
from app.services import setup as setup_svc
from app.settings_store import get_preview_chat_id, set_preview_chat_id
from app.telegram_updates import process_update


def test_get_preview_chat_id_prefers_db(db, monkeypatch):
    monkeypatch.setenv("PREVIEW_CHAT_ID", "env-id")
    from app.config import get_settings

    get_settings.cache_clear()
    assert get_preview_chat_id(db) == "env-id"
    set_preview_chat_id(db, "db-id")
    assert get_preview_chat_id(db) == "db-id"


def test_clear_preview_overrides_env(db, monkeypatch):
    from app.settings_store import clear_preview_chat_id

    monkeypatch.setenv("PREVIEW_CHAT_ID", "env-id")
    from app.config import get_settings

    get_settings.cache_clear()
    set_preview_chat_id(db, "555")
    clear_preview_chat_id(db)
    assert get_preview_chat_id(db) == ""


def test_mint_code_expires_and_pairs(db, admin_user):
    s1 = setup_svc.mint_setup_code(db, admin_user.id)
    assert len(s1.code) == 6
    s2 = setup_svc.mint_setup_code(db, admin_user.id)
    db.refresh(s1)
    assert s1.status == "expired"
    assert s2.status == "pending"
    found = setup_svc.find_session_by_code(db, s2.code)
    assert found is not None
    setup_svc.pair_session(db, found, "424242")
    db.refresh(found)
    assert found.status == "paired"
    assert found.telegram_user_id == "424242"


def test_expired_code_rejected(db, admin_user):
    session = setup_svc.mint_setup_code(db, admin_user.id)
    session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert setup_svc.find_session_by_code(db, session.code) is None


@pytest.mark.asyncio
async def test_start_code_creates_preview_candidate(db, admin_user):
    session = setup_svc.mint_setup_code(db, admin_user.id)
    with patch("app.telegram_updates._send_message", new_callable=AsyncMock) as send:
        await process_update(
            db,
            {
                "update_id": 1,
                "message": {
                    "message_id": 10,
                    "text": f"/start {session.code}",
                    "chat": {"id": 777, "type": "private"},
                    "from": {"id": 777, "first_name": "Ada", "username": "ada"},
                },
            },
        )
    db.refresh(session)
    assert session.status == "paired"
    assert session.telegram_user_id == "777"
    cand = (
        db.query(SetupCandidate)
        .filter(SetupCandidate.session_id == session.id, SetupCandidate.kind == "preview")
        .one()
    )
    assert cand.chat_id == "777"
    assert cand.title == "Ada"
    send.assert_awaited()


@pytest.mark.asyncio
async def test_channel_post_creates_candidate(db, admin_user):
    session = setup_svc.mint_setup_code(db, admin_user.id)
    setup_svc.pair_session(db, session, "777")
    with patch("app.telegram_updates._send_message", new_callable=AsyncMock) as send:
        await process_update(
            db,
            {
                "update_id": 2,
                "channel_post": {
                    "message_id": 99,
                    "chat": {
                        "id": -1001234567890,
                        "type": "channel",
                        "title": "News",
                        "username": "newsroom",
                    },
                    "text": "hello",
                },
            },
        )
    cand = (
        db.query(SetupCandidate)
        .filter(SetupCandidate.session_id == session.id, SetupCandidate.kind == "channel")
        .one()
    )
    assert cand.chat_id == "-1001234567890"
    assert cand.title == "News"
    assert cand.username == "newsroom"
    send.assert_awaited()


@pytest.mark.asyncio
async def test_callback_selects_candidate(db, admin_user):
    session = setup_svc.mint_setup_code(db, admin_user.id)
    setup_svc.pair_session(db, session, "777")
    cand = setup_svc.upsert_candidate(
        db, session=session, kind="preview", chat_id="777", title="Ada"
    )
    with (
        patch("app.telegram_updates._answer_callback", new_callable=AsyncMock),
        patch("app.telegram_updates._edit_message", new_callable=AsyncMock),
    ):
        await process_update(
            db,
            {
                "update_id": 3,
                "callback_query": {
                    "id": "cb1",
                    "data": f"sel:preview:{cand.id}",
                    "from": {"id": 777},
                    "message": {
                        "message_id": 5,
                        "chat": {"id": 777, "type": "private"},
                    },
                },
            },
        )
    db.refresh(cand)
    assert cand.selected == 1
    assert get_preview_chat_id(db) == "777"


@pytest.mark.asyncio
async def test_callback_adds_channel_without_web_confirm(db, admin_user):
    from app.models import Channel

    session = setup_svc.mint_setup_code(db, admin_user.id)
    setup_svc.pair_session(db, session, "777")
    cand = setup_svc.upsert_candidate(
        db,
        session=session,
        kind="channel",
        chat_id="-100123",
        title="News",
        username="newsroom",
    )
    with (
        patch("app.telegram_updates._answer_callback", new_callable=AsyncMock),
        patch("app.telegram_updates._edit_message", new_callable=AsyncMock),
    ):
        await process_update(
            db,
            {
                "update_id": 4,
                "callback_query": {
                    "id": "cb2",
                    "data": f"sel:channel:{cand.id}",
                    "from": {"id": 777},
                    "message": {
                        "message_id": 6,
                        "chat": {"id": 777, "type": "private"},
                    },
                },
            },
        )
    db.refresh(cand)
    assert cand.selected == 1
    ch = db.query(Channel).filter(Channel.chat_id == "@newsroom").one()
    assert ch.name == "News"


def test_setup_page_requires_login(client):
    r = client.get("/setup", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_setup_mint_status_save_preview(auth_client, db, admin_user, monkeypatch):
    async def fake_username(db_):
        return "mybot"

    monkeypatch.setattr(
        "app.routers.setup_routes.fetch_bot_username", fake_username
    )
    r = auth_client.get("/setup")
    assert r.status_code == 200
    assert "Telegram setup" in r.text
    assert "mybot" in r.text

    status = auth_client.get("/setup/status")
    assert status.status_code == 200
    body = status.json()
    assert body["ok"] is True
    assert body["session"]["code"]
    code = body["session"]["code"]

    session = db.query(SetupSession).filter(SetupSession.code == code).one()
    setup_svc.pair_session(db, session, "555")
    cand = setup_svc.upsert_candidate(
        db, session=session, kind="preview", chat_id="555", title="Bob", selected=True
    )

    r = auth_client.post(
        "/setup/preview/save",
        data={"candidate_id": str(cand.id)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert get_preview_chat_id(db) == "555"

    status2 = auth_client.get("/setup/status").json()
    assert status2["preview_chat_id"] == "555"
    assert status2["session"]["status"] == "paired"


def test_setup_add_channel_from_candidate(auth_client, db, admin_user, monkeypatch):
    async def fake_username(db_):
        return "mybot"

    async def fake_verify(chat_id, bot_token):
        return True, f"OK — News ({chat_id})"

    monkeypatch.setattr("app.routers.setup_routes.fetch_bot_username", fake_username)
    monkeypatch.setattr(
        "app.routers.setup_routes.channels_svc.verify_chat_id", fake_verify
    )

    auth_client.get("/setup")
    session = setup_svc.get_active_session_for_user(db, admin_user.id)
    assert session is not None
    setup_svc.pair_session(db, session, "555")
    cand = setup_svc.upsert_candidate(
        db,
        session=session,
        kind="channel",
        chat_id="-100999",
        title="News",
        username="newsroom",
        selected=True,
    )
    r = auth_client.post(
        "/setup/channels/add",
        data={"candidate_id": str(cand.id), "name": "News"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    ch = db.query(Channel).filter(Channel.name == "News").one()
    assert ch.chat_id == "@newsroom"


def test_setup_lookup_channel_adds(auth_client, db, monkeypatch):
    async def fake_lookup(query, bot_token):
        return (
            True,
            "OK — News (@newsroom)",
            {
                "chat_id": "@newsroom",
                "numeric_id": "-100123",
                "title": "News",
                "username": "newsroom",
                "type": "channel",
            },
        )

    async def fake_username(db_):
        return "mybot"

    monkeypatch.setattr(
        "app.routers.setup_routes.channels_svc.lookup_chat", fake_lookup
    )
    monkeypatch.setattr("app.routers.setup_routes.fetch_bot_username", fake_username)
    r = auth_client.post(
        "/setup/channels/lookup",
        data={"query": "@newsroom", "name": "News"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    from app.models import Channel

    db.expire_all()
    ch = db.query(Channel).filter(Channel.chat_id == "@newsroom").one()
    assert ch.name == "News"


def test_setup_lookup_uses_existing(auth_client, db, monkeypatch):
    from app.services.channels import create_channel

    create_channel(db, "News", "@newsroom")

    async def fake_lookup(query, bot_token):
        return (
            True,
            "OK — News (@newsroom)",
            {
                "chat_id": "@newsroom",
                "numeric_id": "-100123",
                "title": "News",
                "username": "newsroom",
                "type": "channel",
            },
        )

    async def fake_username(db_):
        return "mybot"

    monkeypatch.setattr(
        "app.routers.setup_routes.channels_svc.lookup_chat", fake_lookup
    )
    monkeypatch.setattr("app.routers.setup_routes.fetch_bot_username", fake_username)
    r = auth_client.post(
        "/setup/channels/lookup",
        data={"query": "@newsroom"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "Using+existing" in r.headers["location"] or "Using%20existing" in r.headers["location"]
    from app.models import Channel

    assert db.query(Channel).count() == 1


def test_setup_add_uses_existing_channel(auth_client, db, admin_user, monkeypatch):
    from app.services.channels import create_channel

    create_channel(db, "News", "@newsroom")

    async def fake_username(db_):
        return "mybot"

    async def fake_verify(chat_id, bot_token):
        return True, "OK"

    monkeypatch.setattr("app.routers.setup_routes.fetch_bot_username", fake_username)
    monkeypatch.setattr(
        "app.routers.setup_routes.channels_svc.verify_chat_id", fake_verify
    )
    auth_client.get("/setup")
    session = setup_svc.get_active_session_for_user(db, admin_user.id)
    cand = setup_svc.upsert_candidate(
        db,
        session=session,
        kind="channel",
        chat_id="-100999",
        title="News",
        username="newsroom",
    )
    r = auth_client.post(
        "/setup/channels/add",
        data={"candidate_id": str(cand.id)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "Using+existing" in r.headers["location"] or "Using%20existing" in r.headers["location"]
    from app.models import Channel

    assert db.query(Channel).count() == 1


def test_setup_test_preview_sends(auth_client, db, monkeypatch):
    set_preview_chat_id(db, "888")
    calls = []

    async def fake_send(chat_id, caption, media, **kwargs):
        calls.append((chat_id, caption))

    monkeypatch.setattr("app.routers.setup_routes.send_post", fake_send)
    async def fake_username(db_):
        return "mybot"

    monkeypatch.setattr("app.routers.setup_routes.fetch_bot_username", fake_username)
    r = auth_client.post("/setup/test-preview", follow_redirects=False)
    assert r.status_code == 303
    assert calls == [("888", "Setup OK — Telebot can DM you.")]


def test_setup_reset_clears_pairing_preview_and_user(auth_client, db, admin_user, monkeypatch):
    async def fake_username(db_):
        return "mybot"

    monkeypatch.setattr("app.routers.setup_routes.fetch_bot_username", fake_username)
    set_preview_chat_id(db, "555")
    from app.settings_store import get_setting, set_setting
    from app.telegram_user import (
        KEY_API_HASH,
        KEY_API_ID,
        KEY_USER_DISPLAY,
        KEY_USER_SESSION,
        api_credentials_configured,
        get_user_session,
        set_api_credentials,
    )

    set_api_credentials(db, "39208283", "abcdefghijklmnop")
    set_setting(db, KEY_USER_SESSION, "sess")
    set_setting(db, KEY_USER_DISPLAY, "C")
    session = setup_svc.mint_setup_code(db, admin_user.id)
    setup_svc.pair_session(db, session, "555")
    setup_svc.upsert_candidate(
        db, session=session, kind="preview", chat_id="555", title="Bob"
    )
    old_code = session.code

    r = auth_client.post("/setup/reset", follow_redirects=False)
    assert r.status_code == 303
    assert "Setup%20reset" in r.headers["location"]

    from app.models import AppSetting
    from app.settings_store import KEY_PREVIEW_CHAT_ID

    db.expire_all()
    assert get_preview_chat_id(db) == ""
    assert get_user_session(db) == ""
    assert get_setting(db, KEY_USER_DISPLAY) == ""
    assert get_setting(db, KEY_API_ID) == ""
    assert get_setting(db, KEY_API_HASH) == ""
    assert api_credentials_configured(db) is False
    row = db.get(AppSetting, KEY_PREVIEW_CHAT_ID)
    assert row is not None
    assert row.value == ""
    assert db.query(SetupSession).filter(SetupSession.code == old_code).first() is None
    fresh = setup_svc.get_active_session_for_user(db, admin_user.id)
    assert fresh is not None
    assert fresh.status == "pending"
    assert fresh.telegram_user_id is None
    assert fresh.code != old_code
    assert (
        db.query(SetupCandidate)
        .filter(SetupCandidate.session_id == fresh.id, SetupCandidate.kind == "preview")
        .count()
        == 0
    )


def test_dashboard_banner_when_incomplete(auth_client, db, monkeypatch):
    from app.settings_store import clear_preview_chat_id

    monkeypatch.setenv("PREVIEW_CHAT_ID", "1")
    from app.config import get_settings

    get_settings.cache_clear()
    clear_preview_chat_id(db)

    r = auth_client.get("/")
    assert r.status_code == 200
    assert "Setup incomplete" in r.text
    assert "/setup" in r.text
