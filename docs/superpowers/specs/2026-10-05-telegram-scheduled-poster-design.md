# Telegram Scheduled Channel Poster — Design Spec

**Date:** 2026-10-05  
**Status:** Approved for planning  
**Stack:** Python, FastAPI, SQLite, APScheduler, Telegram Bot API

## Goal

A personal web app that schedules one-shot multimedia posts to selected Telegram channels. Posts are sent by a Telegram bot (not a user account). The operator manages channels and the queue through a browser UI with login.

## Success criteria

- Operator can log in, register channels, and queue posts with caption + multiple photos/videos and a specific datetime.
- At the scheduled time, the bot posts to the chosen channel; the queue item is marked posted (one-shot).
- Pending posts can be edited (channel, time, caption, media).
- New/Edit shows an in-browser Telegram-style live preview; operator can also send a real DM preview to themselves.
- App restart does not lose the queue; due pending posts are picked up again.

## Non-goals (v1)

- Posting as a personal Telegram user account (Client API / Telethon).
- Multi-tenant SaaS, OAuth, or role-based access beyond simple username/password accounts.
- Fancy drag-and-drop gallery builders.
- Automatic media cleanup / retention policies.
- Recurring schedules (interval/cron); only per-post datetimes.

## Architecture

Single FastAPI process:

```
Browser (web UI)
    ↓
FastAPI
  ├── Auth (session cookie, username/password)
  ├── CRUD for channels + scheduled posts
  ├── Media file storage (local disk)
  └── APScheduler → Telegram Bot API
         └── sends due posts (text / photo / video / album)
SQLite (users, channels, posts, post_media, status)
```

### Why this shape

- One process is enough for personal use; SQLite persists the queue across restarts.
- Bot API is the supported path for channel posting; posts appear from the bot.
- In-process APScheduler avoids a second worker for v1.

## Data model

### users

| Field | Notes |
|---|---|
| id | PK |
| username | unique |
| password_hash | bcrypt |
| created_at | |

Bootstrap: on first run, create admin from `ADMIN_USERNAME` / `ADMIN_PASSWORD` if no users exist.

### channels

| Field | Notes |
|---|---|
| id | PK |
| name | human label |
| chat_id | `@username` or numeric Telegram chat id |
| created_at | |

### posts

| Field | Notes |
|---|---|
| id | PK |
| channel_id | FK → channels |
| caption | optional text |
| scheduled_at | timezone-aware datetime |
| status | `pending` \| `posting` \| `posted` \| `failed` \| `cancelled` |
| error | last error message if failed |
| posted_at | when successfully sent |
| created_at | |
| updated_at | |

### post_media

| Field | Notes |
|---|---|
| id | PK |
| post_id | FK → posts |
| media_type | `photo` \| `video` |
| media_path | path under local media storage |
| sort_order | album order |
| created_at | |

### Posting rules

- 0 media files → text-only `sendMessage` (caption required in this case)
- 1 photo → `sendPhoto`; 1 video → `sendVideo` (caption optional)
- 2+ files → `sendMediaGroup` album; caption on the first item; mixed photo/video allowed; max **10** files per post (Telegram album limit)
- One-shot: after success, status is `posted` and the item is not sent again
- Posted and cancelled posts are read-only
- Pending and failed posts are editable
- **Retry** (failed only): clear `error`, set status to `pending`. If `scheduled_at` is already due, the next scheduler tick sends it
- Deleting a channel is blocked while any posts still reference it

## Web UI

Server-rendered HTML + minimal CSS (no heavy SPA framework).

| Page | Behavior |
|---|---|
| Login | username / password |
| Dashboard | upcoming pending + recent posted/failed |
| Channels | list, add (`name` + chat id), delete |
| New post | channel, datetime, caption, multi-file upload |
| Edit post | same form, prefilled; pending/failed only |
| Post detail | status, error; Cancel (pending), Retry (failed), Edit link |

### Preview

1. **In-browser mock** — Telegram-style bubble updates live while editing caption/media (client-side only).
2. **Real DM preview** — “Send preview to me” sends the same payload to `PREVIEW_CHAT_ID` via the bot. Not stored as a queue post; never sent to channels. Operator must `/start` the bot once so DMs work.

## Auth

- Session cookie signed with `SECRET_KEY`
- Passwords hashed with bcrypt
- All app routes except login require an authenticated session
- Multiple users allowed in DB; v1 has no roles (any logged-in user is full admin)

## Config (`.env`)

| Variable | Purpose |
|---|---|
| `BOT_TOKEN` | Telegram bot token from @BotFather |
| `SECRET_KEY` | Session signing secret |
| `TIMEZONE` | e.g. `Asia/Singapore` for schedule display/interpretation |
| `ADMIN_USERNAME` | Bootstrap admin username |
| `ADMIN_PASSWORD` | Bootstrap admin password |
| `PREVIEW_CHAT_ID` | Operator Telegram user id for DM previews |

## Telegram setup (manual, one-time)

1. Create a bot with @BotFather; copy token into `BOT_TOKEN`.
2. Add the bot as admin of each target channel (permission to post messages).
3. Message the bot `/start` so DM preview works.
4. Add each channel in the UI (`@username` or numeric id).

## Scheduler & errors

- APScheduler interval job every **30 seconds**.
- Each tick: select `pending` posts with `scheduled_at <= now`, oldest first.
- Soft lock: set status to `posting` before send to avoid double-send on overlapping ticks; on success → `posted` + `posted_at`; on failure → `failed` + `error`.
- On app startup: any rows stuck in `posting` (crash mid-send) are reset to `pending` so they can be retried safely.
- Missing media file → `failed` with clear error.
- Telegram errors (bot not admin, chat not found, network) → `failed` with API message.
- App restart: pending/failed remain in SQLite; scheduler resumes.

Media files are kept after posting in v1 (history / re-preview); no automatic cleanup.

## Project layout (planned)

```
telebot/
  app/
    main.py           # FastAPI app, lifespan (scheduler start/stop)
    config.py
    db.py
    models.py
    auth.py
    telegram_client.py
    scheduler.py
    routers/          # auth, channels, posts, pages
    templates/
    static/
  media/              # uploaded files (gitignored)
  data/               # SQLite (gitignored)
  tests/
  requirements.txt
  .env.example
  README.md
```

## Run (v1)

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`, log in, add channels, schedule posts.

## Testing focus

- Auth: login required; bad password rejected
- Post CRUD: create/edit pending; cannot edit posted
- Media: text-only, single photo/video, multi-file album payload construction
- Scheduler: due pending becomes posted (Telegram client mocked); failed path stores error
- Soft lock: concurrent tick does not double-send
- Preview DM uses preview chat id, not channel

## Decisions log

| Decision | Choice |
|---|---|
| Queue mode | One-shot (post once, mark used) |
| Schedule | Per-post datetime |
| Management UI | Web UI with username/password |
| Runtime | Local-friendly; single process |
| Language | Python |
| Architecture | FastAPI + SQLite + APScheduler + Bot API |
| Sender identity | Bot (not user account) |
| Media | Multiple files per post (albums) |
| Edit | Pending (and failed) editable |
| Preview | In-browser mock + real Telegram DM |
