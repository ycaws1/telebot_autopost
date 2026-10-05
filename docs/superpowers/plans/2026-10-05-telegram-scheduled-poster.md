# Telegram Scheduled Channel Poster Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI web app that schedules one-shot multimedia posts to Telegram channels via Bot API, with login, editable queue, albums, in-browser preview, and DM preview.

**Architecture:** Single FastAPI process with SQLite persistence, session-cookie auth, local media uploads, APScheduler (30s tick) claiming due posts with a soft `posting` lock, and an httpx-based Telegram Bot API client.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, SQLAlchemy 2.0, SQLite, APScheduler, httpx, bcrypt, python-multipart, pytest

**Spec:** `docs/superpowers/specs/2026-10-05-telegram-scheduled-poster-design.md`

## Global Constraints

- Sender is Telegram **Bot API** only (no Telethon / user account).
- One-shot queue: successful post → status `posted`, never resent.
- Max **10** media files per post; mixed photo/video albums allowed.
- Text-only posts require a non-empty caption.
- Timezone from `TIMEZONE` env (default `Asia/Singapore`).
- Media and SQLite live under `media/` and `data/` (gitignored).
- Server-rendered HTML + minimal CSS/JS; no SPA framework.

## Review Focus

- Empty caption + no media → reject create/edit with clear validation error.
- 11th media file → reject with max-10 error before any Telegram call.
- Channel delete while posts exist → blocked with clear error.
- Edit attempted on `posted`/`cancelled` → 400/403, no DB mutation.
- DM preview always targets `PREVIEW_CHAT_ID`, never the post’s channel.

## File Structure

```
telebot/
  app/
    __init__.py
    main.py                 # FastAPI app + lifespan (DB init, reset posting, scheduler)
    config.py               # Settings from env
    db.py                   # engine, SessionLocal, get_db, init_db
    models.py               # User, Channel, Post, PostMedia
    auth.py                 # hash/verify, session helpers, require_user
    telegram_client.py      # send_post(chat_id, caption, media_items) via Bot API
    scheduler.py            # claim due posts, send, update status; reset_stuck_posting
    services/
      channels.py
      posts.py              # create/update/cancel/retry + media save
    routers/
      auth_routes.py
      channel_routes.py
      post_routes.py
      page_routes.py
    templates/
      base.html
      login.html
      dashboard.html
      channels.html
      post_form.html        # new + edit
      post_detail.html
    static/
      styles.css
      preview.js
  media/
  data/
  tests/
    conftest.py
    test_auth.py
    test_channels.py
    test_telegram_client.py
    test_posts.py
    test_scheduler.py
    test_preview.py
  requirements.txt
  .env.example
  .gitignore
  README.md
```

---

### Task 1: Scaffold, config, and settings

**Files:**
- Create: `requirements.txt`, `.gitignore`, `.env.example`, `app/__init__.py`, `app/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: environment variables
- Produces: `Settings` dataclass/pydantic model with fields `bot_token: str`, `secret_key: str`, `timezone: str`, `admin_username: str`, `admin_password: str`, `preview_chat_id: str`, `database_url: str`, `media_dir: Path`, `data_dir: Path`; function `get_settings() -> Settings`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import os
from pathlib import Path

def test_get_settings_reads_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("TIMEZONE", "Asia/Singapore")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("PREVIEW_CHAT_ID", "999")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))
    # clear lru_cache if used
    from app.config import get_settings
    get_settings.cache_clear()
    s = get_settings()
    assert s.bot_token == "123:ABC"
    assert s.preview_chat_id == "999"
    assert s.timezone == "Asia/Singapore"
    assert Path(s.media_dir).name == "media"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_get_settings_reads_env -v`  
Expected: FAIL (module not found)

- [ ] **Step 3: Write minimal implementation**

`requirements.txt`:
```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
sqlalchemy>=2.0.0
httpx>=0.27.0
apscheduler>=3.10.0
bcrypt>=4.0.0
python-multipart>=0.0.9
python-dotenv>=1.0.0
jinja2>=3.1.0
itsdangerous>=2.2.0
pytest>=8.0.0
freezegun>=1.5.0
```

`.gitignore`:
```
.env
__pycache__/
.pytest_cache/
.venv/
venv/
data/
media/
*.db
```

`.env.example`:
```
BOT_TOKEN=
SECRET_KEY=change-me
TIMEZONE=Asia/Singapore
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-me
PREVIEW_CHAT_ID=
DATA_DIR=data
MEDIA_DIR=media
```

`app/config.py`: load dotenv; `@lru_cache` `get_settings()` returning a Settings object (pydantic-settings optional — plain dataclass + os.environ is fine). Default `database_url` to `sqlite:///{data_dir}/telebot.db`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py::test_get_settings_reads_env -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .gitignore .env.example app/__init__.py app/config.py tests/test_config.py
git commit -m "chore: scaffold config and project dependencies"
```

---

### Task 2: Database models and session

**Files:**
- Create: `app/db.py`, `app/models.py`
- Test: `tests/conftest.py`, `tests/test_models.py`

**Interfaces:**
- Consumes: `get_settings().database_url`
- Produces: SQLAlchemy models `User`, `Channel`, `Post`, `PostMedia`; `Base`; `SessionLocal`; `get_db()`; `init_db()`; `PostStatus` enum/str constants: `pending`, `posting`, `posted`, `failed`, `cancelled`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from datetime import datetime, timezone
from app.db import init_db, SessionLocal
from app.models import User, Channel, Post, PostMedia, PostStatus

def test_create_post_with_media(tmp_db):
    db = SessionLocal()
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
    db.add(PostMedia(post_id=post.id, media_type="photo", media_path="a.jpg", sort_order=0))
    db.commit()
    loaded = db.get(Post, post.id)
    assert loaded.media[0].media_type == "photo"
    assert loaded.status == PostStatus.PENDING
    db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py::test_create_post_with_media -v`  
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

- `models.py`: tables per spec; `Post.media` relationship ordered by `sort_order`; `Channel.posts` relationship.
- `db.py`: create engine (SQLite `check_same_thread=False`), `SessionLocal`, `init_db()` creates dirs + `Base.metadata.create_all`.
- `conftest.py`: fixture that sets env to tmp paths, clears settings cache, calls `init_db()`, yields, disposes engine.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/db.py app/models.py tests/conftest.py tests/test_models.py
git commit -m "feat: add SQLAlchemy models and SQLite session"
```

---

### Task 3: Auth (hash, bootstrap admin, login session)

**Files:**
- Create: `app/auth.py`, `app/routers/auth_routes.py`, `app/main.py` (minimal app), `app/templates/base.html`, `app/templates/login.html`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `User` model, `SECRET_KEY`, `ADMIN_*`
- Produces:
  - `hash_password(password: str) -> str`
  - `verify_password(password: str, password_hash: str) -> bool`
  - `bootstrap_admin(db: Session) -> None` — create admin if no users
  - `require_user(request) -> User` dependency (raises 401/redirect)
  - Routes: `GET/POST /login`, `POST /logout`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_auth.py
from fastapi.testclient import TestClient
from app.main import app
from app.auth import hash_password, verify_password

def test_hash_and_verify():
    h = hash_password("secret")
    assert verify_password("secret", h)
    assert not verify_password("wrong", h)

def test_login_success_and_protected_route(client, admin_user):
    r = client.post("/login", data={"username": "admin", "password": "secret"}, follow_redirects=False)
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_auth.py -v`  
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

- bcrypt hash/verify in `auth.py`.
- Starlette `SessionMiddleware` with `secret_key`; store `user_id` in session on login.
- `bootstrap_admin` called from lifespan / `init_db` path.
- Login form template; `TestClient` fixture in conftest that bootstraps admin.
- Minimal `GET /` dashboard stub returning 200 when logged in (full dashboard in Task 8).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_auth.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/auth.py app/routers/auth_routes.py app/main.py app/templates/base.html app/templates/login.html tests/test_auth.py tests/conftest.py
git commit -m "feat: add session auth and admin bootstrap"
```

---

### Task 4: Channels service and routes

**Files:**
- Create: `app/services/channels.py`, `app/routers/channel_routes.py`, `app/templates/channels.html`
- Test: `tests/test_channels.py`

**Interfaces:**
- Consumes: `Channel`, `Post`, db session
- Produces:
  - `create_channel(db, name: str, chat_id: str) -> Channel`
  - `list_channels(db) -> list[Channel]`
  - `delete_channel(db, channel_id: int) -> None` — raises `ValueError` if any posts reference it
  - Routes: `GET /channels`, `POST /channels`, `POST /channels/{id}/delete`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_channels.py
from app.services.channels import create_channel, delete_channel
from app.models import Post, PostStatus
from datetime import datetime, timezone
import pytest

def test_create_and_list(client, auth_headers):
    r = client.post("/channels", data={"name": "Main", "chat_id": "@main"})
    assert r.status_code in (200, 302, 303)
    page = client.get("/channels")
    assert b"Main" in page.content
    assert b"@main" in page.content

def test_delete_blocked_when_posts_exist(db, auth_client):
    ch = create_channel(db, "Main", "@main")
    db.add(Post(channel_id=ch.id, caption="x", scheduled_at=datetime.now(timezone.utc), status=PostStatus.PENDING))
    db.commit()
    with pytest.raises(ValueError, match="posts"):
        delete_channel(db, ch.id)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_channels.py -v`  
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Implement service + form routes + channels template (list, add form, delete button). Flash/error message when delete blocked.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_channels.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/channels.py app/routers/channel_routes.py app/templates/channels.html tests/test_channels.py
git commit -m "feat: add channel CRUD with delete guard"
```

---

### Task 5: Telegram Bot API client

**Files:**
- Create: `app/telegram_client.py`
- Test: `tests/test_telegram_client.py`

**Interfaces:**
- Consumes: `bot_token`, httpx
- Produces:
  - `MediaItem` dataclass: `media_type: Literal["photo","video"]`, `path: Path`
  - `async def send_post(chat_id: str, caption: str | None, media: list[MediaItem], *, bot_token: str | None = None, client: httpx.AsyncClient | None = None) -> None`
  - Raises `TelegramError(message: str)` on non-OK API response or missing files
  - Behavior: 0 media → `sendMessage` (raises if caption empty); 1 photo → `sendPhoto`; 1 video → `sendVideo`; 2+ → `sendMediaGroup` with caption on first; refuse `len(media) > 10`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_telegram_client.py
import pytest
from pathlib import Path
from app.telegram_client import send_post, MediaItem, TelegramError

@pytest.mark.asyncio
async def test_send_text_only(httpx_mock, tmp_path):
    # mock httpx OR pass a fake AsyncClient recording calls
    calls = []
    class Fake:
        async def post(self, url, data=None, files=None):
            calls.append((url, data, files))
            class R:
                def raise_for_status(self): pass
                def json(self): return {"ok": True, "result": {}}
            return R()
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
    await send_post("@ch", "hello", [], bot_token="T", client=Fake())
    assert "sendMessage" in calls[0][0]
    assert calls[0][1]["text"] == "hello"

@pytest.mark.asyncio
async def test_send_single_photo(tmp_path):
    p = tmp_path / "a.jpg"
    p.write_bytes(b"img")
    calls = []
    class Fake:
        async def post(self, url, data=None, files=None):
            calls.append((url, data, files))
            class R:
                def raise_for_status(self): pass
                def json(self): return {"ok": True, "result": {}}
            return R()
    await send_post("@ch", "cap", [MediaItem("photo", p)], bot_token="T", client=Fake())
    assert "sendPhoto" in calls[0][0]

@pytest.mark.asyncio
async def test_reject_more_than_ten(tmp_path):
    items = []
    for i in range(11):
        f = tmp_path / f"{i}.jpg"
        f.write_bytes(b"x")
        items.append(MediaItem("photo", f))
    with pytest.raises(TelegramError, match="10"):
        await send_post("@ch", "c", items, bot_token="T", client=object())

@pytest.mark.asyncio
async def test_text_only_requires_caption():
    with pytest.raises(TelegramError, match="caption"):
        await send_post("@ch", "  ", [], bot_token="T", client=object())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_telegram_client.py -v`  
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Implement `send_post` against `https://api.telegram.org/bot{token}/...`. For albums, build `media` JSON + multipart files per Bot API. Map `ok: false` / HTTP errors to `TelegramError`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_telegram_client.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/telegram_client.py tests/test_telegram_client.py
git commit -m "feat: add Telegram Bot API send_post client"
```

---

### Task 6: Posts service (create, edit, cancel, retry, media)

**Files:**
- Create: `app/services/posts.py`, `app/routers/post_routes.py` (API/form handlers; templates in Task 8 if needed)
- Test: `tests/test_posts.py`

**Interfaces:**
- Consumes: `Post`, `PostMedia`, channels, `MEDIA_DIR`, telegram `MediaItem` types for validation only
- Produces:
  - `create_post(db, *, channel_id, caption, scheduled_at, files: list[tuple[str, bytes, str]]) -> Post`  
    `files` = `(filename, content, media_type)` where media_type is `photo`|`video`; save under `media/{post_id}/`; enforce max 10; text-only requires caption
  - `update_post(db, post_id, **, keep_media_ids, new_files, ...) -> Post` — only if status in `{pending, failed}`; may clear error on edit
  - `cancel_post(db, post_id) -> Post` — only `pending` → `cancelled`
  - `retry_post(db, post_id) -> Post` — only `failed` → clear error, status `pending`
  - `get_post(db, post_id) -> Post`
  - Detect photo vs video from content-type or extension (`.jpg/.jpeg/.png/.webp` → photo; `.mp4/.mov` → video); reject unknown

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_posts.py
from datetime import datetime, timezone, timedelta
import pytest
from app.services import posts as posts_svc
from app.services.channels import create_channel
from app.models import PostStatus

def test_create_text_post(db):
    ch = create_channel(db, "C", "@c")
    p = posts_svc.create_post(db, channel_id=ch.id, caption="hi", scheduled_at=datetime.now(timezone.utc)+timedelta(hours=1), files=[])
    assert p.status == PostStatus.PENDING
    assert p.caption == "hi"

def test_reject_empty_text_only(db):
    ch = create_channel(db, "C", "@c")
    with pytest.raises(ValueError, match="caption"):
        posts_svc.create_post(db, channel_id=ch.id, caption="", scheduled_at=datetime.now(timezone.utc), files=[])

def test_reject_eleven_files(db):
    ch = create_channel(db, "C", "@c")
    files = [(f"{i}.jpg", b"x", "photo") for i in range(11)]
    with pytest.raises(ValueError, match="10"):
        posts_svc.create_post(db, channel_id=ch.id, caption="c", scheduled_at=datetime.now(timezone.utc), files=files)

def test_cannot_edit_posted(db):
    ch = create_channel(db, "C", "@c")
    p = posts_svc.create_post(db, channel_id=ch.id, caption="hi", scheduled_at=datetime.now(timezone.utc), files=[])
    p.status = PostStatus.POSTED
    db.commit()
    with pytest.raises(ValueError, match="edit"):
        posts_svc.update_post(db, p.id, caption="nope")

def test_cancel_and_retry(db):
    ch = create_channel(db, "C", "@c")
    p = posts_svc.create_post(db, channel_id=ch.id, caption="hi", scheduled_at=datetime.now(timezone.utc), files=[])
    posts_svc.cancel_post(db, p.id)
    assert db.get(type(p), p.id).status == PostStatus.CANCELLED
    p2 = posts_svc.create_post(db, channel_id=ch.id, caption="hi", scheduled_at=datetime.now(timezone.utc), files=[])
    p2.status = PostStatus.FAILED
    p2.error = "boom"
    db.commit()
    posts_svc.retry_post(db, p2.id)
    p2 = db.get(type(p2), p2.id)
    assert p2.status == PostStatus.PENDING
    assert p2.error is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_posts.py -v`  
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Implement service methods; wire form routes for create/update/cancel/retry (can render simple strings until Task 8 templates). Persist files to `MEDIA_DIR / str(post_id) / ordered_name`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_posts.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/posts.py app/routers/post_routes.py tests/test_posts.py
git commit -m "feat: add post queue service with edit cancel retry"
```

---

### Task 7: Scheduler (claim, send, recover stuck posting)

**Files:**
- Create: `app/scheduler.py`
- Modify: `app/main.py` (lifespan start/stop scheduler)
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `send_post`, posts/media models, settings
- Produces:
  - `reset_stuck_posting(db) -> int` — `posting` → `pending`
  - `async def process_due_posts(db_factory, send=send_post) -> int` — returns number processed
  - Claim algorithm: `UPDATE posts SET status='posting' WHERE id = (SELECT id FROM posts WHERE status='pending' AND scheduled_at <= :now ORDER BY scheduled_at ASC LIMIT 1) RETURNING ...` or ORM equivalent in a transaction; then send; success → `posted`+`posted_at`; failure → `failed`+`error`
  - `start_scheduler(app)` / stop on shutdown; interval 30 seconds

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scheduler.py
from datetime import datetime, timezone, timedelta
from app.services.channels import create_channel
from app.services import posts as posts_svc
from app.models import PostStatus
from app.scheduler import process_due_posts, reset_stuck_posting

import pytest

@pytest.mark.asyncio
async def test_due_post_becomes_posted(db):
    ch = create_channel(db, "C", "@c")
    p = posts_svc.create_post(db, channel_id=ch.id, caption="hi", scheduled_at=datetime.now(timezone.utc)-timedelta(minutes=1), files=[])
    sent = []
    async def fake_send(chat_id, caption, media, **kwargs):
        sent.append((chat_id, caption))
    n = await process_due_posts(lambda: db, send=fake_send)
    assert n == 1
    db.refresh(p)
    assert p.status == PostStatus.POSTED
    assert p.posted_at is not None
    assert sent == [("@c", "hi")]

@pytest.mark.asyncio
async def test_send_failure_marks_failed(db):
    ch = create_channel(db, "C", "@c")
    p = posts_svc.create_post(db, channel_id=ch.id, caption="hi", scheduled_at=datetime.now(timezone.utc)-timedelta(minutes=1), files=[])
    async def boom(*a, **k):
        raise Exception("bot not admin")
    await process_due_posts(lambda: db, send=boom)
    db.refresh(p)
    assert p.status == PostStatus.FAILED
    assert "bot not admin" in p.error

def test_reset_stuck_posting(db):
    ch = create_channel(db, "C", "@c")
    p = posts_svc.create_post(db, channel_id=ch.id, caption="hi", scheduled_at=datetime.now(timezone.utc), files=[])
    p.status = PostStatus.POSTING
    db.commit()
    assert reset_stuck_posting(db) == 1
    db.refresh(p)
    assert p.status == PostStatus.PENDING

@pytest.mark.asyncio
async def test_future_post_not_sent(db):
    ch = create_channel(db, "C", "@c")
    posts_svc.create_post(db, channel_id=ch.id, caption="hi", scheduled_at=datetime.now(timezone.utc)+timedelta(days=1), files=[])
    async def fake_send(*a, **k):
        raise AssertionError("should not send")
    n = await process_due_posts(lambda: db, send=fake_send)
    assert n == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scheduler.py -v`  
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Implement claim/send/update; on startup in lifespan call `reset_stuck_posting` then start APScheduler `AsyncIOScheduler` interval 30s calling `process_due_posts`. Loop due posts until none left each tick (or process one-by-one in a while loop).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scheduler.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/scheduler.py app/main.py tests/test_scheduler.py
git commit -m "feat: add due-post scheduler with soft lock recovery"
```

---

### Task 8: Web UI pages (dashboard, post form, detail)

**Files:**
- Create/Modify: `app/templates/dashboard.html`, `post_form.html`, `post_detail.html`, `app/static/styles.css`, `app/routers/page_routes.py` / post_routes templates
- Test: `tests/test_ui_pages.py`

**Interfaces:**
- Consumes: services from Tasks 3–6
- Produces: full HTML pages per spec; nav links Login/Dashboard/Channels/New Post

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ui_pages.py
from datetime import datetime, timezone, timedelta

def test_dashboard_lists_pending(auth_client, db):
    from app.services.channels import create_channel
    from app.services import posts as posts_svc
    ch = create_channel(db, "C", "@c")
    posts_svc.create_post(db, channel_id=ch.id, caption="soon", scheduled_at=datetime.now(timezone.utc)+timedelta(hours=2), files=[])
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
    p = posts_svc.create_post(db, channel_id=ch.id, caption="editme", scheduled_at=datetime.now(timezone.utc)+timedelta(hours=2), files=[])
    r = auth_client.get(f"/posts/{p.id}/edit")
    assert r.status_code == 200
    assert b"editme" in r.content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ui_pages.py -v`  
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Jinja templates with simple clean CSS (no purple-gradient AI look — neutral dark-on-light or modest neutrals). Dashboard: upcoming pending + recent posted/failed. Post form: channel select, datetime-local, caption textarea, multi file input, list of existing media with remove checkboxes on edit. Detail: status, error, Cancel/Retry/Edit actions.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ui_pages.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/templates/ app/static/styles.css app/routers/ tests/test_ui_pages.py
git commit -m "feat: add dashboard and post management UI"
```

---

### Task 9: In-browser live preview + real DM preview

**Files:**
- Create: `app/static/preview.js`
- Modify: `app/templates/post_form.html`, `app/routers/post_routes.py`
- Test: `tests/test_preview.py`

**Interfaces:**
- Consumes: `send_post`, `PREVIEW_CHAT_ID`
- Produces:
  - Client JS updating a `.tg-preview` bubble from caption + file input / existing media
  - `POST /posts/preview` — multipart same as create (or post_id + optional draft fields); calls `send_post(preview_chat_id, ...)`; **must not** use channel chat_id; returns flash success/error; does not create a Post row when previewing from unsaved form (preferred: accept draft fields + files)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_preview.py
from unittest.mock import AsyncMock, patch

def test_dm_preview_uses_preview_chat_id(auth_client, monkeypatch):
    calls = []
    async def fake_send(chat_id, caption, media, **kwargs):
        calls.append(chat_id)
    monkeypatch.setenv("PREVIEW_CHAT_ID", "424242")
    from app.config import get_settings
    get_settings.cache_clear()
    with patch("app.routers.post_routes.send_post", side_effect=fake_send):
        r = auth_client.post("/posts/preview", data={"caption": "preview hi"}, files=[])
    assert r.status_code in (200, 302, 303)
    assert calls == ["424242"]

def test_dm_preview_never_uses_channel(auth_client, db, monkeypatch):
    from app.services.channels import create_channel
    create_channel(db, "C", "@should-not-send")
    calls = []
    async def fake_send(chat_id, caption, media, **kwargs):
        calls.append(chat_id)
    monkeypatch.setenv("PREVIEW_CHAT_ID", "111")
    from app.config import get_settings
    get_settings.cache_clear()
    with patch("app.routers.post_routes.send_post", side_effect=fake_send):
        auth_client.post("/posts/preview", data={"caption": "x", "channel_id": "1"})
    assert calls == ["111"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_preview.py -v`  
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

- `preview.js`: listen to caption + file input changes; render Telegram-ish bubble (avatar circle, name “Preview”, caption text, thumbnail grid).
- Route `POST /posts/preview` using `get_settings().preview_chat_id`; if unset, show error “Set PREVIEW_CHAT_ID”.
- Button “Send preview to me” on post form.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_preview.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/static/preview.js app/templates/post_form.html app/routers/post_routes.py tests/test_preview.py
git commit -m "feat: add in-browser and Telegram DM post preview"
```

---

### Task 10: README and end-to-end smoke wiring

**Files:**
- Create: `README.md`
- Modify: `app/main.py` (ensure all routers mounted, static mounted, lifespan complete)
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: full app
- Produces: documented run steps matching spec

- [ ] **Step 1: Write the failing test**

```python
# tests/test_smoke.py
def test_app_starts_and_login_page(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert b"password" in r.content.lower()
```

- [ ] **Step 2: Run test (may already pass — if so, proceed)**

Run: `pytest tests/test_smoke.py -v`

- [ ] **Step 3: Write README**

Include: BotFather setup, add bot as channel admin, `/start` for DM preview, copy `.env.example` → `.env`, `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`, `uvicorn app.main:app --reload`, open `http://127.0.0.1:8000`.

- [ ] **Step 4: Run full suite**

Run: `pytest -v`  
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add README.md app/main.py tests/test_smoke.py
git commit -m "docs: add README and verify app smoke wiring"
```

---

## Spec coverage checklist

| Spec requirement | Task |
|---|---|
| Login / session auth / bootstrap admin | 3 |
| Channels CRUD + delete guard | 4 |
| One-shot posts, per-post datetime | 6, 7 |
| Multi media / albums / max 10 | 5, 6 |
| Edit pending/failed | 6, 8 |
| Cancel / Retry | 6 |
| Scheduler 30s + soft lock + startup reset | 7 |
| In-browser preview | 9 |
| DM preview to PREVIEW_CHAT_ID | 9 |
| Config env vars | 1 |
| README / run instructions | 10 |

## Execution handoff

Plan complete after save. Prefer **Subagent-driven** execution: many tasks with strict interfaces (auth → channels → telegram → posts → scheduler → UI); independent review per task reduces silent contract drift.
