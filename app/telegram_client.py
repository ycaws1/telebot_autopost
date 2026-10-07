from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

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
) -> list[int]:
    """Send a post; return Telegram message_id(s)."""
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
            body = await _post_json(
                client, f"{base}/sendMessage", {"chat_id": chat_id, "text": text}
            )
            return _message_ids(body)

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
                body = await _post_multipart(client, f"{base}/{method}", data, files)
            return _message_ids(body)

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
            body = await _post_multipart(
                client,
                f"{base}/sendMediaGroup",
                {"chat_id": chat_id, "media": json.dumps(media_payload)},
                files,
            )
        finally:
            for _, fh in files.values():
                fh.close()
        return _message_ids(body)
    finally:
        if owns_client and client is not None:
            await client.aclose()


async def forward_messages(
    to_chat_id: str,
    from_chat_id: str,
    message_ids: list[int],
    *,
    bot_token: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    if not message_ids:
        raise TelegramError("No messages to forward")
    token = bot_token if bot_token is not None else get_settings().bot_token
    if not token:
        raise TelegramError("BOT_TOKEN is not configured")
    base = f"https://api.telegram.org/bot{token}"
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=60.0)
    try:
        # Prefer batch when multiple (albums); fall back to one-by-one.
        if len(message_ids) > 1:
            try:
                await _post_json(
                    client,
                    f"{base}/forwardMessages",
                    {
                        "chat_id": to_chat_id,
                        "from_chat_id": from_chat_id,
                        "message_ids": json.dumps(message_ids),
                    },
                )
                return
            except TelegramError:
                pass
        for mid in message_ids:
            await _post_json(
                client,
                f"{base}/forwardMessage",
                {
                    "chat_id": to_chat_id,
                    "from_chat_id": from_chat_id,
                    "message_id": mid,
                },
            )
    finally:
        if owns_client and client is not None:
            await client.aclose()


async def delete_messages(
    chat_id: str,
    message_ids: list[int],
    *,
    bot_token: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    if not message_ids:
        return
    token = bot_token if bot_token is not None else get_settings().bot_token
    if not token:
        return
    base = f"https://api.telegram.org/bot{token}"
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=30.0)
    try:
        for mid in message_ids:
            try:
                await _post_json(
                    client,
                    f"{base}/deleteMessage",
                    {"chat_id": chat_id, "message_id": mid},
                )
            except TelegramError:
                # Staging cleanup is best-effort
                pass
    finally:
        if owns_client and client is not None:
            await client.aclose()


async def publish_post(
    channel_chat_id: str,
    caption: str | None,
    media: list[MediaItem],
    *,
    staging_chat_id: str,
    bot_token: str | None = None,
    client: httpx.AsyncClient | None = None,
    cleanup_staging: bool = True,
) -> None:
    """Send to staging (self/preview DM), then forward into the channel."""
    staging = (staging_chat_id or "").strip()
    if not staging:
        raise TelegramError(
            "Preview chat is not set — open Setup and save your preview DM first"
        )
    dest = (channel_chat_id or "").strip()
    if not dest:
        raise TelegramError("Channel chat id is empty")

    owns_client = client is None
    token = bot_token if bot_token is not None else get_settings().bot_token
    if owns_client:
        client = httpx.AsyncClient(timeout=60.0)
    try:
        ids = await send_post(
            staging, caption, media, bot_token=token, client=client
        )
        await forward_messages(
            dest, staging, ids, bot_token=token, client=client
        )
        if cleanup_staging:
            await delete_messages(staging, ids, bot_token=token, client=client)
    finally:
        if owns_client and client is not None:
            await client.aclose()


def _message_ids(body: dict[str, Any]) -> list[int]:
    result = body.get("result")
    if isinstance(result, list):
        ids = [int(m["message_id"]) for m in result if m.get("message_id") is not None]
        if not ids:
            raise TelegramError("Telegram send returned no message ids")
        return ids
    if isinstance(result, dict) and result.get("message_id") is not None:
        return [int(result["message_id"])]
    raise TelegramError("Telegram send returned no message id")


async def _post_json(client, url: str, data: dict) -> dict[str, Any]:
    resp = await client.post(url, data=data)
    return _raise_if_bad(resp)


async def _post_multipart(client, url: str, data: dict, files: dict) -> dict[str, Any]:
    resp = await client.post(url, data=data, files=files)
    return _raise_if_bad(resp)


def _raise_if_bad(resp) -> dict[str, Any]:
    body = None
    try:
        body = resp.json()
    except Exception:
        body = None
    if isinstance(body, dict) and body.get("ok") is False:
        raise TelegramError(body.get("description") or "Telegram API error")
    status = getattr(resp, "status_code", None)
    if status is not None and status >= 400:
        detail = ""
        if isinstance(body, dict):
            detail = body.get("description") or ""
        raise TelegramError(detail or f"Telegram HTTP {status}")
    if not isinstance(body, dict):
        return {"ok": True, "result": {"message_id": 0}}
    return body
