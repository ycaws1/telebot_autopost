from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Channel, Post


def normalize_chat_id(chat_id: str) -> str:
    value = chat_id.strip().replace(" ", "")
    if not value:
        return value
    # Telegram channel/supergroup ids are typically -100...
    if value.isdigit() and value.startswith("100") and len(value) >= 13:
        return f"-{value}"
    if value.startswith("@") or value.startswith("-") or value.lstrip("-").isdigit():
        return value
    return f"@{value}"


async def verify_chat_id(chat_id: str, bot_token: str) -> tuple[bool, str]:
    """Return (ok, message). Uses Telegram getChat."""
    ok, message, _ = await lookup_chat(chat_id, bot_token)
    return ok, message


async def lookup_chat(
    chat_id: str, bot_token: str
) -> tuple[bool, str, dict | None]:
    """Resolve @username or numeric id via getChat.

    Returns (ok, message, info) where info has chat_id, title, username when ok.
    Telegram has no search-by-title API — public @username or numeric id only.
    """
    import httpx

    normalized = normalize_chat_id(chat_id)
    if not normalized:
        return False, "Enter a channel @username or -100… id", None
    url = f"https://api.telegram.org/bot{bot_token}/getChat"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, params={"chat_id": normalized})
            body = resp.json()
    except Exception as exc:
        return False, f"Could not reach Telegram: {exc}", None
    if not body.get("ok"):
        return False, body.get("description") or "Telegram rejected this chat id", None
    result = body.get("result") or {}
    username = result.get("username")
    title = result.get("title") or username or normalized
    numeric_id = str(result.get("id") or normalized)
    # Prefer @username for storage when public; else numeric id from Telegram
    store_id = f"@{username}" if username else numeric_id
    info = {
        "chat_id": store_id,
        "numeric_id": numeric_id,
        "title": title,
        "username": username,
        "type": result.get("type"),
    }
    return True, f"OK — {title} ({store_id})", info


def create_channel(db: Session, name: str, chat_id: str) -> Channel:
    channel = Channel(name=name.strip(), chat_id=normalize_chat_id(chat_id))
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def list_channels(db: Session) -> list[Channel]:
    return db.query(Channel).order_by(Channel.name).all()


def delete_channel(db: Session, channel_id: int, *, cascade: bool = False) -> None:
    channel = db.get(Channel, channel_id)
    if channel is None:
        raise ValueError("Channel not found")
    posts = db.query(Post).filter(Post.channel_id == channel_id).all()
    if posts and not cascade:
        raise ValueError(
            f"Cannot delete channel while {len(posts)} post(s) still reference it"
        )
    if cascade:
        from pathlib import Path

        for post in posts:
            for media in list(post.media):
                path = Path(media.media_path)
                if path.is_file():
                    path.unlink(missing_ok=True)
                db.delete(media)
            db.delete(post)
    db.delete(channel)
    db.commit()
