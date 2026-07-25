# Migaku Queue From Anki — Design

**Date:** 2026-07-26
**Status:** Approved (pending spec review)
**Working directory:** `/Users/distiled/Dev/migaku/`

## Goal

A single script that, when run, takes the daily new-card count from the Anki deck "Main deck", picks that many new Japanese words from `JLPT.json` (skipping any already in the deck), and puts them into the Migaku dictionary's queue by driving the Migaku Chrome extension with Playwright. The dictionary window is left open with the queue populated.

## Inputs

- **Anki deck "Main deck"** (queried live via AnkiConnect on `localhost:8765`).
  - Deck config field `new.perDay` = `X` (today: 17). This is the number of words to queue.
  - Notes in this deck use the Migaku note type with fields `Vocabulary-Kanji` and `Vocabulary-Kana`. Both fields are pulled for every note in the deck to build the "already known" set.
- **`/Users/distiled/Study materials/Japanese/JLPT.json`** — a flat JSON array of `[word, reading]` pairs. Level boundaries are marked by `["N5","N5"]`, `["N4","N4"]`, `["N3","N3"]`, `["N2","N2"]`, `["N1","N1"]` rows. Some levels have padding `["",""]` rows that must be skipped. Total ~8000 entries, split ~700 N5, ~650 N4, ~1700 N3, ~1850 N2, ~3200 N1.
- **Migaku Chrome extension** installed at `~/Library/Application Support/Google/Chrome/Default/Extensions/lkhiljgmbeecmljiogckofcalncmfnfo/1.30.8.0_0/`. Its dictionary app lives at `chrome-extension://lkhiljgmbeecmljiogckofcalncmfnfo/pages/app-window/index.html#/app/dictionary`.

## Outputs

- The Migaku dictionary window open in Chrome with `X` new words added to its card-creation queue.
- Stdout summary: `X`, the list of words added, and any candidates skipped with reasons.

## Algorithm

1. **Get X from Anki.** `POST localhost:8765` with action `getDeckConfig`, deck `"Main deck"` → `X = result.new.perDay`.
2. **Build "already known" set.** `findNotes` with query `deck:"Main deck"` → note IDs. `notesInfo` (batched, 500 at a time) → for each note, collect `Vocabulary-Kanji` (stripped of HTML) and `Vocabulary-Kana` (stripped of HTML). `known_set = { surface, reading }`.
3. **Read JLPT.json.** Parse the JSON array. Iterate in order. Skip:
   - Level marker rows `["N5","N5"]` … `["N1","N1"]` (they're not words).
   - Empty rows `["",""]` (padding inside levels).
   - Any row whose `word` or `reading` is in `known_set` (the matching rule you picked: match on surface or reading).
4. **Collect X candidates.** Continue iterating; the first X rows that survive the skips go into `candidates`. If we exhaust JLPT.json before reaching X, take what we have and warn.
5. **Drive Migaku dictionary via Playwright:**
   - Launch a persistent Chromium context at `~/Library/Application Support/Migaku-Automation/chrome-profile` with `--load-extension=$EXT_PATH` and `--disable-extensions-except=$EXT_PATH`.
   - Open `chrome-extension://…/pages/app-window/index.html#/app/dictionary`.
   - Detect login state. If the page shows a login screen, pause and prompt the user to log in, then press Enter in the terminal. Session is persisted across runs by the persistent profile.
   - For each candidate word:
     - Clear the dictionary search input. Type the candidate's surface form. Wait for the results panel to update.
     - Find the "add to queue" button (selector pinned during implementation; see "Open questions"). Click it. Wait for the queue badge counter to increment, or for a visible "added" confirmation.
     - On any failure (no results, button not found, counter not incremented), log a warning with the word and reason, and pull the next surviving candidate from JLPT.json so the final queue still has X words (if available).
   - Leave the dictionary window open at the end.

## Components and data flow

```
┌─ AnkiConnect (8765) ──┐    ┌─ JLPT.json ─┐
│  getDeckConfig        │    │  N5/N4/...   │
│  findNotes + notesInfo│    └──────┬──────┘
└──────────┬────────────┘           │
           ▼                        ▼
   known_set {surface,reading}   candidates_in_order
                       │  diff (skip known)  │
                       ▼                     ▼
                       first X candidates → Playwright
                                              │
                                              ▼
                          chrome-extension://…/dictionary
                          (search each word, click "add to queue")
                                              │
                                              ▼
                          dictionary left open, queue has X words
```

## File layout

```
/Users/distiled/Dev/migaku/
├── migaku_queue.py          # the script (one file, ~250 lines)
├── requirements.txt         # playwright, requests
├── README.md                # how to use, one-time setup steps
├── docs/superpowers/specs/  # this design doc lives here
└── .gitignore               # ignore chrome-profile/, __pycache__/, .venv/
```

One file is enough — the logic is linear. No modules.

## CLI

```
python3 migaku_queue.py                 # run with defaults
python3 migaku_queue.py --dry-run        # print X candidates, don't touch Chrome
python3 migaku_queue.py --count 5        # override X (default: from Anki deck config)
python3 migaku_queue.py --no-leave-open  # close Chrome after adding
python3 migaku_queue.py --extension-path /path/to/ext   # override detected path
python3 migaku_queue.py --headless       # headless mode (default: headful, so first-run login and the final open window work)
```

Flags use `argparse`. Bare command does the right thing.

## One-time setup (documented in README)

1. `python3 -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. `python3 -m playwright install chromium`
4. First run: script opens Chrome with the Migaku extension loaded. User logs into their Migaku account **once** in the opened window. Session is persisted in `~/Library/Application Support/Migaku-Automation/chrome-profile/`.
5. Subsequent runs: session reused, no login needed.

Anki must be open with the Migaku Anki add-on installed (for the extension to talk to — though this script doesn't need the add-on itself, just the dictionary UI).

## Error handling

- **AnkiConnect not responding on :8765** → exit with: "Is Anki open? AnkiConnect not responding on :8765."
- **"Main deck" not found** → list available decks from `deckNames`, exit.
- **JLPT.json missing or unparseable** → exit with the path and the parse error.
- **Migaku extension path missing** → exit with the expected path; suggest `--extension-path` override.
- **Fewer than X candidates available in JLPT.json** (user is near the end) → queue what's available, warn loudly.
- **Migaku dictionary search returns no results** for a candidate → log warning with the word, skip, take next candidate.
- **"Add to queue" button not found** → take a screenshot to `~/Dev/migaku/screenshots/<timestamp>_<word>.png`, log warning, skip, take next candidate. After 3 consecutive selector failures, abort and tell the user to inspect the page (extension UI may have changed).
- **Not logged in to Migaku** (first run, or session expired) → pause, print "Please log in to Migaku in the opened window, then press Enter here", continue after Enter.

## Testing

- **Unit-testable (pure functions, `pytest`):**
  - `parse_jlpt_json(path) -> List[(level, word, reading)]` — correctly handles level markers, empty rows, ordering.
  - `is_known(word, reading, known_set) -> bool` — matching rule.
  - `select_candidates(jlpt_entries, known_set, x) -> List[(word, reading)]` — sequential selection, skip-known, fills X.
- **Integration (not unit-tested, verified manually):**
  - AnkiConnect queries — verified by `--dry-run` printing the actual `X` and `known_set` size.
  - Playwright flow — verified by watching a real `--headful` run.

## Things deliberately left out (YAGNI)

- No frequency list / sorting by frequency (sequential by JLPT level).
- No Anki card creation (using the Migaku queue flow, not bypassing it).
- No multi-language support (Japanese only — JLPT.json is JP-specific).
- No daemon/scheduler — run the script when you want your daily words queued.
- No file-based logging beyond stdout.

## Open questions (to resolve during implementation)

1. **"Add to queue" button selector.** Discovered during implementation by inspecting the running dictionary page (Playwright `page.locator(...)` against likely candidates, fall back to dumping the DOM). Pinned in the script as a constant. If Migaku updates the UI, this selector breaks — that's a known fragility, mitigated by the 3-strike abort with screenshots.
2. **Loading the Migaku extension as unpacked** might trigger an Early Access / license warning in the extension itself. If that happens, the README will document a fallback using the user's real Chrome profile via `--remote-debugging-port=9222` (CDP approach). This is a troubleshooting step, not the default flow.
3. **Whether the dictionary search input takes the surface form or the reading.** Default: surface form. If a word returns no results, retry once with the reading before giving up on that candidate.

## Tech choices

- **Python 3** — AnkiConnect HTTP and JSON parsing are trivial in either Python or Node; Playwright's Python bindings are stable; you have Python 3 installed. Single-language project, no Node needed.
- **Playwright (not Selenium, not raw CDP)** — first-class support for loading extensions, persistent contexts, and auto-waiting. Less brittle than CDP for this UI-driving task.
- **`requests` for AnkiConnect** — synchronous, simple, no async needed for a handful of HTTP calls.
- **`pytest`** for unit tests of the pure functions.

## Non-goals

- Replacing Migaku's review or card-creation flow.
- Syncing state back into Anki.
- Bulk-importing hundreds of words at once — this is a "top up the daily queue" tool.
- Working with any deck other than "Main deck" (parameterizable later if needed, but not now).
