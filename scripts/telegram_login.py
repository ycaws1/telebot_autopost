"""Interactive login to create a Telethon string session for user-account publishing.

Usage (local machine with phone access):

  python -m scripts.telegram_login

Requires TELEGRAM_API_ID and TELEGRAM_API_HASH in .env (from https://my.telegram.org).
Prints TELEGRAM_SESSION=... to paste into .env / Render env.
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv


async def main() -> None:
    load_dotenv()
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        print("Install telethon: pip install telethon", file=sys.stderr)
        sys.exit(1)

    api_id = os.environ.get("TELEGRAM_API_ID", "").strip()
    api_hash = os.environ.get("TELEGRAM_API_HASH", "").strip()
    if not api_id or not api_hash:
        print(
            "Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env "
            "(create an app at https://my.telegram.org).",
            file=sys.stderr,
        )
        sys.exit(1)

    phone = os.environ.get("TELEGRAM_PHONE", "").strip() or None
    client = TelegramClient(StringSession(), int(api_id), api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        phone = phone or input("Phone (+countrycode…): ").strip()
        await client.send_code_request(phone)
        code = input("Code from Telegram: ").strip()
        try:
            await client.sign_in(phone, code)
        except Exception:
            pw = input("2FA password (if enabled): ").strip()
            await client.sign_in(password=pw)

    me = await client.get_me()
    session = client.session.save()
    await client.disconnect()
    print()
    print(f"Logged in as {me.first_name} (id={me.id})")
    print()
    print("Add this to your .env / host environment:")
    print(f"TELEGRAM_SESSION={session}")


if __name__ == "__main__":
    asyncio.run(main())
