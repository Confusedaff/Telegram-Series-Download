#!/usr/bin/env python3
"""
╔════════════════════════════════════════════════════╗
║     🎬  Telegram Episode Auto-Downloader v2        ║
║                                                    ║
║  • Shorthand input  →  darkS02                     ║
║  • Downloads in order  →  E01, E02, E03 …          ║
║  • Auto-detects season end                         ║
║  • Auto-picks highest quality from buttons         ║
╚════════════════════════════════════════════════════╝

SETUP (one-time):
  1. Go to https://my.telegram.org → log in → API development tools
     Create an app, copy api_id (number) and api_hash (string).
  2. pip install telethon
  3. Fill in the ⚙️ CONFIGURATION block below.
  4. python episode_downloader.py

First run: Telethon will ask for your phone + Telegram OTP.
After that it saves a session file and never asks again.
"""

import asyncio
import logging
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaDocument, DocumentAttributeFilename

# ═══════════════════════════════════════════════════════════════════
#  ⚙️  CONFIGURATION  — values are loaded from your .env file
#  Never hardcode secrets here; edit .env instead.
# ═══════════════════════════════════════════════════════════════════

load_dotenv()   # reads .env from the same folder as this script

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

# Optional — fall back to sensible defaults if not set in .env
QUERY_TEMPLATE          = os.getenv("QUERY_TEMPLATE",          "{series} S{season:02d}E{episode:02d}")
DOWNLOAD_DIR            = Path(os.getenv("DOWNLOAD_DIR",       "./downloads"))
RESPONSE_TIMEOUT        = int(os.getenv("RESPONSE_TIMEOUT",    "120"))
DELAY_BETWEEN_EPISODES  = int(os.getenv("DELAY_BETWEEN_EPISODES", "10"))

# Auto-detect mode: stop after this many consecutive episodes fail
# (e.g. 2 means "if ep 11 and ep 12 both fail, assume season only has 10 eps")
MAX_CONSECUTIVE_FAILS = 2

# Hard cap on episodes per season in auto-detect mode
MAX_EPISODES_CAP = 60

# ═══════════════════════════════════════════════════════════════════


# ─── Logging setup ──────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger("EpDL")


# ─── Quality ranking (highest score = best) ──────────────────────────────────

QUALITY_TIERS = [
    (["2160p", "2160", "4k", "uhd"],                 100),
    (["1080p", "1080", "fhd", "full hd", "fullhd"],   80),
    (["720p",  "720",  "hd"],                          60),
    (["480p",  "480"],                                 40),
    (["360p",  "360"],                                 20),
    (["240p",  "240"],                                 10),
]

def quality_score(text: str) -> int:
    t = text.lower()
    for keywords, score in QUALITY_TIERS:
        if any(k in t for k in keywords):
            return score
    return 1  # unknown label → still valid, just low priority

def best_quality_button(buttons):
    """Return the button with the highest quality score from a 2-D button grid."""
    best_btn   = None
    best_score = -1
    for row in buttons:
        for btn in row:
            label = getattr(btn, "text", "") or ""
            s = quality_score(label)
            if s > best_score:
                best_score = s
                best_btn   = btn
    return best_btn or buttons[0][0]   # safe fallback


# ─── Input parser ────────────────────────────────────────────────────────────

INPUT_PATTERN = re.compile(
    r'^(.+?)\s*[Ss](\d{1,2})'          # <series>  S<season>
    r'(?:[Ee](\d{1,3})'                 # optional  E<from>
    r'(?:\s*[-–]\s*(\d{1,3}))?)?$'     # optional  -<to>
)

def parse_input(raw: str) -> dict | None:
    """
    Parse shorthand series+season strings.  Returns a dict or None.

    Accepted formats
    ──────────────────────────────────────────────────────
    darkS02              series=Dark     s=2  ep=1→AUTO
    dark s2              series=Dark     s=2  ep=1→AUTO
    Breaking Bad S03     series=Breaking Bad  s=3  ep=1→AUTO
    dark S02E01-08       series=Dark     s=2  ep=1→8
    dark S02E05          series=Dark     s=2  ep=5 (single)
    """
    m = INPUT_PATTERN.match(raw.strip())
    if not m:
        return None

    series   = m.group(1).strip().title()
    season   = int(m.group(2))
    from_ep  = int(m.group(3)) if m.group(3) else 1
    # to_ep: explicit end, or same as from (single ep), or None (auto-detect whole season)
    if m.group(4):                           # range given:  E01-08
        to_ep = int(m.group(4))
    elif m.group(3):                         # single ep:    E05
        to_ep = from_ep
    else:                                    # whole season: no E at all
        to_ep = None

    return dict(series=series, season=season, from_ep=from_ep, to_ep=to_ep)


# ─── Progress bar ────────────────────────────────────────────────────────────

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
        mb_r = recv  / 1_048_576
        mb_t = total / 1_048_576
        print(
            f"\r  [{bar}] {pct:3d}%  {mb_r:5.1f}/{mb_t:.1f} MB  {label}",
            end="", flush=True,
        )
        if pct == 100:
            print()
    return cb


# ─── Downloader ──────────────────────────────────────────────────────────────

class EpisodeDownloader:

    def __init__(self):
        self.client = TelegramClient("ep_dl_session", API_ID, API_HASH)
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # ── Auth ──────────────────────────────────────────────────────

    async def start(self):
        await self.client.start()
        me = await self.client.get_me()
        log.info(f"✅  Signed in as: {me.first_name} (@{me.username})")

    async def stop(self):
        await self.client.disconnect()

    # ── Single query → file ───────────────────────────────────────

    async def query_bot(self, query: str):
        """
        Send *query* to SEARCH_BOT.  Handles three bot behaviours:

          A) Bot sends a file directly              → download it
          B) Bot sends quality-picker buttons first → click best → wait for file
          C) Bot sends a status text message        → ignore, keep waiting

        Returns the Telethon Message carrying the document, or None on timeout.
        """
        ready   = asyncio.Event()
        result  = [None]
        clicked = [False]       # guard against clicking twice

        @self.client.on(events.NewMessage(from_users=SEARCH_BOT))
        async def handler(event):
            msg = event.message

            # ── A) Got a downloadable file — done ──
            if msg.media and isinstance(msg.media, MessageMediaDocument):
                result[0] = msg
                ready.set()
                return

            # ── B) Got quality-picker buttons ──
            if msg.buttons and not clicked[0]:
                clicked[0] = True
                btn = best_quality_button(msg.buttons)
                log.info(f"  🎯  Quality options found — picking: [{btn.text}]")
                await btn.click()
                return

            # ── C) Status / search text — just log it ──
            if msg.text:
                snippet = msg.text[:130].replace("\n", " ")
                log.info(f"  Bot: {snippet}")

        try:
            await self.client.send_message(SEARCH_BOT, query)
            log.info(f"  ↗  Query: «{query}»")
            await asyncio.wait_for(ready.wait(), timeout=RESPONSE_TIMEOUT)
            return result[0]

        except asyncio.TimeoutError:
            log.warning(f"  ⏱  No file received within {RESPONSE_TIMEOUT}s")
            return None

        finally:
            self.client.remove_event_handler(handler)

    # ── Single episode ────────────────────────────────────────────

    async def download_episode(self, series: str, season: int, episode: int) -> bool:
        ep_str = f"S{season:02d}E{episode:02d}"
        log.info(f"\n{'─'*56}")
        log.info(f"  📺  {series}  {ep_str}")

        query = QUERY_TEMPLATE.format(series=series, season=season, episode=episode)
        msg   = await self.query_bot(query)

        if msg is None:
            log.error(f"  ✗  Failed: {ep_str}")
            return False

        # ── Determine filename ──
        filename = f"{series} {ep_str}.mkv"    # fallback
        if msg.media and isinstance(msg.media, MessageMediaDocument):
            for attr in msg.media.document.attributes:
                if isinstance(attr, DocumentAttributeFilename):
                    filename = attr.file_name
                    break

        # ── Output path: downloads/Series_Name/Season_02/filename ──
        safe_name = series.replace(" ", "_").replace("/", "-")
        out_dir   = DOWNLOAD_DIR / safe_name / f"Season_{season:02d}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path  = out_dir / filename

        if out_path.exists():
            log.info(f"  ⏭  Already downloaded — skipping")
            return True

        log.info(f"  ⬇  Saving → {filename}")
        await self.client.download_media(
            msg,
            file=str(out_path),
            progress_callback=make_progress(filename),
        )
        log.info(f"  ✓  Saved: {out_path}")
        return True

    # ── Full season ───────────────────────────────────────────────

    async def download_season(
        self,
        series  : str,
        season  : int,
        from_ep : int  = 1,
        to_ep           = None,    # None = auto-detect season end
    ):
        auto  = to_ep is None
        limit = MAX_EPISODES_CAP if auto else (to_ep - from_ep + 1)

        log.info(f"\n{'═'*56}")
        log.info(f"  🎬  {series}")
        log.info(f"  📅  Season {season}")
        if auto:
            log.info(f"  🔢  Episodes: {from_ep} → AUTO-DETECT (stops after "
                     f"{MAX_CONSECUTIVE_FAILS} consecutive misses)")
        else:
            log.info(f"  🔢  Episodes: {from_ep} → {to_ep}")
        log.info(f"  🎯  Quality: auto (highest available)")
        log.info(f"  💾  Saving to: {DOWNLOAD_DIR.resolve()}")
        log.info(f"{'═'*56}")

        ok_list   = []
        fail_list = []
        consecutive_fails = 0

        for ep in range(from_ep, from_ep + limit):
            success = await self.download_episode(series, season, ep)

            if success:
                ok_list.append(ep)
                consecutive_fails = 0
            else:
                fail_list.append(ep)
                consecutive_fails += 1

                # Auto-detect: bail out after N consecutive misses
                if auto and consecutive_fails >= MAX_CONSECUTIVE_FAILS:
                    log.info(
                        f"\n  🏁  {MAX_CONSECUTIVE_FAILS} episodes in a row not found "
                        f"— assuming season {season} is complete."
                    )
                    break

            # Pause before next episode (skip delay after last one)
            next_ep = ep + 1
            is_last = next_ep > from_ep + limit - 1 or (
                auto and consecutive_fails >= MAX_CONSECUTIVE_FAILS
            )
            if not is_last:
                log.info(f"  ⏳  Waiting {DELAY_BETWEEN_EPISODES}s …")
                await asyncio.sleep(DELAY_BETWEEN_EPISODES)

        # In auto mode the last N episodes in fail_list are just probes; filter them
        last_ok = max(ok_list, default=from_ep - 1)
        real_fails = [e for e in fail_list if e <= last_ok]

        # ── Summary ──
        log.info(f"\n{'═'*56}")
        log.info(f"  ✅  Downloaded : {len(ok_list)} episode(s)  {ok_list}")
        if real_fails:
            log.info(f"  ❌  Failed      : episodes {real_fails}")
            log.info(f"      Tip: re-run the same input to retry failures.")
        log.info(f"  📁  Output dir  : {DOWNLOAD_DIR.resolve()}")
        log.info(f"{'═'*56}\n")


# ─── CLI ─────────────────────────────────────────────────────────────────────

HELP = """
╔══════════════════════════════════════════════════════╗
║        🎬  Telegram Episode Downloader v2            ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  Accepted input formats:                             ║
║                                                      ║
║    darkS02             whole season 2  (auto-detect) ║
║    dark s2             same                          ║
║    Breaking Bad S03    whole season 3  (auto-detect) ║
║    dark S02E01-08      episodes 1 → 8                ║
║    dark S02E05         single episode 5              ║
║                                                      ║
║  The script:                                         ║
║    • Downloads episodes in order: E01, E02, E03 …   ║
║    • Picks highest available quality automatically   ║
║    • Stops when the bot can't find more episodes     ║
║    • Skips files that already exist on disk          ║
║                                                      ║
║  Type  quit  to exit                                 ║
╚══════════════════════════════════════════════════════╝
"""

async def run_cli(dl: EpisodeDownloader):
    print(HELP)
    while True:
        try:
            raw = input("  Enter series (e.g. darkS02): ").strip()
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
                "  ⚠️  Couldn't parse that input.\n"
                "      Try:  darkS02  or  Breaking Bad S03  or  dark S02E01-08\n"
            )
            continue

        # ── Confirm ──
        print()
        print(f"  Series  : {parsed['series']}")
        print(f"  Season  : {parsed['season']}")
        if parsed["to_ep"] is None:
            print(f"  Episodes: {parsed['from_ep']} → AUTO-DETECT")
        elif parsed["from_ep"] == parsed["to_ep"]:
            print(f"  Episode : {parsed['from_ep']} only")
        else:
            print(f"  Episodes: {parsed['from_ep']} → {parsed['to_ep']}")
        print()

        try:
            confirm = input("  Start download? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if confirm in ("n", "no"):
            print()
            continue

        await dl.download_season(
            series  = parsed["series"],
            season  = parsed["season"],
            from_ep = parsed["from_ep"],
            to_ep   = parsed["to_ep"],
        )

        try:
            again = input("  Download another series/season? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if again in ("n", "no"):
            break
        print()


# ─── Entry point ─────────────────────────────────────────────────────────────

async def main():
    # Credentials are validated at load time by _require() above

    dl = EpisodeDownloader()
    await dl.start()
    try:
        await run_cli(dl)
    finally:
        await dl.stop()


if __name__ == "__main__":
    asyncio.run(main())
