from unittest.mock import patch


def test_dm_preview_uses_preview_chat_id(auth_client, monkeypatch):
    calls = []

    async def fake_send(chat_id, caption, media, **kwargs):
        calls.append((chat_id, caption))

    monkeypatch.setenv("PREVIEW_CHAT_ID", "424242")
    from app.config import get_settings

    get_settings.cache_clear()
    with patch("app.routers.post_routes.send_post", side_effect=fake_send):
        r = auth_client.post(
            "/posts/preview",
            data={"caption": "preview hi"},
            headers={"Accept": "application/json"},
        )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert calls == [("424242", "[Preview]\npreview hi")]


def test_dm_preview_never_uses_channel(auth_client, db, monkeypatch):
    from app.services.channels import create_channel

    create_channel(db, "C", "@should-not-send")
    calls = []

    async def fake_send(chat_id, caption, media, **kwargs):
        calls.append(chat_id)

    monkeypatch.setenv("PREVIEW_CHAT_ID", "111")
    from app.config import get_settings

    get_settings.cache_clear()
    with patch("app.routers.post_routes.send_post", side_effect=fake_send):
        r = auth_client.post(
            "/posts/preview",
            data={"caption": "x", "channel_id": "1"},
            headers={"Accept": "application/json"},
        )
    assert r.status_code == 200
    assert calls == ["111"]


def test_dm_preview_error_json(auth_client, monkeypatch):
    async def boom(*a, **k):
        from app.telegram_client import TelegramError

        raise TelegramError("nope")

    monkeypatch.setenv("PREVIEW_CHAT_ID", "1")
    from app.config import get_settings

    get_settings.cache_clear()
    with patch("app.routers.post_routes.send_post", side_effect=boom):
        r = auth_client.post(
            "/posts/preview",
            data={"caption": "x"},
            headers={"Accept": "application/json"},
        )
    assert r.status_code == 400
    assert r.json()["ok"] is False
    assert "nope" in r.json()["error"]
