from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.config import get_settings


def app_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def to_utc(dt: datetime) -> datetime:
    """Normalize any datetime to timezone-aware UTC."""
    if dt.tzinfo is None:
        # Interpret naive values as app local time (form input convention).
        dt = dt.replace(tzinfo=app_tz())
    return dt.astimezone(timezone.utc)


def assume_utc(dt: datetime) -> datetime:
    """Treat DB-loaded naive datetimes as UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_local(dt: datetime) -> datetime:
    return assume_utc(dt).astimezone(app_tz())


def parse_local_datetime(value: str) -> datetime:
    """Parse HTML datetime-local (naive) as app timezone, return UTC."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=app_tz())
    return to_utc(dt)


def format_local_input(dt: datetime) -> str:
    """Format for datetime-local input value."""
    local = to_local(dt)
    return local.strftime("%Y-%m-%dT%H:%M")


def format_local_display(dt: datetime) -> str:
    local = to_local(dt)
    return local.strftime("%Y-%m-%d %H:%M:%S %Z")
