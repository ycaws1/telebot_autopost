import pytest

from app.config import get_settings
from app.db import Base, engine, init_db, reset_engine


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setenv("BOT_TOKEN", "t")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("PREVIEW_CHAT_ID", "1")
    get_settings.cache_clear()
    reset_engine()
    init_db()
    yield
    Base.metadata.drop_all(bind=engine())
    reset_engine()
    get_settings.cache_clear()
