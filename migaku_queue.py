#!/usr/bin/env python3
"""Top up the Migaku dictionary queue with new Japanese words from JLPT.json."""

import re
import requests
from typing import List, Set, Tuple as PyTuple, Tuple

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
    entries: List[PyTuple[str, str, str]],
    known_set: Set[str],
    x: int,
) -> List[PyTuple[str, str]]:
    """Return the first x (word, reading) entries not in known_set, in order.

    Skips duplicates within the input. Returns fewer than x if the input
    is exhausted — caller is responsible for warning.
    """
    candidates: List[PyTuple[str, str]] = []
    seen: Set[PyTuple[str, str]] = set()
    for _level, word, reading in entries:
        if x == 0:
            break
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
    payload = resp.json()
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


def main() -> int:
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
