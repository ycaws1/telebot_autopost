# tests/test_config.py
from pathlib import Path

def test_get_settings_reads_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("TIMEZONE", "Asia/Singapore")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("PREVIEW_CHAT_ID", "999")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))
    from app.config import get_settings
    get_settings.cache_clear()
    s = get_settings()
    assert s.bot_token == "123:ABC"
    assert s.preview_chat_id == "999"
    assert s.timezone == "Asia/Singapore"
    assert Path(s.media_dir).name == "media"
