def test_app_starts_and_login_page(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert b"password" in r.content.lower()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "db": "ok"}
