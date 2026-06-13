#!/usr/bin/env python3
"""
Diagnostic: send ONE query to the bot and print the FULL raw structure
of EVERY message it sends back (type, media, buttons, text) for ~8s.

Run this once, paste the output here, and we'll know exactly:
  - Does the "Results for your Search" message have .buttons? What kind?
  - Is the "[1.40 GB] [S02E01] ..." message a MessageMediaDocument,
    or is it plain text with its own .buttons?
  - If it has buttons, what do they say / what type are they
    (URL button vs callback/data button)?

Usage:
    python inspect_bot.py "Psych 2006 S02E01"
"""

import asyncio
import os
import sys
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaDocument, DocumentAttributeFilename

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")
SEARCH_BOT = os.getenv("SEARCH_BOT")

QUERY = sys.argv[1] if len(sys.argv) > 1 else "Psych 2006 S02E01"


def dump_buttons(msg):
    if not msg.buttons:
        print("    buttons: None")
        return
    print(f"    buttons: {len(msg.buttons)} row(s)")
    for r, row in enumerate(msg.buttons):
        for c, btn in enumerate(row):
            raw = getattr(btn, "button", btn)
            cls = type(raw).__name__
            text = getattr(raw, "text", None)
            url = getattr(raw, "url", None)
            data = getattr(raw, "data", None)
            print(f"      [{r}][{c}] class={cls} text={text!r} url={url!r} data={data!r}")


async def main():
    client = TelegramClient("ep_dl_session", API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print(f"Signed in as {me.first_name} (@{me.username})\n")

    @client.on(events.NewMessage(from_users=SEARCH_BOT))
    async def handler(event):
        msg = event.message
        print("=" * 70)
        print(f"NEW MESSAGE  id={msg.id}  date={msg.date}")
        print(f"  raw_text       : {msg.raw_text!r}")
        print(f"  msg.media type : {type(msg.media).__name__}")
        print(f"  is doc?        : {isinstance(msg.media, MessageMediaDocument)}")
        if isinstance(msg.media, MessageMediaDocument):
            doc = msg.media.document
            print(f"    doc.size     : {doc.size}")
            print(f"    doc.mime_type: {doc.mime_type}")
            for attr in doc.attributes:
                if isinstance(attr, DocumentAttributeFilename):
                    print(f"    filename     : {attr.file_name}")
        dump_buttons(msg)
        # also dump entities (markdown links etc live here)
        if msg.entities:
            print(f"  entities       : {msg.entities}")
        print()

    print(f"Sending query: {QUERY!r}\n")
    await client.send_message(SEARCH_BOT, QUERY)

    print("Listening for 10 seconds...\n")
    await asyncio.sleep(10)

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())