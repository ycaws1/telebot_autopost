# Telebot — Scheduled Telegram Channel Poster

Personal web app that queues one-shot multimedia posts to Telegram channels on a schedule. Posts are sent by a **Telegram bot**.

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Add the bot as an **admin** of each target channel (permission to post).
3. Message the bot `/start` so DM previews work.
4. Copy env and fill in values:

```bash
cp .env.example .env
```

Required:

| Variable | Meaning |
|---|---|
| `BOT_TOKEN` | BotFather token |
| `SECRET_KEY` | Session cookie secret |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | First login (created on startup) |
| `PREVIEW_CHAT_ID` | Your Telegram user id (for “Send preview to me”) |
| `TIMEZONE` | e.g. `Asia/Singapore` |

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000), log in, add channels, schedule posts.

## Features

- One-shot queue with per-post datetime
- Text, photo, video, and albums (up to 10 files)
- Edit pending/failed posts; cancel and retry
- In-browser Telegram-style preview + real DM preview
- SQLite persistence; scheduler recovers after restart

## Tests

```bash
pytest -v
```
