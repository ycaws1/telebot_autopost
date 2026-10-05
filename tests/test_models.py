from datetime import datetime, timezone

from app import db as dbmod
from app.models import Channel, Post, PostMedia, PostStatus, User


def test_create_post_with_media(tmp_db):
    db = dbmod.SessionLocal()
    user = User(username="a", password_hash="x")
    ch = Channel(name="News", chat_id="@news")
    db.add_all([user, ch])
    db.commit()
    post = Post(
        channel_id=ch.id,
        caption="hello",
        scheduled_at=datetime.now(timezone.utc),
        status=PostStatus.PENDING,
    )
    db.add(post)
    db.flush()
    db.add(
        PostMedia(
            post_id=post.id, media_type="photo", media_path="a.jpg", sort_order=0
        )
    )
    db.commit()
    loaded = db.get(Post, post.id)
    assert loaded.media[0].media_type == "photo"
    assert loaded.status == PostStatus.PENDING
    db.close()
