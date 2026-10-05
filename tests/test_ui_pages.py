from datetime import datetime, timezone, timedelta


def test_dashboard_lists_pending(auth_client, db):
    from app.services.channels import create_channel
    from app.services import posts as posts_svc

    ch = create_channel(db, "C", "@c")
    posts_svc.create_post(
        db,
        channel_id=ch.id,
        caption="soon",
        scheduled_at=datetime.now(timezone.utc) + timedelta(hours=2),
        files=[],
    )
    r = auth_client.get("/")
    assert r.status_code == 200
    assert b"soon" in r.content


def test_new_post_form(auth_client, db):
    from app.services.channels import create_channel

    create_channel(db, "C", "@c")
    r = auth_client.get("/posts/new")
    assert r.status_code == 200
    assert b"caption" in r.content.lower() or b"Caption" in r.content


def test_edit_form_for_pending(auth_client, db):
    from app.services.channels import create_channel
    from app.services import posts as posts_svc

    ch = create_channel(db, "C", "@c")
    p = posts_svc.create_post(
        db,
        channel_id=ch.id,
        caption="editme",
        scheduled_at=datetime.now(timezone.utc) + timedelta(hours=2),
        files=[],
    )
    r = auth_client.get(f"/posts/{p.id}/edit")
    assert r.status_code == 200
    assert b"editme" in r.content
