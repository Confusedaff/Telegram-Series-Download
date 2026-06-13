#!/usr/bin/env python3
"""
Diagnostic step 2: send a query, find the result button(s), CLICK the
first one, and watch ALL incoming messages (from the bot AND from
anywhere else, e.g. the bot's PM / "Saved Messages" / a file-store bot)
for ~15s afterwards.

This tells us:
  - Does clicking the button cause THIS message to be edited with media?
  - Does the bot send a NEW message in this same chat with the file?
  - Does the file arrive via a DIFFERENT chat (e.g. bot opens a PM,
    or forwards from a private file-store channel)?
  - What does the callback ANSWER (if any) say?

Usage:
    python inspect_click.py "Psych 2006 S02E01"
"""

import asyncio
import os
import sys
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import (
    MessageMediaDocument,
    DocumentAttributeFilename,
    KeyboardButtonCallback,
)

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")
SEARCH_BOT = os.getenv("SEARCH_BOT")

QUERY = sys.argv[1] if len(sys.argv) > 1 else "Psych 2006 S02E01"


def dump_msg(tag, msg):
    print("=" * 70)
    print(f"{tag}  chat_id={msg.chat_id}  id={msg.id}  date={msg.date}")
    try:
        sender = msg.sender
        sname = getattr(sender, "username", None) or getattr(sender, "first_name", None)
    except Exception:
        sname = "?"
    print(f"  from           : {sname}")
    print(f"  raw_text       : {msg.raw_text!r}")
    print(f"  msg.media type : {type(msg.media).__name__}")
    is_doc = isinstance(msg.media, MessageMediaDocument)
    print(f"  is doc?        : {is_doc}")
    if is_doc:
        doc = msg.media.document
        print(f"    doc.size     : {doc.size}")
        print(f"    doc.mime_type: {doc.mime_type}")
        for attr in doc.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                print(f"    filename     : {attr.file_name}")
    if msg.buttons:
        print(f"  buttons        : {len(msg.buttons)} row(s)")
        for r, row in enumerate(msg.buttons):
            for c, btn in enumerate(row):
                raw = getattr(btn, "button", btn)
                cls = type(raw).__name__
                print(f"    [{r}][{c}] class={cls} text={getattr(raw,'text',None)!r} "
                      f"url={getattr(raw,'url',None)!r} data={getattr(raw,'data',None)!r}")
    print()


async def main():
    client = TelegramClient("ep_dl_session", API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print(f"Signed in as {me.first_name} (@{me.username})\n")

    # Watch ALL incoming messages from ANY chat, so we catch the file
    # even if it arrives somewhere unexpected (PM, saved messages, etc.)
    @client.on(events.NewMessage(incoming=True))
    async def any_msg(event):
        dump_msg("INCOMING (any chat)", event.message)

    # Watch edits to the original message too
    @client.on(events.MessageEdited())
    async def any_edit(event):
        dump_msg("EDITED MESSAGE", event.message)

    print(f"Sending query: {QUERY!r}\n")
    sent = await client.send_message(SEARCH_BOT, QUERY)

    # Wait for the results message to arrive
    print("Waiting up to 10s for results message...\n")
    result_msg = None
    for _ in range(20):
        await asyncio.sleep(0.5)
        async for m in client.iter_messages(SEARCH_BOT, limit=1):
            if m.id != sent.id and m.buttons:
                result_msg = m
                break
        if result_msg:
            break

    if not result_msg:
        print("No results message with buttons found within 10s.")
        await client.disconnect()
        return

    dump_msg("RESULTS MESSAGE", result_msg)

    # Find first KeyboardButtonCallback
    target_btn = None
    for row in result_msg.buttons:
        for btn in row:
            raw = getattr(btn, "button", btn)
            if isinstance(raw, KeyboardButtonCallback):
                target_btn = btn
                break
        if target_btn:
            break

    if not target_btn:
        print("No callback button found.")
        await client.disconnect()
        return

    print(f"Clicking button: {getattr(target_btn,'text',None)!r}\n")
    try:
        answer = await target_btn.click()
        print(f"Callback answer object: {answer}\n")
        if answer is not None:
            print(f"  answer.message : {getattr(answer, 'message', None)!r}")
            print(f"  answer.alert   : {getattr(answer, 'alert', None)!r}")
            print(f"  answer.url     : {getattr(answer, 'url', None)!r}\n")
    except Exception as e:
        print(f"Click raised exception: {e!r}\n")

    print("Now watching for 15 seconds for any incoming messages / edits...\n")
    await asyncio.sleep(15)

    print("Done. Re-fetching the results message to check for edits...\n")
    refreshed = await client.get_messages(SEARCH_BOT, ids=result_msg.id)
    if refreshed:
        dump_msg("RESULTS MESSAGE (after click, refetched)", refreshed)

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())