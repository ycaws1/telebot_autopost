from fastapi.testclient import TestClient

from app.auth import hash_password, verify_password
from app.main import app


def test_hash_and_verify():
    h = hash_password("secret")
    assert verify_password("secret", h)
    assert not verify_password("wrong", h)


def test_login_success_and_protected_route(client, admin_user):
    r = client.post(
        "/login",
        data={"username": "admin", "password": "secret"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    r2 = client.get("/")
    assert r2.status_code == 200


def test_login_bad_password(client, admin_user):
    r = client.post("/login", data={"username": "admin", "password": "nope"})
    assert r.status_code == 200
    assert b"Invalid" in r.content or b"invalid" in r.content.lower()


def test_unauthenticated_redirect(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/login" in r.headers["location"]
