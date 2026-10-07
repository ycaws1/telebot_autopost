# Telebot — Scheduled Telegram Channel Poster

Personal web app that queues one-shot multimedia posts to Telegram channels on a schedule. Posts are sent by a **Telegram bot**.

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Copy env and fill in values:

```bash
cp .env.example .env
```

Required:

| Variable | Meaning |
|---|---|
| `BOT_TOKEN` | BotFather token |
| `SECRET_KEY` | Session cookie secret |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | First login (created on startup) |
| `TIMEZONE` | e.g. `Asia/Singapore` |

Optional:

| Variable | Meaning |
|---|---|
| `PREVIEW_CHAT_ID` | Bootstrap preview DM id (overridden once you save via Setup) |
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

1. Open **Setup** — copy the deep link or send `/start CODE` to the bot.
2. Tap **Use as my preview DM** in Telegram, then **Save preview chat** on the web (optional **Send test DM**).
3. Add the bot as a channel **admin**, post any message in the channel, tap **Add as posting channel** in the bot DM, then **Add channel** on the web.
4. Use Dashboard / New post when the checklist is green.

The app long-polls Telegram `getUpdates` in-process (single uvicorn worker). Saved preview chat id lives in SQLite `app_settings` and takes precedence over `.env`.

## Features

- Guided Telegram pairing for preview DM + channel discovery
- One-shot queue with per-post datetime
- Text, photo, video, and albums (up to 10 files)
- Edit pending/failed posts; cancel and retry
- In-browser Telegram-style preview + real DM preview
- SQLite persistence; scheduler recovers after restart

## Tests

```bash
pytest -v
```
