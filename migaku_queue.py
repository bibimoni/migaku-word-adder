#!/usr/bin/env python3
"""Top up the Migaku dictionary queue with new Japanese words from JLPT.json."""

import re
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


def main() -> int:
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
