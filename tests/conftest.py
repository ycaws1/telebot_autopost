import pytest
from fastapi.testclient import TestClient

from app.auth import bootstrap_admin, hash_password
from app.config import get_settings
from app.db import Base, engine, init_db, reset_engine
from app.models import User


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'data' / 'test.db'}")
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


@pytest.fixture
def db(tmp_db):
    from app import db as dbmod

    session = dbmod.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(tmp_db, monkeypatch):
    # Rebuild middleware secret from test settings
    get_settings.cache_clear()
    from app.main import app
    from starlette.middleware.sessions import SessionMiddleware

    # Ensure session secret matches test env
    app.user_middleware = [
        m for m in app.user_middleware if m.cls is not SessionMiddleware
    ]
    app.middleware_stack = None
    app.add_middleware(SessionMiddleware, secret_key=get_settings().secret_key)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_user(db):
    bootstrap_admin(db)
    user = db.query(User).filter(User.username == "admin").first()
    assert user is not None
    return user


@pytest.fixture
def auth_client(client, admin_user):
    client.post("/login", data={"username": "admin", "password": "secret"})
    return client
