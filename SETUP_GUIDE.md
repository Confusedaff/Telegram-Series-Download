# 🎬 Episode Downloader — Setup Guide

---

## What you need before starting

| Requirement | How to check |
|---|---|
| Python 3.9 or higher | Open terminal → `python --version` |
| A Telegram account | Any account works, including your personal one |
| The script file | `episode_downloader.py` (already downloaded) |

---

## Step 1 — Install Python (skip if you have it)

**Windows:**
Download from https://www.python.org/downloads/ → run the installer →
**tick "Add Python to PATH"** before clicking Install.

**Mac:**
```bash
brew install python
```
Or download from https://www.python.org/downloads/

**Linux (Ubuntu/Debian):**
```bash
sudo apt install python3 python3-pip
```

---

## Step 2 — Install Telethon

Open your terminal (Command Prompt on Windows, Terminal on Mac/Linux) and run:

```bash
pip install telethon
```

That's the only library needed. It handles everything — logging in, talking to bots, downloading files.

---

## Step 3 — Get your Telegram API credentials

This is the most important step. You need two values: `api_id` (a number) and `api_hash` (a long string).

1. Go to **https://my.telegram.org** in your browser
2. Log in with your phone number and the OTP Telegram sends you
3. Click **"API development tools"**
4. Fill in the form:
   - **App title:** anything (e.g. `MyDownloader`)
   - **Short name:** anything lowercase (e.g. `mydownloader`)
   - **Platform:** Other
   - **Description:** leave blank
5. Click **"Create application"**
6. You'll see your `App api_id` (a number like `12345678`) and `App api_hash` (a long hex string)

> ⚠️ Keep these private. Don't share them or post them online.

---

## Step 4 — Find the search bot's username

In Telegram, open the search bot you found the series in.
The username is the `@name` shown at the top (e.g. `@MoviezBot`).

> **Tip:** Send the bot a test message manually first (e.g. `Dark S02E01`) to confirm
> it responds with a file and to see whether it shows quality buttons.

---

## Step 5 — Configure the script

Open `episode_downloader.py` in any text editor (Notepad, VS Code, etc.)
and find the **CONFIGURATION** block near the top. Edit these four lines:

```python
API_ID   = 12345678           # ← paste your api_id number here
API_HASH = "abcdef1234..."    # ← paste your api_hash string here (keep the quotes)

SEARCH_BOT = "@MoviezBot"     # ← the bot's @username (keep the quotes)

QUERY_TEMPLATE = "{series} S{season:02d}E{episode:02d}"   # ← usually fine as-is
```

### Matching the query format to your bot

Send the bot a manual message and watch what format it expects.
Then adjust `QUERY_TEMPLATE`:

| If the bot expects | Set QUERY_TEMPLATE to |
|---|---|
| `Dark S02E03` | `"{series} S{season:02d}E{episode:02d}"` (default) |
| `Dark Season 2 Episode 3` | `"{series} Season {season} Episode {episode}"` |
| `/search Dark S02E03` | `"/search {series} S{season:02d}E{episode:02d}"` |

---

## Step 6 — Run the script

In your terminal, navigate to the folder containing the script, then run:

```bash
python episode_downloader.py
```

### First run only — logging in

Telethon will ask:
```
Please enter your phone (or bot token): +91XXXXXXXXXX
Please enter the code you received: 12345
```

Enter your phone number with country code, then the OTP Telegram sends you.
This creates a `ep_dl_session.session` file in the same folder.
**You only do this once** — after that it stays logged in automatically.

---

## Step 7 — Download a series

After login, you'll see the prompt:

```
Enter series (e.g. darkS02):
```

### Input formats

| You type | What happens |
|---|---|
| `darkS02` | Downloads all of Season 2 (auto-detects episode count) |
| `dark S2` | Same as above |
| `Breaking Bad S03` | All of Breaking Bad Season 3 |
| `dark S02E01-08` | Episodes 1 through 8 of Season 2 |
| `dark S02E05` | Only episode 5 |

### Example session

```
Enter series (e.g. darkS02): dark s2

  Series  : Dark
  Season  : 2
  Episodes: 1 → AUTO-DETECT

  Start download? [Y/n]: y

════════════════════════════════════════════════════
  🎬  Dark
  📅  Season 2
  🔢  Episodes: 1 → AUTO-DETECT
  🎯  Quality: auto (highest available)
════════════════════════════════════════════════════

  📺  Dark  S02E01
  ↗  Query: «Dark S02E01»
  Bot: Searching…
  🎯  Quality buttons found — picking: [1080p]
  ⬇  Saving → Dark.S02E01.1080p.mkv
  [████████████████████] 100%  842.3/842.3 MB  Dark.S02E01.1080p.mkv
  ✓  Saved

  ⏳  Waiting 10s …

  📺  Dark  S02E02
  ...
```

---

## Where files are saved

Downloads are organised automatically:

```
downloads/
└── Dark/
    └── Season_02/
        ├── Dark.S02E01.1080p.mkv
        ├── Dark.S02E02.1080p.mkv
        └── Dark.S02E03.1080p.mkv
```

The `downloads/` folder is created in the same directory as the script.

---

## Common issues

### "No file received" for an episode
- The bot might not have that episode. The script will skip it and move on.
- Re-run the same input after finishing — it skips already-downloaded files
  and retries only the ones that failed.

### The bot shows quality buttons but quality is wrong
- Open `episode_downloader.py` and look for the comment:
  ```
  🎯  Quality buttons found — picking: [1080p]
  ```
- If it's picking the wrong quality, update the keyword list in `QUALITY_TIERS`
  to match your bot's exact button labels.

### Flood wait error (`FloodWaitError: X seconds`)
- Telegram is rate-limiting you. Increase `DELAY_BETWEEN_EPISODES` from `10`
  to `30` or more. The script will automatically wait if this happens.

### The script stops at episode 1 or 2 (auto-detect too aggressive)
- The bot might be slow to respond. Increase `RESPONSE_TIMEOUT` from `120` to `180`.
- Or increase `MAX_CONSECUTIVE_FAILS` from `2` to `3`.

### "Please fill in API_ID" error
- You haven't edited the configuration block yet. Re-read Step 5.

---

## Tips

- You can run it for multiple seasons back to back — after one download finishes,
  it asks "Download another?" Just type the next one.
- It's safe to cancel mid-download (`Ctrl+C`) and restart — already-downloaded
  episodes are skipped automatically.
- The session file (`ep_dl_session.session`) keeps you logged in. Don't delete it.
