#!/usr/bin/env python3
"""Top up the Migaku dictionary queue with new Japanese words from JLPT.json."""

import argparse
import os
import re
import requests
from typing import List, Set, Tuple

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(s: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    no_tags = _TAG_RE.sub("", s)
    return _WS_RE.sub(" ", no_tags).strip()


def parse_jlpt_json(data: list) -> List[Tuple[str, str, str]]:
    """Parse the JLPT.json array into (level, word, reading) tuples.

    Level markers are rows where word == reading and word starts with 'N'.
    Empty rows are ['','']. Both are skipped. The 'level' of each entry is
    the most recent level marker seen.
    """
    entries: List[Tuple[str, str, str]] = []
    current_level = ""
    for row in data:
        word, reading = row[0], row[1]
        if word == "" and reading == "":
            continue
        if word == reading and word.startswith("N"):
            current_level = word
            continue
        entries.append((current_level, word, reading))
    return entries


KNOWN_FIELDS = (
    # Japanese-75658 (default Migaku vocab)
    "Vocabulary-Kanji", "Vocabulary-Kana",
    # Migaku Japanese CUSTOM STYLING
    "Target Word",
    # Lapis
    "Expression", "ExpressionReading",
    # Japanese sentences
    "VocabKanji",
)


def build_known_set(notes_info: list) -> Set[str]:
    """Build a set of all known surfaces and readings from AnkiConnect notesInfo.

    HTML is stripped from each field value. Empty values are skipped.
    """
    known: Set[str] = set()
    for note in notes_info:
        fields = note.get("fields", {})
        for field_name in KNOWN_FIELDS:
            field = fields.get(field_name)
            if not field:
                continue
            value = strip_html(field.get("value", ""))
            if value:
                known.add(value)
    return known


def is_known(word: str, reading: str, known_set: Set[str]) -> bool:
    """A word is known if its surface or reading is already in the known set."""
    return word in known_set or reading in known_set


def select_candidates(
    entries: List[Tuple[str, str, str]],
    known_set: Set[str],
    x: int,
    levels: List[str] = None,
) -> List[Tuple[str, str]]:
    """Return the first x (word, reading) entries not in known_set, in order.

    Skips duplicates within the input. Returns fewer than x if the input
    is exhausted — caller is responsible for warning.

    If `levels` is set (e.g. ["N3", "N4"]), only entries from those JLPT
    levels are considered, in the order they appear in JLPT.json.
    If `levels` is None or contains "all", all entries are considered.
    """
    if x <= 0:
        return []
    # Normalize: "all" or None means no filter
    if not levels or "all" in levels:
        levels = None
    candidates: List[Tuple[str, str]] = []
    seen: Set[Tuple[str, str]] = set()
    for entry_level, word, reading in entries:
        if levels and entry_level not in levels:
            continue
        key = (word, reading)
        if key in seen:
            continue
        seen.add(key)
        if is_known(word, reading, known_set):
            continue
        candidates.append(key)
        if len(candidates) >= x:
            break
    return candidates


ANKI_URL = "http://localhost:8765"
ANKI_VERSION = 6


class AnkiError(RuntimeError):
    """Raised when AnkiConnect returns an error or HTTP failure."""


def anki_post(action: str, params: dict, url: str = ANKI_URL, timeout: float = 10.0):
    """POST an AnkiConnect action. Returns the `result` field. Raises AnkiError on failure."""
    body = {"action": action, "version": ANKI_VERSION, "params": params}
    try:
        resp = requests.post(url, json=body, timeout=timeout)
    except requests.RequestException as e:
        raise AnkiError(f"AnkiConnect not reachable at {url}: {e}") from e
    if resp.status_code != 200:
        raise AnkiError(f"AnkiConnect HTTP {resp.status_code}")
    try:
        payload = resp.json()
    except ValueError as e:
        raise AnkiError(f"AnkiConnect returned non-JSON response: {e}") from e
    if payload.get("error"):
        raise AnkiError(f"AnkiConnect error: {payload['error']}")
    return payload.get("result")


def anki_get_deck_config_x(deck: str, url: str = ANKI_URL) -> int:
    """Return the perDay new-card count for the given Anki deck."""
    config = anki_post("getDeckConfig", {"deck": deck}, url=url)
    return int(config["new"]["perDay"])


NOTES_INFO_BATCH = 500


def anki_get_deck_words(deck: str, url: str = ANKI_URL) -> Set[str]:
    """Return the set of known words (surfaces + readings) in the given Anki deck."""
    note_ids = anki_post("findNotes", {"query": f'deck:"{deck}"'}, url=url)
    if not note_ids:
        return set()
    known: Set[str] = set()
    for i in range(0, len(note_ids), NOTES_INFO_BATCH):
        batch = note_ids[i : i + NOTES_INFO_BATCH]
        notes_info = anki_post("notesInfo", {"notes": batch}, url=url)
        known |= build_known_set(notes_info)
    return known


def anki_word_in_deck(word: str, deck: str, url: str = ANKI_URL) -> bool:
    """Check if a word appears anywhere in the Anki deck (any field, any note type).

    Uses AnkiConnect's full-text search to catch words stored in different
    surface forms (e.g., kanji 有らゆる vs hiragana あらゆる) or in non-standard
    fields the known-set builder doesn't check.
    """
    note_ids = anki_post("findNotes", {"query": f'deck:"{deck}" {word}'}, url=url)
    return len(note_ids) > 0


DEFAULT_JLPT_PATH = "/Users/distiled/Study materials/Japanese/JLPT.json"
DEFAULT_PROFILE_DIR = os.path.expanduser(
    "~/Library/Application Support/Migaku-Automation/chrome-profile"
)
DEFAULT_SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
DEFAULT_SKIPPED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skipped_words.txt")
DEFAULT_LAST_SELECTION_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_selection.txt")
DEFAULT_QUEUED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "queued_words.txt")

CONFIG_TEMPLATE = """\
# Migaku Queue Configuration

# JLPT level(s) to pull words from.
#   Single level:  N3
#   Multiple:      N3,N4      (comma-separated, words taken in JLPT.json order)
#   All levels:    all         (sequential N5 -> N1)
level: all

# Number of words to queue per run.
#   Set a number to always queue that many.
#   Leave commented to use Anki deck's "new cards per day" setting.
# count: 17

# Anki deck to read known words from.
# deck: Main deck

# Path to JLPT.json.
# jlpt_path: /Users/distiled/Study materials/Japanese/JLPT.json

# Chrome profile directory for the Migaku extension session.
# profile_dir: ~/Library/Application Support/Migaku-Automation/chrome-profile
"""


def parse_levels(level_str: str) -> List[str]:
    """Parse a level string like 'N3,N4' or 'all' or 'N5' into a list of levels.

    Returns an empty list for "all" (meaning no filter).
    """
    if not level_str:
        return []
    parts = [p.strip().upper() for p in level_str.split(",") if p.strip()]
    if not parts or "ALL" in parts:
        return []
    return parts


def load_config(path: str = DEFAULT_CONFIG_PATH) -> dict:
    """Load YAML config. Auto-creates from template if file is missing."""
    import yaml
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        # Auto-create from template so the user has something to edit
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(CONFIG_TEMPLATE)
            print(f"Created default config at {path} — edit it to set your level/count.")
        except OSError:
            pass  # Can't write (read-only dir?), just proceed with defaults
        return {}


def load_skipped(path: str = DEFAULT_SKIPPED_PATH) -> Set[str]:
    """Load previously skipped words from file. Returns a set of surfaces and readings."""
    skipped: Set[str] = set()
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    skipped.add(line)
    except FileNotFoundError:
        pass
    return skipped


def save_skipped(words: Set[str], path: str = DEFAULT_SKIPPED_PATH) -> None:
    """Append new skipped words to the file (deduped against existing content)."""
    existing = load_skipped(path)
    new_words = words - existing
    if not new_words:
        return
    with open(path, "a", encoding="utf-8") as f:
        for w in sorted(new_words):
            f.write(w + "\n")


def load_queued(path: str = DEFAULT_QUEUED_PATH) -> Set[str]:
    """Load previously queued (sent to Migaku) words. Returns a set of surfaces and readings."""
    return load_skipped(path)  # same file format, reuse loader


def save_queued(words: Set[str], path: str = DEFAULT_QUEUED_PATH) -> None:
    """Append newly queued words to the file (deduped)."""
    save_skipped(words, path)  # same append-dedup logic


def save_last_selection(candidates: List[Tuple[str, str]], path: str = DEFAULT_LAST_SELECTION_PATH) -> None:
    """Save the accepted word selection to a file so it can be restored on next run.

    Deduplicates by (word, reading) to prevent the same word appearing twice.
    """
    seen: Set[Tuple[str, str]] = set()
    with open(path, "w", encoding="utf-8") as f:
        for word, reading in candidates:
            key = (word, reading)
            if key in seen:
                continue
            seen.add(key)
            f.write(f"{word}\t{reading}\n")


def load_last_selection(path: str = DEFAULT_LAST_SELECTION_PATH) -> List[Tuple[str, str]]:
    """Load a previously saved selection. Returns empty list if file is missing.

    Deduplicates by (word, reading) to handle files with duplicate entries.
    """
    candidates: List[Tuple[str, str]] = []
    seen: Set[Tuple[str, str]] = set()
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) == 2:
                    key = (parts[0], parts[1])
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append(key)
    except FileNotFoundError:
        pass
    return candidates


def parse_args(argv=None) -> argparse.Namespace:
    """Parse CLI arguments. Bare command produces sensible defaults.

    Config file is loaded in two phases: first `--config` is extracted via
    parse_known_args, then the full parse uses config values as defaults.
    """
    # Phase 1: extract --config so we know which file to load
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    pre_args, _ = pre.parse_known_args(argv)

    config = load_config(pre_args.config)

    # Phase 2: full parse with config as defaults
    p = argparse.ArgumentParser(
        description="Top up the Migaku dictionary queue with new words from JLPT.json."
    )
    p.add_argument("--deck", default=config.get("deck", "Main deck"), help="Anki deck name (default: Main deck)")
    p.add_argument("--count", type=int, default=config.get("count"), help="Override X (default: from Anki deck config new.perDay)")
    p.add_argument("--level", default=config.get("level", "all"), help="JLPT level(s): N5, N4, N3, N2, N1, comma-separated (N3,N4), or all (default: all)")
    p.add_argument("--jlpt-path", default=config.get("jlpt_path", DEFAULT_JLPT_PATH), help="Path to JLPT.json")
    p.add_argument("--extension-path", default="", help="Path to the Migaku extension folder (default: auto-detect)")
    p.add_argument("--profile-dir", default=config.get("profile_dir", DEFAULT_PROFILE_DIR), help="Chrome persistent profile directory")
    p.add_argument("--dry-run", action="store_true", help="Print candidates, don't touch Chrome")
    p.add_argument("--no-confirm", action="store_true", help="Skip interactive word selection, accept all candidates")
    p.add_argument("--no-leave-open", dest="leave_open", action="store_false", help="Close Chrome after adding")
    p.add_argument("--headless", action="store_true", help="Run Chrome headless (default: headful)")
    p.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Path to config.yaml (default: config.yaml next to script)")
    p.add_argument("--anki-url", default=ANKI_URL, help=argparse.SUPPRESS)
    return p.parse_args(argv)


MIGAKU_EXTENSION_ID = "lkhiljgmbeecmljiogckofcalncmfnfo"
DEFAULT_CHROME_EXTENSIONS_DIR = os.path.expanduser(
    "~/Library/Application Support/Google/Chrome/Default/Extensions"
)


class ExtensionNotFound(RuntimeError):
    """Raised when the Migaku Chrome extension can't be located."""


def detect_extension_path(extensions_dir: str = DEFAULT_CHROME_EXTENSIONS_DIR) -> str:
    """Find the Migaku extension folder. Picks the highest installed version.

    Raises ExtensionNotFound if the extension is missing or has no version dirs.
    """
    ext_root = os.path.join(extensions_dir, MIGAKU_EXTENSION_ID)
    if not os.path.isdir(ext_root):
        raise ExtensionNotFound(
            f"Migaku extension not found at {ext_root}. "
            f"Pass --extension-path to override."
        )
    versions = [
        name for name in os.listdir(ext_root)
        if os.path.isdir(os.path.join(ext_root, name))
    ]
    if not versions:
        raise ExtensionNotFound(f"No version dirs inside {ext_root}")
    # Sort by version tuple (split on '.', compare numerically)
    versions.sort(key=lambda v: [int(x) for x in v.replace("_", ".").split(".") if x.isdigit()])
    return os.path.join(ext_root, versions[-1])


DICTIONARY_URL = (
    f"chrome-extension://{MIGAKU_EXTENSION_ID}/pages/app-window/index.html#/app/dictionary"
)


def launch_chrome(extension_path: str, profile_dir: str, headless: bool = False):
    """Launch a persistent Chromium context with the Migaku extension loaded.

    Returns (playwright, context, page). Caller is responsible for closing.
    """
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        profile_dir,
        headless=headless,
        args=[
            f"--disable-extensions-except={extension_path}",
            f"--load-extension={extension_path}",
        ],
        # Extensions only load in headed mode by default; --headless=new is required for headless extensions.
        # Playwright handles this when headless=True on recent Chromium.
        viewport={"width": 1280, "height": 900},
    )
    page = context.new_page()
    return pw, context, page


def open_dictionary(page, setup_timeout_seconds: int = 120):
    """Navigate to the Migaku dictionary page. Returns when the dictionary view is shown.

    On a fresh profile, the Migaku app shows a loading/setup screen first
    (it installs a default dictionary). We wait for the app to finish initializing
    (title no longer contains "Loading" or "Setup"). The SPA may redirect to
    #/app/dashboard after init; if so, we set the hash to #/app/dictionary directly
    (page.goto to the dictionary URL during init gets redirected, but post-init
    hash changes are respected).
    """
    import time
    page.goto(DICTIONARY_URL, wait_until="domcontentloaded")
    deadline = time.time() + setup_timeout_seconds
    while time.time() < deadline:
        title = page.title()
        if "Loading" not in title and "Setup" not in title:
            # App finished loading. If we're not on dictionary, navigate there.
            if "#/app/dictionary" not in page.url:
                page.evaluate("window.location.hash = '#/app/dictionary'")
                page.wait_for_timeout(1500)
            if "#/app/dictionary" in page.url:
                page.wait_for_timeout(1500)  # let the dictionary view render
                return
        page.wait_for_timeout(2000)
    raise RuntimeError(
        f"Dictionary view did not load within {setup_timeout_seconds}s "
        f"(still at {page.url}, title={page.title()!r})."
    )


def ensure_logged_in(page, poll_timeout_seconds: int = 300):
    """Detect login screen and block until the user logs in.

    Polls the page state every 2 seconds. If a login screen is visible,
    prints a prompt once, then waits until the dictionary view is shown
    or `poll_timeout_seconds` elapse (default 5 minutes).
    """
    import time
    deadline = time.time() + poll_timeout_seconds
    prompted = False
    while time.time() < deadline:
        url = page.url
        login_visible = False
        if "#/login" in url or "/auth" in url or "login" in url.lower():
            login_visible = True
        else:
            try:
                if page.locator("input[type='password']").count() > 0:
                    login_visible = True
            except Exception:
                pass
        if not login_visible:
            return
        if not prompted:
            print(
                "Migaku dictionary is showing a login page. "
                "Please log in in the Chrome window — this script will "
                "auto-continue once login completes.",
                flush=True,
            )
            prompted = True
        page.wait_for_timeout(2000)
    raise RuntimeError(
        f"Still showing a login page after {poll_timeout_seconds}s; aborting."
    )


# Selectors discovered by inspecting the Migaku dictionary page.
# Update these if a Migaku extension update breaks the script.
DICTIONARY_SEARCH_INPUT = ".MainDictionary__input"
SEND_TO_CARD_CREATOR_BUTTON = ".UiDictEntry__send"
QUEUE_COUNTER_BUTTON = "button:has-text('Queued')"


def add_word_to_queue(page, word: str, screenshot_dir: str = DEFAULT_SCREENSHOT_DIR, max_retries: int = 3) -> bool:
    """Search for `word` in the dictionary and click 'Send to Card Creator'.

    Returns True on success, False on failure. On failure, saves a screenshot.
    The first word sent opens the Card Creator form; subsequent words go to
    the 'Queued' list inside the Card Creator.

    Retries up to `max_retries` times if the search input is temporarily
    unavailable (e.g., Card Creator is still processing the previous word).
    """
    import time

    for attempt in range(1, max_retries + 1):
        try:
            # Wait for the search input to be ready, then clear and fill
            input_locator = page.locator(DICTIONARY_SEARCH_INPUT)
            input_locator.wait_for(state="visible", timeout=10000)
            page.fill(DICTIONARY_SEARCH_INPUT, "", timeout=10000)
            page.fill(DICTIONARY_SEARCH_INPUT, word, timeout=10000)
            page.wait_for_timeout(1500)  # let results populate
            break
        except Exception as e:
            if attempt < max_retries:
                print(f"  [retry {attempt}/{max_retries}] search input not ready for {word!r}, waiting 3s...")
                page.wait_for_timeout(3000)
            else:
                print(f"  [warn] could not search for {word!r} after {max_retries} attempts: {e}")
                _screenshot(page, screenshot_dir, word)
                return False

    # Find and click the 'Send to Card Creator' button on the first dictionary entry
    try:
        btn = page.locator(SEND_TO_CARD_CREATOR_BUTTON).first
        if btn.count() == 0:
            print(f"  [warn] no dictionary entries for {word!r} — skipping")
            _screenshot(page, screenshot_dir, word)
            return False
        btn.click(timeout=3000)
        page.wait_for_timeout(1000)  # let the card creator / queue update
        return True
    except Exception as e:
        print(f"  [warn] send-to-card-creator button not clickable for {word!r}: {e}")
        _screenshot(page, screenshot_dir, word)
        return False


def get_queue_count(page) -> int:
    """Return the current 'Queued' counter from the Card Creator, or -1 if not found."""
    try:
        btn = page.locator(QUEUE_COUNTER_BUTTON).first
        if btn.count() == 0:
            return -1
        text = btn.inner_text()  # e.g. "Queued (3)"
        import re
        match = re.search(r"\((\d+)\)", text)
        return int(match.group(1)) if match else -1
    except Exception:
        return -1


def _screenshot(page, screenshot_dir: str, word: str) -> None:
    import time
    os.makedirs(screenshot_dir, exist_ok=True)
    ts = int(time.time())
    safe = word.replace("/", "_")
    path = os.path.join(screenshot_dir, f"{ts}_{safe}.png")
    try:
        page.screenshot(path=path, full_page=True)
        print(f"  [screenshot] saved to {path}")
    except Exception as e:
        print(f"  [warn] could not save screenshot: {e}")


def interactive_select(
    entries: List[Tuple[str, str, str]],
    known_set: Set[str],
    x: int,
    levels: List[str] = None,
    skipped_path: str = DEFAULT_SKIPPED_PATH,
    queued_path: str = DEFAULT_QUEUED_PATH,
) -> List[Tuple[str, str]]:
    """Show candidates to the user, let them skip words, refetch replacements.

    Loops until the user accepts X words (or the levels are exhausted).
    Skipped words are persisted to `skipped_path` and accepted words are
    persisted to `queued_path` so neither is re-offered on future runs.
    """
    accepted: List[Tuple[str, str]] = []
    rejected: Set[str] = set()
    level_label = ",".join(levels) if levels else "all levels"

    while len(accepted) < x:
        needed = x - len(accepted)
        effective_known = known_set | rejected | {w for w, _r in accepted}
        new_batch = select_candidates(entries, effective_known, needed, levels)

        if not new_batch:
            print(f"\nNo more candidates available from {level_label}.")
            break

        print(f"\n--- {len(new_batch)} new candidate(s) from {level_label} "
              f"({len(accepted)} accepted, {len(accepted) + len(new_batch)}/{x}) ---")
        for i, (word, reading) in enumerate(new_batch, 1):
            print(f"  {i}. {word}  ({reading})")

        print(f"\nEnter numbers to skip (space-separated), or Enter to accept all:")
        try:
            response = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted by user.")
            save_skipped(rejected, skipped_path)
            return accepted

        if not response:
            accepted.extend(new_batch)
        else:
            skip_indices = set()
            for part in response.split():
                try:
                    idx = int(part) - 1
                    if 0 <= idx < len(new_batch):
                        skip_indices.add(idx)
                except ValueError:
                    pass

            kept = 0
            for i, (word, reading) in enumerate(new_batch):
                if i in skip_indices:
                    rejected.add(word)
                    rejected.add(reading)
                    print(f"  skipped: {word} ({reading})")
                else:
                    accepted.append((word, reading))
                    kept += 1

            if skip_indices:
                print(f"  Kept {kept}, skipped {len(skip_indices)}. Fetching replacements...")

    save_skipped(rejected, skipped_path)
    # Persist accepted words immediately so they're never re-offered,
    # even if the Chrome phase fails or the user interrupts.
    if accepted:
        accepted_words = {w for w, r in accepted} | {r for w, r in accepted}
        save_queued(accepted_words, queued_path)
    return accepted


def _verify_against_anki(
    candidates: List[Tuple[str, str]],
    deck: str,
    anki_url: str,
    known_set: Set[str],
    entries: List[Tuple[str, str, str]],
    levels: List[str],
    x: int,
) -> List[Tuple[str, str]]:
    """Double-check candidates against Anki's full-text search.

    Catches words stored in non-standard note types or surface forms that
    the known-set builder missed. Replaces any that are found in Anki with
    fresh candidates.
    """
    verified: List[Tuple[str, str]] = []
    replaced = 0
    for word, reading in candidates:
        try:
            if anki_word_in_deck(word, deck, url=anki_url):
                print(f"  [anki] {word} ({reading}) found in deck via full-text search — skipping")
                known_set.add(word)
                known_set.add(reading)
                replaced += 1
                continue
        except AnkiError as e:
            print(f"  [warn] Anki search failed for {word!r}: {e}")
        verified.append((word, reading))

    if replaced > 0:
        print(f"  [anki] {replaced} word(s) found in Anki; fetching {replaced} replacement(s)...")
        extra_known = known_set | {w for w, r in verified} | {r for w, r in verified}
        extra = select_candidates(entries, extra_known, replaced, levels)
        verified.extend(extra)
        if extra:
            print(f"  [anki] added {len(extra)} replacement(s).")

    return verified


def main(argv=None) -> int:
    import json
    import time

    args = parse_args(argv)

    # 1. Determine X
    if args.count is not None:
        x = args.count
        print(f"Using --count override: X={x}")
    else:
        try:
            x = anki_get_deck_config_x(args.deck, url=args.anki_url)
        except AnkiError as e:
            print(f"Error: {e}")
            return 1
        print(f"Anki deck {args.deck!r}: new.perDay = {x}")

    if x <= 0:
        print("X is 0; nothing to do.")
        return 0

    # 2. Load JLPT.json
    try:
        with open(args.jlpt_path, encoding="utf-8") as f:
            jlpt_data = json.load(f)
    except (OSError, ValueError) as e:
        print(f"Error reading {args.jlpt_path}: {e}")
        return 1
    entries = parse_jlpt_json(jlpt_data)
    print(f"JLPT.json: {len(entries)} parsed entries")

    # 3. Build known set (Anki deck words + previously skipped + previously queued)
    try:
        known_set = anki_get_deck_words(args.deck, url=args.anki_url)
    except AnkiError as e:
        print(f"Error: {e}")
        return 1
    extra = []
    skipped_set = load_skipped()
    if skipped_set:
        known_set |= skipped_set
        extra.append(f"{len(skipped_set)} skipped")
    queued_set = load_queued()
    if queued_set:
        known_set |= queued_set
        extra.append(f"{len(queued_set)} queued")
    if extra:
        print(f"Known words in {args.deck!r}: {len(known_set)} (+{', '.join(extra)})")
    else:
        print(f"Known words in {args.deck!r}: {len(known_set)}")

    # 4. Select candidates (or restore previous selection)
    levels = parse_levels(args.level)
    level_label = args.level or "all"

    if args.no_confirm or args.dry_run:
        candidates = select_candidates(entries, known_set, x, levels)
        # Verify each candidate against Anki's full-text search to catch
        # words stored in different note types / surface forms
        if not args.dry_run and candidates:
            candidates = _verify_against_anki(candidates, args.deck, args.anki_url, known_set, entries, levels, x)
            if not candidates:
                print("All candidates were already in Anki. Try a different level or increase count.")
                return 0
        if len(candidates) < x:
            print(f"Warning: only {len(candidates)} candidates available from {level_label} (requested {x}).")

        print(f"Selected {len(candidates)} new words from {level_label}:")
        for word, reading in candidates:
            print(f"  {word}  ({reading})")
        if not args.dry_run and candidates:
            save_queued({w for w, r in candidates} | {r for w, r in candidates})
    else:
        # Load the previous selection (regardless of whether we restore it,
        # we want to avoid re-offering those words during fresh selection)
        last_selection_raw = load_last_selection()
        # Filter out words that are now in the known set (already in Anki or skipped)
        last_selection = [
            (w, r) for w, r in last_selection_raw
            if not is_known(w, r, known_set)
        ]
        candidates = []
        if last_selection:
            print(f"\nFound a previous selection of {len(last_selection)} word(s) not yet in your deck:")
            for i, (word, reading) in enumerate(last_selection, 1):
                print(f"  {i}. {word}  ({reading})")
            print(f"\nRestore previous selection? [Y/n]: ", end="", flush=True)
            try:
                response = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                response = "n"
            if response in ("", "y", "yes"):
                candidates = last_selection
                print("Restored previous selection.")
            else:
                candidates = []

        if not candidates:
            # Merge the previous selection into the known set so those words
            # are not re-offered during fresh selection. This prevents the
            # user from seeing the same words they just reviewed.
            for w, r in last_selection_raw:
                known_set.add(w)
                known_set.add(r)
            print(f"\nSelecting {x} words from {level_label}.")
            print("You can skip words you don't want; replacements will be fetched automatically.")
            candidates = interactive_select(entries, known_set, x, levels)
            if len(candidates) < x:
                print(f"\nWarning: only {len(candidates)} candidates available from {level_label} (requested {x}).")

        print(f"\nFinal selection ({len(candidates)} words from {level_label}):")
        for word, reading in candidates:
            print(f"  {word}  ({reading})")
        save_last_selection(candidates)

    if not candidates:
        print("No words to add.")
        return 0

    if args.dry_run:
        print("Dry run — not touching Chrome.")
        return 0

    # 5. Drive Migaku dictionary
    try:
        extension_path = args.extension_path or detect_extension_path()
    except ExtensionNotFound as e:
        print(f"Error: {e}")
        return 1

    print("Launching Chrome with Migaku extension...")
    pw, ctx, page = launch_chrome(extension_path, args.profile_dir, headless=args.headless)
    try:
        open_dictionary(page)
        ensure_logged_in(page)
        # After login, the SPA may have redirected to #/app/dashboard.
        # Re-navigate to the dictionary to be sure we're on the right page.
        if "#/app/dictionary" not in page.url:
            print("Re-navigating to dictionary after login...")
            open_dictionary(page)

        consecutive_failures = 0
        added = 0
        successfully_queued: List[Tuple[str, str]] = []
        for i, (word, reading) in enumerate(candidates):
            print(f"Adding {word!r} ({reading})...  [{i+1}/{len(candidates)}]")
            if add_word_to_queue(page, word, screenshot_dir=DEFAULT_SCREENSHOT_DIR):
                added += 1
                consecutive_failures = 0
                successfully_queued.append((word, reading))
                # Small delay between words to let the Card Creator process
                if i < len(candidates) - 1:
                    page.wait_for_timeout(500)
            else:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    print("Three consecutive failures — extension UI may have changed. Aborting.")
                    print("Check screenshots/ for diagnostics.")
                    break

        # Persist successfully queued words so they're never re-offered
        if successfully_queued:
            queued_words = {w for w, r in successfully_queued} | {r for w, r in successfully_queued}
            save_queued(queued_words)
            print(f"Saved {len(successfully_queued)} words to queued_words.txt.")

        queue_count = get_queue_count(page)
        print(f"\nAdded {added}/{len(candidates)} words to the Migaku Card Creator.")
        if queue_count >= 0:
            print(f"Card Creator queue: {queue_count} waiting (plus 1 current item being edited).")

        if not args.leave_open:
            ctx.close()
        else:
            print("\nLeaving the dictionary window open. Press Ctrl+C in terminal to close.")
            try:
                while True:
                    page.wait_for_timeout(60000)
            except (KeyboardInterrupt, Exception):
                pass
    finally:
        if not args.leave_open:
            ctx.close()
        pw.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
