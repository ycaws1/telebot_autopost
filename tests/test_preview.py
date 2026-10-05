from unittest.mock import patch


def test_dm_preview_uses_preview_chat_id(auth_client, monkeypatch):
    calls = []

    async def fake_send(chat_id, caption, media, **kwargs):
        calls.append(chat_id)

    monkeypatch.setenv("PREVIEW_CHAT_ID", "424242")
    from app.config import get_settings

    get_settings.cache_clear()
    with patch("app.routers.post_routes.send_post", side_effect=fake_send):
        r = auth_client.post(
            "/posts/preview",
            data={"caption": "preview hi"},
        )
    assert r.status_code in (200, 302, 303)
    assert calls == ["424242"]


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
        auth_client.post("/posts/preview", data={"caption": "x", "channel_id": "1"})
    assert calls == ["111"]
