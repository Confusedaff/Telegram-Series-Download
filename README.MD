# Telegram Episode Downloader

A command-line tool built on [Telethon](https://docs.telethon.dev/) that automates searching a Telegram "file/episode" bot for an entire TV season, episode by episode, and triggers the bot to send each matching file straight into your chat with it.

> **Note on the name:** despite "downloader" in the name, the script doesn't write video files to disk itself. It automates the *search and request* steps — the bot delivers each file as a message in your Telegram chat, and you download it from there using your normal Telegram app.

## Screenshots

<!-- Replace with a screenshot of the help banner / startup output -->
![Startup banner](<img width="1776" height="684" alt="Image" src="https://github.com/user-attachments/assets/a33b3410-4bf2-4643-8d4f-d8811a014761" />)

## Features

- Searches a configured Telegram bot for every episode in a season, one query per episode.
- Optional release-year support for disambiguating shows with common names (`psych 2006 S02`).
- Supports a single episode, an episode range, or a full season with auto-detection.
- Follows pagination ("Next" buttons) so no result page is missed.
- Clicks every result button so the bot delivers the file(s) into your chat.
- Detects "join this channel first" gates on the bot and joins the required channels automatically.
- All credentials and behavior tuned via a `.env` file — no code edits needed.

## How It Works

1. Logs into your Telegram account via Telethon (interactive on first run only).
2. Sends `/start` to the configured bot and auto-joins any required channels.
3. Prompts you for a series/season to search.
4. For each episode number in the requested range, sends a search query built from `QUERY_TEMPLATE`.
5. Collects all result buttons (across pagination) and clicks each one, prompting the bot to post the matching file into the chat.
6. Prints a running log and a final summary of how many files were delivered vs. missed.

If no end episode is given, the script keeps searching increasing episode numbers — up to a 60-episode cap — until two episodes in a row return nothing, then assumes the season is complete.

## Requirements

- Python 3.10+
- A Telegram account
- API credentials (`api_id` / `api_hash`) from https://my.telegram.org
- The username of a bot that returns file results for search queries

### Dependencies

```
telethon
python-dotenv
```

## Installation

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install telethon python-dotenv
```

## Configuration

Create a `.env` file alongside `episode_downloader.py`:

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

To get `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`: log in at https://my.telegram.org, open **API development tools**, and create an application — any name/description is fine.

|
 Variable 
|
 Required 
|
 Default 
|
 Description 
|

|
---
|
---
|
---
|
---
|

|
 
`TELEGRAM_API_ID`
 
|
 Yes 
|
 — 
|
 Numeric API ID from my.telegram.org 
|

|
 
`TELEGRAM_API_HASH`
 
|
 Yes 
|
 — 
|
 API hash from my.telegram.org 
|

|
 
`SEARCH_BOT`
 
|
 Yes 
|
 — 
|
 Username of the bot to query, e.g. 
`@SomeBot`
 
|

|
 
`QUERY_TEMPLATE`
 
|
 No 
|
 
`{series} S{season:02d}E{episode:02d}`
 
|
 Format string for each per-episode search 
|

|
 
`DOWNLOAD_DIR`
 
|
 No 
|
 
`./downloads`
 
|
 Created on startup; not currently used to save files (see Limitations) 
|

|
 
`RESPONSE_TIMEOUT`
 
|
 No 
|
 
`60`
 
|
 Seconds to wait for the bot's reply before giving up 
|

|
 
`DELAY_BETWEEN_EPISODES`
 
|
 No 
|
 
`8`
 
|
 Seconds to pause between episode searches 
|


## Usage

```bash
python episode_downloader.py
```

On first run, Telethon will ask for your phone number and login code, then save a session file (`ep_dl_session.session`) so future runs don't require logging in again.

<!-- Replace with a screenshot of the channel auto-join log output -->
![Channel auto-join log](<img width="1794" height="64" alt="Image" src="https://github.com/user-attachments/assets/571fc5a5-06df-467e-ae2b-6302ef281cec" />)

You'll then see a help banner followed by:

```
Enter series (e.g. psych 2006 S02): 
```

### Input formats

|
 Input 
|
 Meaning 
|

|
---
|
---
|

|
 
`dark S02`
 
|
 "Dark", season 2, auto-detect all episodes 
|

|
 
`psych 2006 S02`
 
|
 "Psych", year 2006, season 2, auto-detect 
|

|
 
`Breaking Bad S03E01-08`
 
|
 "Breaking Bad", season 3, episodes 1–8 
|

|
 
`dark S02E05`
 
|
 "Dark", season 2, episode 5 only 
|


After parsing, the script confirms what it understood before searching:

```
  Series  : Dark
  Season  : 2
  Episodes: 1 → AUTO-DETECT

  Search? [Y/n]: 
```

<!-- Replace with a screenshot of the input prompt and confirmation -->
![Input prompt and confirmation](<img width="1312" height="266" alt="Image" src="https://github.com/user-attachments/assets/f1cc3a0a-c328-4e77-bee9-225fd059c0ac" />)

Type `quit`, `q`, or `exit` at the first prompt to exit without searching.

## Where the Files End Up

For each matching result, the script clicks the bot's button — the bot then posts the file as a message in your chat with it.

<!-- Replace with a screenshot of the bot delivering files in Telegram -->
![Bot delivering files in Telegram](<img width="1148" height="914" alt="Image" src="https://github.com/user-attachments/assets/143ab076-00c5-4d40-8c98-a1da26a2f9c9" />)

Open Telegram afterward and download each file from that chat as usual.

## Run Summary Example

```
──────────────────────────────────────────────────────────
  ✅  8 file(s) sent to this chat — open Telegram and download them there.
  ⚠️  1 episode(s)/result(s) had no file.
──────────────────────────────────────────────────────────
```

<!-- Replace with a screenshot of the final summary in the terminal -->
![Run summary](<img width="1410" height="210" alt="Image" src="https://github.com/user-attachments/assets/f67ac3b7-168b-466f-86bd-71f74188654d" />)

## Limitations & Notes

- Files are delivered to your Telegram chat, not saved locally — `DOWNLOAD_DIR` is created but unused for output.
- `ep_dl_session.session` holds your authenticated Telegram session; keep it private.
- Result formats and pagination handling assume a specific bot "protocol" (callback-button results, `[size] [tag] name` labels, "Next" buttons). A bot with a different format may not work correctly.
- The `quality_score` / `best_quality_button` and progress-bar helpers are defined but not currently used by the main flow — every returned result is requested, not just the highest-quality one.

## Troubleshooting

|
 Symptom 
|
 Likely fix 
|

|
---
|
---
|

|
 
`Missing required value in .env: ...`
 
|
 
`.env`
 is missing, misnamed, or in the wrong directory 
|

|
 Times out waiting for results 
|
 Increase 
`RESPONSE_TIMEOUT`
, or the bot may be slow/rate-limiting 
|

|
 "Nothing found" for every episode 
|
 Check 
`SEARCH_BOT`
 and that 
`QUERY_TEMPLATE`
 matches what the bot expects 
|

|
 Asked to log in again every run 
|
 Make sure 
`ep_dl_session.session`
 isn't being deleted between runs 
|


## Disclaimer

You're responsible for ensuring your use of this script, and of any bot you configure it to query, complies with Telegram's Terms of Service, the rules of that bot/channel, and applicable copyright law.
