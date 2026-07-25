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


KNOWN_FIELDS = ("Vocabulary-Kanji", "Vocabulary-Kana")


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
    level: str = None,
) -> List[Tuple[str, str]]:
    """Return the first x (word, reading) entries not in known_set, in order.

    Skips duplicates within the input. Returns fewer than x if the input
    is exhausted — caller is responsible for warning.

    If `level` is set (e.g. "N3"), only entries from that JLPT level are
    considered. If `level` is None or "all", all entries are considered.
    """
    if x <= 0:
        return []
    candidates: List[Tuple[str, str]] = []
    seen: Set[Tuple[str, str]] = set()
    for entry_level, word, reading in entries:
        if level and level != "all" and entry_level != level:
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


DEFAULT_JLPT_PATH = "/Users/distiled/Study materials/Japanese/JLPT.json"
DEFAULT_PROFILE_DIR = os.path.expanduser(
    "~/Library/Application Support/Migaku-Automation/chrome-profile"
)
DEFAULT_SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
DEFAULT_SKIPPED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skipped_words.txt")


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


def load_config(path: str = DEFAULT_CONFIG_PATH) -> dict:
    """Load YAML config. Returns a dict, possibly empty if file is missing."""
    import yaml
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}


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
    p.add_argument("--level", default=config.get("level", "all"), help="JLPT level: N5, N4, N3, N2, N1, or all (default: all)")
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


def add_word_to_queue(page, word: str, screenshot_dir: str = DEFAULT_SCREENSHOT_DIR) -> bool:
    """Search for `word` in the dictionary and click 'Send to Card Creator'.

    Returns True on success, False on failure. On failure, saves a screenshot.
    The first word sent opens the Card Creator form; subsequent words go to
    the 'Queued' list inside the Card Creator.
    """
    try:
        page.fill(DICTIONARY_SEARCH_INPUT, "")
        page.fill(DICTIONARY_SEARCH_INPUT, word)
        page.wait_for_timeout(1500)  # let results populate
    except Exception as e:
        print(f"  [warn] could not search for {word!r}: {e}")
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
    level: str = None,
    skipped_path: str = DEFAULT_SKIPPED_PATH,
) -> List[Tuple[str, str]]:
    """Show candidates to the user, let them skip words, refetch replacements.

    Loops until the user accepts X words (or the level is exhausted).
    Skipped words are remembered in-memory and persisted to `skipped_path`
    so they aren't re-offered on future runs.
    """
    accepted: List[Tuple[str, str]] = []
    rejected: Set[str] = set()
    level_label = level if level and level != "all" else "all levels"

    while len(accepted) < x:
        needed = x - len(accepted)
        effective_known = known_set | rejected | {w for w, _r in accepted}
        new_batch = select_candidates(entries, effective_known, needed, level)

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
    return accepted


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

    # 3. Build known set (Anki deck words + previously skipped words)
    try:
        known_set = anki_get_deck_words(args.deck, url=args.anki_url)
    except AnkiError as e:
        print(f"Error: {e}")
        return 1
    skipped_set = load_skipped()
    if skipped_set:
        print(f"Known words in {args.deck!r}: {len(known_set)} (+{len(skipped_set)} previously skipped)")
        known_set |= skipped_set
    else:
        print(f"Known words in {args.deck!r}: {len(known_set)}")

    # 4. Select candidates
    level = args.level if args.level and args.level != "all" else None
    level_label = args.level or "all"

    if args.no_confirm or args.dry_run:
        candidates = select_candidates(entries, known_set, x, level)
        if len(candidates) < x:
            print(f"Warning: only {len(candidates)} candidates available from {level_label} (requested {x}).")

        print(f"Selected {len(candidates)} new words from {level_label}:")
        for word, reading in candidates:
            print(f"  {word}  ({reading})")
    else:
        print(f"\nSelecting {x} words from {level_label}.")
        print("You can skip words you don't want; replacements will be fetched automatically.")
        candidates = interactive_select(entries, known_set, x, level)
        if len(candidates) < x:
            print(f"\nWarning: only {len(candidates)} candidates available from {level_label} (requested {x}).")

        print(f"\nFinal selection ({len(candidates)} words from {level_label}):")
        for word, reading in candidates:
            print(f"  {word}  ({reading})")

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

        consecutive_failures = 0
        added = 0
        for word, reading in candidates:
            print(f"Adding {word!r} ({reading})...")
            if add_word_to_queue(page, word, screenshot_dir=DEFAULT_SCREENSHOT_DIR):
                added += 1
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    print("Three consecutive failures — extension UI may have changed. Aborting.")
                    print("Check screenshots/ for diagnostics.")
                    break

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
