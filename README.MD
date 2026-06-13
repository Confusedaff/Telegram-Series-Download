# 📺 Telegram Episode Downloader

A command-line tool built on [Telethon](https://docs.telethon.dev/) that automates searching a Telegram "file/episode" bot for an entire TV season — episode by episode — and triggers the bot to send each matching file straight into your chat.

> **How it actually works:** The script doesn't download video files to disk. It automates the *search and request* steps. The bot delivers each file as a Telegram message, and you download from there using the normal Telegram app.

---

## Features

- Searches a configured Telegram bot for every episode in a season, one query per episode
- Supports a single episode, a range, or a full season with **auto-detection**
- Optional release-year support to disambiguate shows with common names (`psych 2006 S02`)
- Follows pagination ("Next" buttons) so no result page is missed
- Clicks every result button so the bot delivers files directly into your chat
- Detects "join this channel first" gates and **auto-joins** the required channels
- All credentials and behavior configured via a `.env` file — no code edits needed

---

## How It Works

1. Logs into your Telegram account via Telethon *(interactive on first run only)*
2. Sends `/start` to the configured bot and auto-joins any required channels
3. Prompts you for a series and season to search
4. For each episode in the requested range, sends a search query built from `QUERY_TEMPLATE`
5. Collects all result buttons across pages and clicks each one, prompting the bot to post the file
6. Prints a running log and a final summary of files delivered vs. missed

**Auto-detection:** If no end episode is given, the script searches increasing episode numbers up to a 60-episode cap, stopping when two consecutive episodes return nothing.

---

## Requirements

- Python 3.10+
- A Telegram account
- API credentials (`api_id` / `api_hash`) from [my.telegram.org](https://my.telegram.org)
- The username of a bot that returns file results for search queries

### Python Dependencies

```
telethon
python-dotenv
```

---

## Installation

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install telethon python-dotenv
```

---

## Configuration

Create a `.env` file in the same directory as `episode_downloader.py`:

```env
# Required
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_api_hash_here
SEARCH_BOT=@SomeEpisodeSearchBot

# Optional — defaults shown
QUERY_TEMPLATE={series} S{season:02d}E{episode:02d}
DOWNLOAD_DIR=./downloads
RESPONSE_TIMEOUT=60
DELAY_BETWEEN_EPISODES=8
```

To get your `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`: log in at [my.telegram.org](https://my.telegram.org), open **API development tools**, and create an application (any name/description is fine).

### Variable Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_API_ID` | ✅ Yes | — | Numeric API ID from my.telegram.org |
| `TELEGRAM_API_HASH` | ✅ Yes | — | API hash from my.telegram.org |
| `SEARCH_BOT` | ✅ Yes | — | Username of the bot to query, e.g. `@SomeBot` |
| `QUERY_TEMPLATE` | No | `{series} S{season:02d}E{episode:02d}` | Format string for each per-episode search |
| `DOWNLOAD_DIR` | No | `./downloads` | Created on startup; not currently used to save files |
| `RESPONSE_TIMEOUT` | No | `60` | Seconds to wait for the bot's reply before giving up |
| `DELAY_BETWEEN_EPISODES` | No | `8` | Seconds to pause between episode searches |

---

## Usage

```bash
python episode_downloader.py
```

On first run, Telethon will prompt for your phone number and login code, then save a session file (`ep_dl_session.session`) so future runs skip the login step.

You'll see a help banner, then:

```
Enter series (e.g. psych 2006 S02):
```

### Input Formats

| Input | Meaning |
|---|---|
| `dark S02` | "Dark", season 2, auto-detect all episodes |
| `psych 2006 S02` | "Psych", year 2006, season 2, auto-detect |
| `Breaking Bad S03E01-08` | "Breaking Bad", season 3, episodes 1–8 |
| `dark S02E05` | "Dark", season 2, episode 5 only |

After parsing, the script confirms what it understood before searching:

```
  Series  : Dark
  Season  : 2
  Episodes: 1 → AUTO-DETECT

  Search? [Y/n]:
```

Type `quit`, `q`, or `exit` at the first prompt to exit without searching.

---

## Where Files End Up

For each matching result, the script clicks the bot's button — the bot then posts the file as a message in your Telegram chat with it. Open Telegram afterward and download each file from that chat as usual.

### Run Summary Example

```
──────────────────────────────────────────────────────────
  ✅  8 file(s) sent to this chat — open Telegram and download them there.
  ⚠️  1 episode(s)/result(s) had no file.
──────────────────────────────────────────────────────────
```

---

## Limitations & Notes

- **Files are delivered to Telegram, not saved locally** — `DOWNLOAD_DIR` is created on startup but unused for output.
- **Keep `ep_dl_session.session` private** — it holds your authenticated Telegram session.
- **Bot-specific behavior** — result parsing and pagination handling assume a specific bot "protocol" (callback-button results, `[size] [tag] name` labels, "Next" buttons). A bot with a different format may not work correctly.
- **Quality selection is not active** — the `quality_score` / `best_quality_button` helpers are defined but unused; every returned result is requested, not just the highest-quality one.

---

## Troubleshooting

| Symptom | Likely Fix |
|---|---|
| `Missing required value in .env: ...` | `.env` is missing, misnamed, or in the wrong directory |
| Times out waiting for results | Increase `RESPONSE_TIMEOUT`, or the bot may be slow/rate-limiting |
| "Nothing found" for every episode | Check `SEARCH_BOT` and that `QUERY_TEMPLATE` matches what the bot expects |
| Asked to log in again every run | Make sure `ep_dl_session.session` isn't being deleted between runs |

---

## Disclaimer

You are responsible for ensuring your use of this script — and of any bot you configure it to query — complies with [Telegram's Terms of Service](https://telegram.org/tos), the rules of that bot/channel, and applicable copyright law.