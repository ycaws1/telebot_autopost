# Telebot — Scheduled Telegram Channel Poster

Personal web app that queues one-shot multimedia posts to Telegram channels on a schedule.

- **Preview / Setup:** Telegram **bot**
- **Scheduled publish:** bot sends to your preview DM (no `[Preview]` prefix), then your **user account** forwards into the channel

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Create an API app at [my.telegram.org](https://my.telegram.org) → copy `api_id` / `api_hash`.
3. Copy env and fill in values:

```bash
cp .env.example .env
```

Required:

| Variable | Meaning |
|---|---|
| `BOT_TOKEN` | BotFather token (Setup + DM preview) |
| `SECRET_KEY` | Session cookie secret |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | First login (created on startup) |
| `TIMEZONE` | e.g. `Asia/Singapore` |

Optional:

| Variable | Meaning |
|---|---|
| `PREVIEW_CHAT_ID` | Bootstrap preview DM id (overridden once you save via Setup) |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | Optional bootstrap; prefer **Setup → User account** on the web |
| `TELEGRAM_SESSION` | Optional bootstrap session; prefer web login on Setup |
| `TELEGRAM_UPDATES_ENABLED` | `1` (default) to run the setup poller; `0` in tests |

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000), log in, then open **Setup**.

### Self-setup wizard (`/setup`)

You do not need to hand-copy chat ids:

1. Open **Setup** — **User account**: paste API id/hash from my.telegram.org, then phone + login code (+ 2FA if asked).
2. Pair the bot (`/start CODE`), save preview chat, then add channels (lookup or post-discovery).
3. Use Dashboard / New post when the checklist is green.

CLI alternative for the user session: `python -m scripts.telegram_login`.

The app long-polls Telegram `getUpdates` in-process (single uvicorn worker). Preview chat, API credentials, and user session live in SQLite `app_settings` and take precedence over `.env` (logout clears the session even if `TELEGRAM_SESSION` is still set in env).

## Features

- Guided Telegram pairing for preview DM + channel discovery
- Scheduled posts: bot → preview DM, user forwards to channel, then staging DM is deleted
- One-shot queue with per-post datetime
- Text, photo, video, and albums (up to 10 files)
- Edit pending/failed posts; cancel and retry
- In-browser Telegram-style preview + real DM preview
- SQLite persistence; scheduler recovers after restart

Your Telegram user must be allowed to post in the target channel (usually admin). Treat `TELEGRAM_SESSION` like a password.

## Tests

```bash
pytest -v
```
