# migaku-queue

Top up the Migaku dictionary Card Creator queue with new Japanese words from `JLPT.json`, skipping words already in your Anki "Main deck". Drives the Migaku Chrome extension with Playwright.

## What it does

1. Reads the daily new-card count (`new.perDay`) from your Anki "Main deck" via AnkiConnect. This is `X` (default: 17).
2. Pulls every word currently in the deck (surface + reading) into an in-memory set.
3. Walks `JLPT.json` in order (N5 → N4 → N3 → N2 → N1), skipping words already in the deck.
4. Takes the first `X` survivors.
5. Launches Chrome with the Migaku extension loaded, opens the dictionary, searches each word, clicks "Send to Card Creator". The first word opens in the Card Creator form; the rest go to the "Queued" list. The dictionary window is left open.

## One-time setup

```bash
cd /Users/distiled/Dev/migaku
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
```

Anki must be open with AnkiConnect enabled (default port 8765). The "Main deck" and the Migaku Anki add-on should be installed.

## First run

The script opens Chrome with the Migaku extension loaded. **Log in to your Migaku account in the Chrome window when prompted** — the script auto-continues once login completes. The session is saved to `~/Library/Application Support/Migaku-Automation/chrome-profile/` so subsequent runs won't ask you to log in again.

```bash
.venv/bin/python migaku_queue.py
```

## Usage

```bash
# Default: read X from Anki deck config, queue X words, leave Chrome open
.venv/bin/python migaku_queue.py

# Print the candidates without touching Chrome
.venv/bin/python migaku_queue.py --dry-run

# Override X (e.g. queue 5 instead of 17)
.venv/bin/python migaku_queue.py --count 5

# Close Chrome after adding instead of leaving it open
.venv/bin/python migaku_queue.py --no-leave-open

# Use a different Anki deck
.venv/bin/python migaku_queue.py --deck "Other deck"

# Override the JLPT.json path
.venv/bin/python migaku_queue.py --jlpt-path /path/to/other.json

# Override the Migaku extension path (auto-detected by default)
.venv/bin/python migaku_queue.py --extension-path /path/to/extension-folder
```

## Flags

| Flag | Default | Purpose |
| --- | --- | --- |
| `--deck` | `Main deck` | Anki deck to read X and known words from |
| `--count` | (from Anki) | Override X |
| `--jlpt-path` | `~/Study materials/Japanese/JLPT.json` | Path to JLPT.json |
| `--extension-path` | (auto-detected) | Migaku extension folder |
| `--profile-dir` | `~/Library/Application Support/Migaku-Automation/chrome-profile` | Chrome persistent profile |
| `--dry-run` | off | Print candidates, don't touch Chrome |
| `--no-leave-open` | off | Close Chrome after adding |
| `--headless` | off | Run Chrome headless (extensions may not load — see Troubleshooting) |

## How the Migaku Card Creator queue works

When the script sends a word to the Card Creator:
- The **first** word opens in the Card Creator form (the "current item" being edited)
- **Subsequent** words go to the "Queued" list (waiting their turn)
- After all words are sent: 1 word is in the form + (X-1) words are queued

To process the queue: click "CREATE CARD" in the Card Creator form for each word. This sends the card to Anki and loads the next queued word.

## Troubleshooting

### "Migaku extension not found at ..."

The script looks for the extension at `~/Library/Application Support/Google/Chrome/Default/Extensions/lkhiljgmbeecmljiogckofcalncmfnfo/`. If you installed Migaku in a different Chrome profile or it's missing, pass `--extension-path /path/to/extension/version-folder`.

### "Three consecutive failures — extension UI may have changed"

The selectors are pinned in `migaku_queue.py` as constants (`DICTIONARY_SEARCH_INPUT`, `SEND_TO_CARD_CREATOR_BUTTON`, `QUEUE_COUNTER_BUTTON`). If Migaku updates their UI, these selectors may break. Check the screenshots saved to `./screenshots/` to find the new selectors and update the constants.

### "AnkiConnect not reachable at http://localhost:8765"

Open Anki. AnkiConnect only works while Anki is running.

### Login prompt every run

The persistent profile at `~/Library/Application Support/Migaku-Automation/chrome-profile/` stores your session. If you deleted it, or if Migaku's session expired, you'll be prompted to log in again. Just log in in the Chrome window and the script will auto-continue.

### Headless mode doesn't load the extension

Chrome historically disabled extensions in headless mode. If `--headless` launches but the extension page is blank, run without `--headless` (the default). Headless mode is not the primary flow.

### Google OAuth "browser not secure" error

If you try to log in with Google and get "This browser or app may not be secure", use a different login method (email/password) instead. Playwright's bundled Chromium is detected as an automation browser by Google OAuth.

## Running the tests

```bash
.venv/bin/pytest -q
```

Unit tests cover the pure functions (JLPT parsing, HTML stripping, known-set building, candidate selection, CLI parsing, AnkiConnect client with mocked HTTP). The Playwright integration is verified manually.

## Files

- `migaku_queue.py` — the script
- `requirements.txt` — runtime deps (`requests`, `playwright`)
- `requirements-dev.txt` — adds `pytest`
- `tests/` — unit tests and fixtures
- `docs/superpowers/specs/` — design spec
- `docs/superpowers/plans/` — implementation plan
