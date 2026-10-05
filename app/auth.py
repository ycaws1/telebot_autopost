from __future__ import annotations

import bcrypt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.config import get_settings
from app.db import get_db
from app.models import User


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def bootstrap_admin(db: Session) -> None:
    if db.query(User).count() > 0:
        return
    settings = get_settings()
    user = User(
        username=settings.admin_username,
        password_hash=hash_password(settings.admin_password),
    )
    db.add(user)
    db.commit()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if user is None:
        raise HTTPException(
            status_code=303,
            headers={"Location": "/login"},
        )
    return user


def login_redirect():
    return RedirectResponse("/login", status_code=303)
