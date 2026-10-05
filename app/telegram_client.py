from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

from app.config import get_settings


class TelegramError(Exception):
    pass


@dataclass
class MediaItem:
    media_type: Literal["photo", "video"]
    path: Path


async def send_post(
    chat_id: str,
    caption: str | None,
    media: list[MediaItem],
    *,
    bot_token: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    if len(media) > 10:
        raise TelegramError("Telegram albums allow at most 10 media files")

    token = bot_token if bot_token is not None else get_settings().bot_token
    if not token:
        raise TelegramError("BOT_TOKEN is not configured")

    base = f"https://api.telegram.org/bot{token}"
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=60.0)

    try:
        if not media:
            text = (caption or "").strip()
            if not text:
                raise TelegramError("caption is required for text-only posts")
            await _post_json(client, f"{base}/sendMessage", {"chat_id": chat_id, "text": text})
            return

        for item in media:
            if not Path(item.path).is_file():
                raise TelegramError(f"Missing media file: {item.path}")

        if len(media) == 1:
            item = media[0]
            field = "photo" if item.media_type == "photo" else "video"
            method = "sendPhoto" if item.media_type == "photo" else "sendVideo"
            data = {"chat_id": chat_id}
            if caption:
                data["caption"] = caption
            with open(item.path, "rb") as fh:
                files = {field: (Path(item.path).name, fh)}
                await _post_multipart(client, f"{base}/{method}", data, files)
            return

        # Album
        media_payload = []
        files = {}
        for idx, item in enumerate(media):
            attach_name = f"file{idx}"
            entry: dict = {
                "type": "photo" if item.media_type == "photo" else "video",
                "media": f"attach://{attach_name}",
            }
            if idx == 0 and caption:
                entry["caption"] = caption
            media_payload.append(entry)
            files[attach_name] = (Path(item.path).name, open(item.path, "rb"))

        try:
            await _post_multipart(
                client,
                f"{base}/sendMediaGroup",
                {"chat_id": chat_id, "media": json.dumps(media_payload)},
                files,
            )
        finally:
            for _, fh in files.values():
                fh.close()
    finally:
        if owns_client and client is not None:
            await client.aclose()


async def _post_json(client, url: str, data: dict) -> None:
    resp = await client.post(url, data=data)
    _raise_if_bad(resp)


async def _post_multipart(client, url: str, data: dict, files: dict) -> None:
    resp = await client.post(url, data=data, files=files)
    _raise_if_bad(resp)


def _raise_if_bad(resp) -> None:
    try:
        resp.raise_for_status()
    except Exception as exc:
        raise TelegramError(str(exc)) from exc
    try:
        body = resp.json()
    except Exception:
        return
    if isinstance(body, dict) and body.get("ok") is False:
        raise TelegramError(body.get("description") or "Telegram API error")
