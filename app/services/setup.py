from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import SetupCandidate, SetupSession
from app.timeutil import assume_utc

CODE_TTL_MINUTES = 10


def mint_setup_code(db: Session, user_id: int) -> SetupSession:
    """Create a fresh pairing session; expire older pending/paired ones for this user."""
    now = datetime.now(timezone.utc)
    for old in (
        db.query(SetupSession)
        .filter(
            SetupSession.user_id == user_id,
            SetupSession.status.in_(["pending", "paired"]),
        )
        .all()
    ):
        old.status = "expired"
    code = f"{secrets.randbelow(1_000_000):06d}"
    # ensure unique
    while db.query(SetupSession).filter(SetupSession.code == code).first():
        code = f"{secrets.randbelow(1_000_000):06d}"
    session = SetupSession(
        code=code,
        user_id=user_id,
        status="pending",
        expires_at=now + timedelta(minutes=CODE_TTL_MINUTES),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_active_session_for_user(db: Session, user_id: int) -> SetupSession | None:
    now = datetime.now(timezone.utc)
    sessions = (
        db.query(SetupSession)
        .filter(
            SetupSession.user_id == user_id,
            SetupSession.status.in_(["pending", "paired"]),
        )
        .order_by(SetupSession.id.desc())
        .all()
    )
    for s in sessions:
        if assume_utc(s.expires_at) >= now:
            return s
        s.status = "expired"
    db.commit()
    return None


def find_session_by_code(db: Session, code: str) -> SetupSession | None:
    code = (code or "").strip()
    if not code:
        return None
    session = db.query(SetupSession).filter(SetupSession.code == code).first()
    if session is None:
        return None
    if assume_utc(session.expires_at) < datetime.now(timezone.utc):
        session.status = "expired"
        db.commit()
        return None
    if session.status not in ("pending", "paired"):
        return None
    return session


def pair_session(db: Session, session: SetupSession, telegram_user_id: str) -> None:
    session.telegram_user_id = str(telegram_user_id)
    session.status = "paired"
    # Give time after pairing for channel discovery during the wizard.
    session.expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    db.commit()


def upsert_candidate(
    db: Session,
    *,
    session: SetupSession,
    kind: str,
    chat_id: str,
    title: str | None = None,
    username: str | None = None,
    raw_update_id: int | None = None,
    selected: bool = False,
) -> SetupCandidate:
    existing = (
        db.query(SetupCandidate)
        .filter(
            SetupCandidate.session_id == session.id,
            SetupCandidate.kind == kind,
            SetupCandidate.chat_id == str(chat_id),
        )
        .first()
    )
    if existing:
        if title:
            existing.title = title
        if username:
            existing.username = username
        if selected:
            _select_candidate(db, existing)
        else:
            db.commit()
            db.refresh(existing)
        return existing
    cand = SetupCandidate(
        session_id=session.id,
        kind=kind,
        chat_id=str(chat_id),
        title=title,
        username=username,
        selected=1 if selected else 0,
        raw_update_id=raw_update_id,
    )
    db.add(cand)
    db.commit()
    db.refresh(cand)
    if selected:
        _select_candidate(db, cand)
    return cand


def _select_candidate(db: Session, candidate: SetupCandidate) -> None:
    others = (
        db.query(SetupCandidate)
        .filter(
            SetupCandidate.session_id == candidate.session_id,
            SetupCandidate.kind == candidate.kind,
        )
        .all()
    )
    for o in others:
        o.selected = 1 if o.id == candidate.id else 0
    db.commit()
    db.refresh(candidate)


def select_candidate(db: Session, candidate_id: int) -> SetupCandidate | None:
    cand = db.get(SetupCandidate, candidate_id)
    if cand is None:
        return None
    _select_candidate(db, cand)
    return cand


def active_paired_sessions(db: Session) -> list[SetupSession]:
    now = datetime.now(timezone.utc)
    out = []
    for s in (
        db.query(SetupSession)
        .filter(SetupSession.status == "paired")
        .all()
    ):
        if assume_utc(s.expires_at) >= now:
            out.append(s)
        else:
            s.status = "expired"
    db.commit()
    return out


def reset_setup(db: Session, user_id: int) -> SetupSession:
    """Clear pairing sessions/candidates for this user and mint a fresh code.

    Does not delete channels. Caller should clear saved preview_chat_id separately.
    """
    sessions = (
        db.query(SetupSession)
        .filter(SetupSession.user_id == user_id)
        .all()
    )
    for s in sessions:
        db.delete(s)  # cascades candidates
    db.commit()
    return mint_setup_code(db, user_id)
