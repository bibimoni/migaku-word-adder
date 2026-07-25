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
) -> List[Tuple[str, str]]:
    """Return the first x (word, reading) entries not in known_set, in order.

    Skips duplicates within the input. Returns fewer than x if the input
    is exhausted — caller is responsible for warning.
    """
    if x <= 0:
        return []
    candidates: List[Tuple[str, str]] = []
    seen: Set[Tuple[str, str]] = set()
    for _level, word, reading in entries:
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


def parse_args(argv=None) -> argparse.Namespace:
    """Parse CLI arguments. Bare command produces sensible defaults."""
    p = argparse.ArgumentParser(
        description="Top up the Migaku dictionary queue with new words from JLPT.json."
    )
    p.add_argument("--deck", default="Main deck", help="Anki deck name (default: Main deck)")
    p.add_argument("--count", type=int, default=None, help="Override X (default: from Anki deck config new.perDay)")
    p.add_argument("--jlpt-path", default=DEFAULT_JLPT_PATH, help="Path to JLPT.json")
    p.add_argument("--extension-path", default="", help="Path to the Migaku extension folder (default: auto-detect)")
    p.add_argument("--profile-dir", default=DEFAULT_PROFILE_DIR, help="Chrome persistent profile directory")
    p.add_argument("--dry-run", action="store_true", help="Print candidates, don't touch Chrome")
    p.add_argument("--no-leave-open", dest="leave_open", action="store_false", help="Close Chrome after adding")
    p.add_argument("--headless", action="store_true", help="Run Chrome headless (default: headful)")
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


def main() -> int:
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
