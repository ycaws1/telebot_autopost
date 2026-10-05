from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Channel, Post


def create_channel(db: Session, name: str, chat_id: str) -> Channel:
    channel = Channel(name=name.strip(), chat_id=chat_id.strip())
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def list_channels(db: Session) -> list[Channel]:
    return db.query(Channel).order_by(Channel.name).all()


def delete_channel(db: Session, channel_id: int) -> None:
    channel = db.get(Channel, channel_id)
    if channel is None:
        raise ValueError("Channel not found")
    if db.query(Post).filter(Post.channel_id == channel_id).count() > 0:
        raise ValueError("Cannot delete channel while posts still reference it")
    db.delete(channel)
    db.commit()
