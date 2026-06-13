#!/usr/bin/env python3
"""
╔════════════════════════════════════════════════════╗
║     🎬  Telegram Episode Auto-Downloader v3        ║
║                                                    ║
║  • Year support   →  psych 2006 S02                ║
║  • Browse mode    →  lists all results, you pick   ║
║  • Paginates NEXT →  collects all pages            ║
║  • Auto quality   →  picks highest on download     ║
║  • Channel gate   →  auto-joins required channels  ║
╚════════════════════════════════════════════════════╝
"""

import asyncio
import logging
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, events, functions, types
from telethon.tl.types import (
    MessageMediaDocument,
    DocumentAttributeFilename,
    KeyboardButtonUrl,
)

# ═══════════════════════════════════════════════════════════════════
#  ⚙️  CONFIGURATION  — values loaded from .env
# ═══════════════════════════════════════════════════════════════════

load_dotenv()

def _require(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        print(f"❌  Missing required value in .env: {key}")
        print(f"    Open .env and add:  {key}=your_value_here")
        sys.exit(1)
    return val

API_ID   = int(_require("TELEGRAM_API_ID"))
API_HASH = _require("TELEGRAM_API_HASH")
SEARCH_BOT = _require("SEARCH_BOT")

QUERY_TEMPLATE         = os.getenv("QUERY_TEMPLATE",             "{series} S{season:02d}E{episode:02d}")
DOWNLOAD_DIR           = Path(os.getenv("DOWNLOAD_DIR",          "./downloads"))
RESPONSE_TIMEOUT       = int(os.getenv("RESPONSE_TIMEOUT",       "60"))
DELAY_BETWEEN_EPISODES = int(os.getenv("DELAY_BETWEEN_EPISODES", "8"))
MAX_CONSECUTIVE_FAILS  = 2
MAX_EPISODES_CAP       = 60

# ═══════════════════════════════════════════════════════════════════

logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger("EpDL")

# ─── Quality ranking ─────────────────────────────────────────────

QUALITY_TIERS = [
    (["2160p", "2160", "4k", "uhd"],                100),
    (["1080p", "1080", "fhd", "full hd", "fullhd"],  80),
    (["720p",  "720",  "hd"],                         60),
    (["480p",  "480"],                                40),
    (["360p",  "360"],                                20),
    (["240p",  "240"],                                10),
]

def quality_score(text: str) -> int:
    t = text.lower()
    for keywords, score in QUALITY_TIERS:
        if any(k in t for k in keywords):
            return score
    return 1

def best_quality_button(buttons):
    best_btn, best_score = None, -1
    for row in buttons:
        for btn in row:
            label = getattr(btn, "text", "") or ""
            s = quality_score(label)
            if s > best_score:
                best_score, best_btn = s, btn
    return best_btn or buttons[0][0]

# ─── Input parser (now with optional year) ───────────────────────

# Matches:  <series> [year] S<season> [E<from>[-<to>]]
# Examples: dark S02 / psych 2006 S02 / Breaking Bad S03E01-05
INPUT_PATTERN = re.compile(
    r'^(.+?)'                           # series name (lazy)
    r'(?:\s+(\d{4}))?'                  # optional year  e.g. 2006
    r'\s*[Ss](\d{1,2})'                # S<season>
    r'(?:[Ee](\d{1,3})'                # optional E<from>
    r'(?:\s*[-–]\s*(\d{1,3}))?)?'      # optional -<to>
    r'\s*$'
)

def parse_input(raw: str) -> dict | None:
    raw = raw.strip().replace("_", " ")
    m = INPUT_PATTERN.match(raw)
    if not m:
        return None

    series  = m.group(1).strip().title()
    year    = m.group(2)                        # may be None
    season  = int(m.group(3))
    from_ep = int(m.group(4)) if m.group(4) else 1
    if m.group(5):
        to_ep = int(m.group(5))
    elif m.group(4):
        to_ep = from_ep
    else:
        to_ep = None

    # Build the search term sent to the bot
    search_term = f"{series} {year}" if year else series

    return dict(
        series=series,
        year=year,
        search_term=search_term,
        season=season,
        from_ep=from_ep,
        to_ep=to_ep,
    )

# ─── Progress bar ────────────────────────────────────────────────

def make_progress(label: str):
    last = [-1]
    def cb(recv: int, total: int):
        if not total:
            return
        pct = int(recv / total * 100)
        if pct == last[0]:
            return
        last[0] = pct
        filled = pct // 5
        bar = "█" * filled + "░" * (20 - filled)
        mb_r, mb_t = recv / 1_048_576, total / 1_048_576
        print(f"\r  [{bar}] {pct:3d}%  {mb_r:5.1f}/{mb_t:.1f} MB  {label}",
              end="", flush=True)
        if pct == 100:
            print()
    return cb

# ─── Main class ──────────────────────────────────────────────────

class EpisodeDownloader:

    def __init__(self):
        self.client = TelegramClient("ep_dl_session", API_ID, API_HASH)
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # ── Auth ──────────────────────────────────────────────────────

    async def start(self):
        await self.client.start()
        me = await self.client.get_me()
        log.info(f"✅  Signed in as: {me.first_name} (@{me.username})")
        await self._auto_join_required_channels()

    async def stop(self):
        await self.client.disconnect()

    # ── Auto-join any channel the bot requires ────────────────────

    async def _auto_join_required_channels(self):
        """
        Many bots send a 'Join our channel first' gate message with a
        URL button pointing to their Telegram channel.  This method
        sends /start to the bot, watches for such buttons, and joins
        those channels automatically so the bot unlocks for us.
        """
        log.info("🔓  Checking for required channel memberships …")

        joined     = []
        gate_done  = asyncio.Event()

        @self.client.on(events.NewMessage(from_users=SEARCH_BOT))
        async def gate_handler(event):
            msg = event.message
            if not msg.buttons:
                gate_done.set()
                return

            found_url = False
            for row in msg.buttons:
                for btn in row:
                    # URL buttons have a .url attribute; inline callback buttons don't
                    raw_btn = btn.button if hasattr(btn, "button") else btn
                    url = getattr(raw_btn, "url", None)
                    if url and "t.me/" in url:
                        # Extract the channel username from the URL
                        # handles  https://t.me/SomeChannel  and  https://t.me/joinchat/xxx
                        slug = url.rstrip("/").split("/")[-1]
                        if slug.startswith("+") or "joinchat" in url:
                            # Private invite link — join via the hash
                            invite_hash = slug.lstrip("+")
                            try:
                                await self.client(
                                    functions.messages.ImportChatInviteRequest(invite_hash)
                                )
                                joined.append(url)
                                log.info(f"  ✅  Joined (invite): {url}")
                            except Exception as e:
                                log.warning(f"  ⚠️  Could not join {url}: {e}")
                        else:
                            # Public channel — join by username
                            try:
                                await self.client(
                                    functions.channels.JoinChannelRequest(slug)
                                )
                                joined.append(slug)
                                log.info(f"  ✅  Joined channel: @{slug}")
                            except Exception as e:
                                log.warning(f"  ⚠️  Could not join @{slug}: {e}")
                        found_url = True

            gate_done.set()

        try:
            await self.client.send_message(SEARCH_BOT, "/start")
            await asyncio.wait_for(gate_done.wait(), timeout=10)
        except asyncio.TimeoutError:
            pass
        finally:
            self.client.remove_event_handler(gate_handler)

        if joined:
            log.info(f"  Joined {len(joined)} channel(s). Bot should now be unlocked.")
            await asyncio.sleep(2)   # give Telegram a moment to register membership
        else:
            log.info("  No channel gate detected — bot is already accessible.")

    # ── Browse: collect all result messages for a query ───────────

    async def browse_bot(self, query: str) -> list:
        """
        Send *query*, then collect ALL result messages the bot sends
        (including across NEXT pagination buttons).

        Returns a flat list of Telethon Message objects that carry
        a document (i.e. actual downloadable files).
        """
        results    = []       # list of Message objects with documents
        text_msgs  = []       # text/status messages (for display)
        done       = asyncio.Event()
        paginating = [False]

        @self.client.on(events.NewMessage(from_users=SEARCH_BOT))
        async def collect_handler(event):
            msg = event.message

            # ── Got a file result ──
            if msg.media and isinstance(msg.media, MessageMediaDocument):
                results.append(msg)
                return

            # ── Got a text message (status or search results list) ──
            if msg.text:
                text_msgs.append(msg.text)

            # ── Check buttons: NEXT pagination or end-of-results ──
            if msg.buttons:
                next_btn = None
                for row in msg.buttons:
                    for btn in row:
                        label = (getattr(btn, "text", "") or "").upper()
                        if "NEXT" in label or "➡" in label or "→" in label:
                            next_btn = btn
                            break
                    if next_btn:
                        break

                if next_btn:
                    # More pages — click NEXT and keep collecting
                    paginating[0] = True
                    log.info(f"  📄  Loading next page …")
                    await asyncio.sleep(1)
                    await next_btn.click()
                    return
                else:
                    # Buttons exist but no NEXT → this is the last page
                    done.set()
            else:
                # No buttons at all → end of results
                if not paginating[0]:
                    # Small delay in case more messages are still incoming
                    await asyncio.sleep(2)
                    done.set()

        try:
            await self.client.send_message(SEARCH_BOT, query)
            log.info(f"  ↗  Query sent: «{query}»")
            await asyncio.wait_for(done.wait(), timeout=RESPONSE_TIMEOUT)
        except asyncio.TimeoutError:
            if not results:
                log.warning(f"  ⏱  Timed out — no results received")
        finally:
            self.client.remove_event_handler(collect_handler)

        # If the bot sent text results (filenames listed as text, not files),
        # log them so the user can see what the bot said
        for t in text_msgs:
            snippet = t[:200].replace("\n", " | ")
            log.info(f"  Bot said: {snippet}")

        return results

    # ── Show results and let user pick ───────────────────────────

    def _filename_from_msg(self, msg) -> str:
        """Extract the best display name from a message."""
        if msg.media and isinstance(msg.media, MessageMediaDocument):
            for attr in msg.media.document.attributes:
                if isinstance(attr, DocumentAttributeFilename):
                    return attr.file_name
            # Fallback: use file size
            size_mb = msg.media.document.size / 1_048_576
            return f"[unnamed file — {size_mb:.0f} MB]"
        return "[unknown]"

    def _filesize_from_msg(self, msg) -> str:
        try:
            size = msg.media.document.size
            if size >= 1_073_741_824:
                return f"{size/1_073_741_824:.2f} GB"
            return f"{size/1_048_576:.0f} MB"
        except Exception:
            return "?"

    async def select_and_download(
        self,
        search_term : str,
        series      : str,
        season      : int,
        from_ep     : int,
        to_ep,              # None = auto
    ):
        """
        Browse mode: query episode by episode, show numbered results,
        let user choose which to download.
        """
        auto  = to_ep is None
        limit = MAX_EPISODES_CAP if auto else (to_ep - from_ep + 1)

        print(f"\n{'═'*58}")
        print(f"  🎬  {series}  {'('+str(auto) and 'AUTO' or ''}")
        print(f"  📅  Season {season}  ·  Episodes {from_ep} → {'AUTO' if auto else to_ep}")
        print(f"{'═'*58}\n")

        all_results  = []   # (episode_number, message)
        consec_fails = 0

        for ep in range(from_ep, from_ep + limit):
            ep_str = f"S{season:02d}E{episode:02d}" if False else f"S{season:02d}E{ep:02d}"
            query  = QUERY_TEMPLATE.format(
                series=search_term, season=season, episode=ep
            )
            print(f"  🔍  Searching {ep_str} …")
            msgs = await self.browse_bot(query)

            if msgs:
                consec_fails = 0
                for m in msgs:
                    all_results.append((ep, m))
            else:
                consec_fails += 1
                print(f"  ✗  Nothing found for {ep_str}")
                if auto and consec_fails >= MAX_CONSECUTIVE_FAILS:
                    print(f"\n  🏁  {MAX_CONSECUTIVE_FAILS} consecutive misses — "
                          f"assuming season is complete.\n")
                    break

            if ep < from_ep + limit - 1:
                await asyncio.sleep(DELAY_BETWEEN_EPISODES)

        if not all_results:
            print("\n  ❌  No results found at all. Check the series name / bot username.\n")
            return

        # ── Display the numbered list ──────────────────────────────
        print(f"\n{'─'*58}")
        print(f"  📋  Found {len(all_results)} file(s):\n")
        for i, (ep, msg) in enumerate(all_results, 1):
            fname = self._filename_from_msg(msg)
            fsize = self._filesize_from_msg(msg)
            ep_str = f"S{season:02d}E{ep:02d}"
            print(f"  [{i:>2}]  {ep_str}  {fname}  ({fsize})")
        print(f"{'─'*58}")

        # ── Ask user which to download ─────────────────────────────
        print()
        print("  Enter numbers to download (e.g.  1 2 3  or  1-5  or  all):")
        try:
            choice = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            return

        selected = self._parse_selection(choice, len(all_results))
        if not selected:
            print("  Nothing selected.")
            return

        # ── Download chosen files ──────────────────────────────────
        print(f"\n  ⬇  Downloading {len(selected)} file(s) …\n")
        for idx in selected:
            ep, msg = all_results[idx - 1]
            await self._download_msg(msg, series, season, ep)
            if idx != selected[-1]:
                await asyncio.sleep(3)

        print(f"\n  ✅  Done. Files saved to: {DOWNLOAD_DIR.resolve()}\n")

    def _parse_selection(self, raw: str, max_n: int) -> list[int]:
        """Parse '1 2 3', '1-5', 'all' into a sorted list of 1-based indices."""
        raw = raw.strip().lower()
        if raw in ("all", "a", "*"):
            return list(range(1, max_n + 1))

        indices = set()
        # match ranges like 2-5 and plain numbers
        for token in re.split(r"[\s,]+", raw):
            range_m = re.match(r"^(\d+)-(\d+)$", token)
            if range_m:
                a, b = int(range_m.group(1)), int(range_m.group(2))
                indices.update(range(a, b + 1))
            elif token.isdigit():
                indices.add(int(token))

        valid = sorted(i for i in indices if 1 <= i <= max_n)
        invalid = sorted(i for i in indices if not (1 <= i <= max_n))
        if invalid:
            print(f"  ⚠️  Ignored out-of-range: {invalid}")
        return valid

    async def _download_msg(self, msg, series: str, season: int, episode: int):
        ep_str   = f"S{season:02d}E{episode:02d}"
        filename = self._filename_from_msg(msg)

        safe_name = series.replace(" ", "_").replace("/", "-")
        out_dir   = DOWNLOAD_DIR / safe_name / f"Season_{season:02d}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path  = out_dir / filename

        if out_path.exists():
            print(f"  ⏭  {ep_str} already exists — skipping")
            return

        print(f"  ⬇  {ep_str}  →  {filename}")
        await self.client.download_media(
            msg,
            file=str(out_path),
            progress_callback=make_progress(filename),
        )
        print(f"  ✓  Saved: {out_path}")


# ─── CLI ─────────────────────────────────────────────────────────

HELP = """
╔══════════════════════════════════════════════════════════╗
║         🎬  Telegram Episode Downloader v3               ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  Input formats:                                          ║
║    dark S02                 Season 2 (auto-detect)       ║
║    psych 2006 S02           With year                    ║
║    Breaking Bad S03E01-08   Episodes 1-8                 ║
║    dark S02E05              Single episode               ║
║                                                          ║
║  Flow:                                                   ║
║    1. Script searches the bot episode by episode         ║
║    2. Shows you a numbered list of ALL results found     ║
║    3. You pick which ones to download                    ║
║    4. Downloads your selection in order                  ║
║                                                          ║
║  Type  quit  to exit                                     ║
╚══════════════════════════════════════════════════════════╝
"""

async def run_cli(dl: EpisodeDownloader):
    print(HELP)
    while True:
        try:
            raw = input("  Enter series (e.g. psych 2006 S02): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue
        if raw.lower() in ("q", "quit", "exit"):
            break

        parsed = parse_input(raw)
        if not parsed:
            print(
                "  ⚠️  Couldn't parse that.\n"
                "      Try:  dark S02  or  psych 2006 S02  or  dark S02E01-08\n"
            )
            continue

        print()
        print(f"  Series  : {parsed['search_term']}")
        print(f"  Season  : {parsed['season']}")
        if parsed["to_ep"] is None:
            print(f"  Episodes: {parsed['from_ep']} → AUTO-DETECT")
        elif parsed["from_ep"] == parsed["to_ep"]:
            print(f"  Episode : {parsed['from_ep']} only")
        else:
            print(f"  Episodes: {parsed['from_ep']} → {parsed['to_ep']}")
        print()

        try:
            confirm = input("  Search? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if confirm in ("n", "no"):
            print()
            continue

        await dl.select_and_download(
            search_term = parsed["search_term"],
            series      = parsed["series"],
            season      = parsed["season"],
            from_ep     = parsed["from_ep"],
            to_ep       = parsed["to_ep"],
        )

        try:
            again = input("  Search another? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if again in ("n", "no"):
            break
        print()


# ─── Entry point ─────────────────────────────────────────────────

async def main():
    dl = EpisodeDownloader()
    await dl.start()
    try:
        await run_cli(dl)
    finally:
        await dl.stop()

if __name__ == "__main__":
    asyncio.run(main())
