from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.settings_store import get_setting, set_setting
from app.telegram_user import (
    KEY_AUTH_HASH,
    KEY_AUTH_NEEDS_PASSWORD,
    KEY_AUTH_PENDING_SESSION,
    KEY_AUTH_PHONE,
    KEY_USER_DISPLAY,
    KEY_USER_SESSION,
    TelegramUserError,
    clear_user_session,
    complete_user_login,
    get_user_session,
    start_user_login,
    user_auth_status,
    user_client_configured,
)


def test_user_client_configured(monkeypatch, db):
    monkeypatch.setenv("TELEGRAM_API_ID", "123")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
    monkeypatch.delenv("TELEGRAM_SESSION", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    assert user_client_configured(db) is False
    set_setting(db, KEY_USER_SESSION, "sess")
    assert user_client_configured(db) is True
    get_settings.cache_clear()


def test_get_user_session_prefers_db(db, monkeypatch):
    monkeypatch.setenv("TELEGRAM_SESSION", "env-sess")
    from app.config import get_settings

    get_settings.cache_clear()
    assert get_user_session(db) == "env-sess"
    set_setting(db, KEY_USER_SESSION, "db-sess")
    assert get_user_session(db) == "db-sess"
    get_settings.cache_clear()


def test_clear_user_session_overrides_env(db, monkeypatch):
    monkeypatch.setenv("TELEGRAM_SESSION", "env-sess")
    from app.config import get_settings

    get_settings.cache_clear()
    assert get_user_session(db) == "env-sess"
    clear_user_session(db)
    assert get_user_session(db) == ""
    status = user_auth_status(db)
    assert status["session_ok"] is False
    assert status["from_env_only"] is False
    get_settings.cache_clear()


def test_api_credentials_from_db(db, monkeypatch):
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)
    from app.config import get_settings
    from app.telegram_user import (
        api_credentials_configured,
        get_api_hash,
        get_api_id,
        set_api_credentials,
    )

    get_settings.cache_clear()
    assert api_credentials_configured(db) is False
    set_api_credentials(db, "42", "abcdefghijklmnop")
    assert get_api_id(db) == 42
    assert get_api_hash(db) == "abcdefghijklmnop"
    assert api_credentials_configured(db) is True
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_start_user_login_stores_pending(db, monkeypatch):
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hashhash")
    from app.config import get_settings

    get_settings.cache_clear()

    class FakeSent:
        phone_code_hash = "hash123"

    class FakeSession:
        def save(self):
            return "pending-sess"

    class FakeClient:
        def __init__(self, *a, **k):
            self.session = FakeSession()

        async def connect(self):
            return None

        async def send_code_request(self, phone):
            assert phone == "+6591234567"
            return FakeSent()

        async def disconnect(self):
            return None

    with (
        patch("telethon.TelegramClient", FakeClient),
        patch("telethon.sessions.StringSession"),
    ):
        phone = await start_user_login(db, "+65 9123 4567")
    assert phone == "+6591234567"
    assert get_setting(db, KEY_AUTH_PHONE) == "+6591234567"
    assert get_setting(db, KEY_AUTH_HASH) == "hash123"
    assert get_setting(db, KEY_AUTH_PENDING_SESSION) == "pending-sess"
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_complete_user_login_saves_session(db, monkeypatch):
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hashhash")
    from app.config import get_settings

    get_settings.cache_clear()
    set_setting(db, KEY_AUTH_PHONE, "+651234")
    set_setting(db, KEY_AUTH_HASH, "hash123")
    set_setting(db, KEY_AUTH_PENDING_SESSION, "pending")

    class FakeMe:
        first_name = "Ada"
        username = "ada"
        id = 1

    class FakeSession:
        def save(self):
            return "final-sess"

    class FakeClient:
        def __init__(self, *a, **k):
            self.session = FakeSession()

        async def connect(self):
            return None

        async def sign_in(self, *a, **k):
            return None

        async def is_user_authorized(self):
            return True

        async def get_me(self):
            return FakeMe()

        async def disconnect(self):
            return None

    with (
        patch("telethon.TelegramClient", FakeClient),
        patch("telethon.sessions.StringSession"),
    ):
        name = await complete_user_login(db, code="12345")
    assert name == "Ada"
    assert get_setting(db, KEY_USER_SESSION) == "final-sess"
    assert get_setting(db, KEY_USER_DISPLAY) == "Ada"
    assert get_setting(db, KEY_AUTH_PHONE) == ""
    status = user_auth_status(db)
    assert status["session_ok"] is True
    get_settings.cache_clear()


def test_clear_user_session(db):
    set_setting(db, KEY_USER_SESSION, "x")
    set_setting(db, KEY_USER_DISPLAY, "Ada")
    clear_user_session(db)
    assert get_setting(db, KEY_USER_SESSION) == ""
    assert get_setting(db, KEY_USER_DISPLAY) == ""


def test_setup_user_phone_route(auth_client, db, monkeypatch):
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hashhash")
    from app.config import get_settings

    get_settings.cache_clear()

    async def fake_start(db_, phone):
        set_setting(db_, KEY_AUTH_PHONE, phone)
        return phone

    monkeypatch.setattr("app.routers.setup_routes.start_user_login", fake_start)
    async def fake_username(db_):
        return "mybot"

    monkeypatch.setattr("app.routers.setup_routes.fetch_bot_username", fake_username)
    r = auth_client.post(
        "/setup/user/phone",
        data={"phone": "+65999"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "Code+sent" in r.headers["location"] or "Code%20sent" in r.headers["location"]
    get_settings.cache_clear()


def test_setup_user_api_route(auth_client, db, monkeypatch):
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)
    from app.config import get_settings
    from app.telegram_user import api_credentials_configured, get_api_id

    get_settings.cache_clear()
    r = auth_client.post(
        "/setup/user/api",
        data={"api_id": "99", "api_hash": "abcdefghijklmnop"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert api_credentials_configured(db) is True
    assert get_api_id(db) == 99
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_publish_bot_then_user_forward(db, monkeypatch):
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hashhash")
    from app.config import get_settings
    from app.settings_store import set_preview_chat_id
    from app.telegram_user import publish_post_as_user

    get_settings.cache_clear()
    set_setting(db, KEY_USER_SESSION, "sess")
    set_preview_chat_id(db, "111")

    sent = {}
    forwarded = {}
    deleted = {}

    async def fake_send(chat_id, caption, media, **kwargs):
        sent["chat_id"] = chat_id
        sent["caption"] = caption
        return [42]

    async def fake_delete(chat_id, message_ids, **kwargs):
        deleted["chat_id"] = chat_id
        deleted["ids"] = message_ids

    async def fake_bot_username(db_):
        return "mybot"

    class FakeMsg:
        def __init__(self, mid):
            self.id = mid
            self.out = False

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def connect(self):
            return None

        async def is_user_authorized(self):
            return True

        async def get_entity(self, peer):
            return peer

        async def get_messages(self, peer, ids=None, limit=None):
            if ids is not None:
                return [FakeMsg(i) for i in ids]
            return []

        async def forward_messages(self, dest, messages):
            forwarded["dest"] = dest
            forwarded["ids"] = [m.id for m in messages]
            return messages

        async def disconnect(self):
            return None

    with (
        patch("app.telegram_client.send_post", fake_send),
        patch("app.telegram_client.delete_messages", fake_delete),
        patch("app.telegram_updates.fetch_bot_username", fake_bot_username),
        patch("app.telegram_user.asyncio.sleep", AsyncMock()),
        patch("telethon.TelegramClient", FakeClient),
        patch("telethon.sessions.StringSession"),
    ):
        await publish_post_as_user("@channel", "hello world", [], db=db)

    assert sent == {"chat_id": "111", "caption": "hello world"}
    assert forwarded == {"dest": "@channel", "ids": [42]}
    assert deleted == {"chat_id": "111", "ids": [42]}
    get_settings.cache_clear()
