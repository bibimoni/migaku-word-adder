# Migaku Queue From Anki — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single Python script (`migaku_queue.py`) that reads the daily new-card count from the Anki "Main deck", picks that many unlearned Japanese words from `JLPT.json` (skipping words already in the deck), and queues them in the Migaku dictionary Chrome extension via Playwright.

**Architecture:** Linear pipeline. AnkiConnect HTTP queries → in-memory "already known" set → sequential filter of `JLPT.json` entries → Playwright drives the Migaku extension's dictionary UI to search each word and click "add to queue". One script file plus tests; no modules.

**Tech Stack:** Python 3.14, `requests` (AnkiConnect HTTP), `playwright` (Chrome automation), `pytest` (unit tests of pure functions), `unittest.mock` (mocking HTTP in tests — no extra deps).

**Spec:** `docs/superpowers/specs/2026-07-26-migaku-queue-from-anki-design.md`

**Working directory:** `/Users/distiled/Dev/migaku/`

---

## File Structure

```
/Users/distiled/Dev/migaku/
├── migaku_queue.py              # the script (all logic in one file, ~300 lines)
├── requirements.txt             # runtime deps: requests, playwright
├── requirements-dev.txt         # dev deps: pytest
├── .gitignore                   # ignore venv, profile dir, screenshots, __pycache__
├── README.md                    # setup + usage + troubleshooting
└── tests/
    ├── __init__.py
    ├── conftest.py              # fixtures: paths, sample data
    ├── fixtures/
    │   ├── small_jlpt.json       # tiny JLPT-like JSON for parsing tests
    │   └── notes_info_sample.json  # sample AnkiConnect notesInfo response
    ├── test_parse_jlpt.py       # parse_jlpt_json, strip_html
    ├── test_known_set.py         # build_known_set, is_known
    ├── test_select_candidates.py # select_candidates
    ├── test_anki_client.py       # anki_get_deck_config_x, anki_get_deck_words (mocked HTTP)
    └── test_cli.py               # argument parsing
```

All functions live in `migaku_queue.py` (one file). Tests import from `migaku_queue`. The script is importable (no top-level side effects in functions under test; `main()` only runs under `if __name__ == "__main__"`).

---

## Task 1: Project skeleton

**Files:**
- Create: `/Users/distiled/Dev/migaku/.gitignore`
- Create: `/Users/distiled/Dev/migaku/requirements.txt`
- Create: `/Users/distiled/Dev/migaku/requirements-dev.txt`
- Create: `/Users/distiled/Dev/migaku/tests/__init__.py`
- Create: `/Users/distiled/Dev/migaku/tests/conftest.py`
- Create: `/Users/distiled/Dev/migaku/tests/fixtures/small_jlpt.json`
- Create: `/Users/distiled/Dev/migaku/tests/fixtures/notes_info_sample.json`
- Create: `/Users/distiled/Dev/migaku/migaku_queue.py` (stub)
- Create: `/Users/distiled/Dev/migaku/README.md` (stub, fully written in Task 14)

- [ ] **Step 1: Create `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
screenshots/
chrome-profile/
*.log
.DS_Store
```

- [ ] **Step 2: Create `requirements.txt`**

```
requests>=2.31
playwright>=1.40
```

- [ ] **Step 3: Create `requirements-dev.txt`**

```
-r requirements.txt
pytest>=8.0
```

- [ ] **Step 4: Create `tests/__init__.py` (empty file)**

- [ ] **Step 5: Create `tests/fixtures/small_jlpt.json`**

A miniature JLPT-like array exercising: N5 block with real words, a padding `["",""]` row, an N4 block with a duplicate word (same surface as an N5 word, to test that the parser doesn't dedupe — dedup happens later in `select_candidates`), and an empty trailing row.

```json
[["N5", "N5"],
 ["猫", "ねこ"],
 ["犬", "いぬ"],
 ["", ""],
 ["N4", "N4"],
 ["学校", "がっこう"],
 ["猫", "ねこ"],
 ["", ""]]
```

- [ ] **Step 6: Create `tests/fixtures/notes_info_sample.json`**

A realistic slice of AnkiConnect's `notesInfo` response, including HTML in some fields to exercise `strip_html`.

```json
[
  {"noteId": 1, "fields": {"Vocabulary-Kanji": {"value": "猫"}, "Vocabulary-Kana": {"value": "ねこ"}}},
  {"noteId": 2, "fields": {"Vocabulary-Kanji": {"value": "<b>学校</b>"}, "Vocabulary-Kana": {"value": "がっこう"}}},
  {"noteId": 3, "fields": {"Vocabulary-Kanji": {"value": ""}, "Vocabulary-Kana": {"value": "いぬ"}}}
]
```

- [ ] **Step 7: Create `tests/conftest.py`**

Exposes paths to fixture files so tests don't hardcode them.

```python
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def pytest_configure():
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")
```

- [ ] **Step 8: Create `migaku_queue.py` stub**

```python
#!/usr/bin/env python3
"""Top up the Migaku dictionary queue with new Japanese words from JLPT.json."""


def main() -> int:
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 9: Create `README.md` stub**

```markdown
# migaku-queue

Top up the Migaku dictionary queue with new Japanese words from `JLPT.json`.

Full setup and usage docs land in Task 14.
```

- [ ] **Step 10: Set up venv and install deps**

Run:
```bash
cd /Users/distiled/Dev/migaku && python3 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m playwright install chromium
```

Expected: venv created, pytest installed, Chromium downloaded for Playwright.

- [ ] **Step 11: Verify pytest runs (no tests yet)**

Run: `.venv/bin/pytest -q`
Expected: `no tests ran in 0.00s` (exit code 5 is fine for "no tests").

- [ ] **Step 12: Commit**

```bash
git -C /Users/distiled/Dev/migaku add .gitignore requirements.txt requirements-dev.txt tests/ migaku_queue.py README.md
git -C /Users/distiled/Dev/migaku commit -m "chore: project skeleton with venv and test fixtures"
```

---

## Task 2: `parse_jlpt_json` — TDD

Parse `JLPT.json` into a list of `(level, word, reading)` tuples. Skip level-marker rows (where `word == reading` and `word` starts with "N"), skip empty rows (`["",""]`), preserve order. The level is the *current* level as we walk down the file.

**Files:**
- Modify: `/Users/distiled/Dev/migaku/migaku_queue.py` (add `parse_jlpt_json`)
- Test: `/Users/distiled/Dev/migaku/tests/test_parse_jlpt.py`

- [ ] **Step 1: Write failing tests**

`tests/test_parse_jlpt.py`:

```python
import json
from pathlib import Path

from migaku_queue import parse_jlpt_json

from conftest import load_fixture


def test_parse_jlpt_json_returns_tuples_in_order():
    data = json.loads(load_fixture("small_jlpt.json"))
    entries = parse_jlpt_json(data)
    assert entries == [
        ("N5", "猫", "ねこ"),
        ("N5", "犬", "いぬ"),
        ("N4", "学校", "がっこう"),
        ("N4", "猫", "ねこ"),
    ]


def test_parse_jlpt_json_skips_level_marker_rows():
    # N5 marker row should not appear as an entry
    data = [["N5", "N5"], ["猫", "ねこ"]]
    entries = parse_jlpt_json(data)
    assert ("N5", "N5", "N5") not in entries


def test_parse_jlpt_json_skips_empty_rows():
    data = [["N5", "N5"], ["", ""], ["猫", "ねこ"]]
    entries = parse_jlpt_json(data)
    assert entries == [("N5", "猫", "ねこ")]


def test_parse_jlpt_json_handles_no_level_marker_at_start():
    # Edge case: file without leading level marker
    data = [["猫", "ねこ"]]
    entries = parse_jlpt_json(data)
    assert entries == [("", "猫", "ねこ")]
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `.venv/bin/pytest tests/test_parse_jlpt.py -v`
Expected: 4 FAIL with `ImportError: cannot import name 'parse_jlpt_json'`.

- [ ] **Step 3: Implement `parse_jlpt_json`**

Add to `migaku_queue.py`:

```python
from typing import List, Tuple


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
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `.venv/bin/pytest tests/test_parse_jlpt.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git -C /Users/distiled/Dev/migaku add migaku_queue.py tests/test_parse_jlpt.py
git -C /Users/distiled/Dev/migaku commit -m "feat: parse JLPT.json into (level, word, reading) tuples"
```

---

## Task 3: `strip_html` — TDD

Anki field values can contain HTML (`<b>学校</b>`). We need plain text for the known-set.

**Files:**
- Modify: `/Users/distiled/Dev/migaku/migaku_queue.py`
- Test: `/Users/distiled/Dev/migaku/tests/test_parse_jlpt.py` (add tests in the same file — both are about parsing/cleaning)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_parse_jlpt.py`:

```python
from migaku_queue import strip_html


def test_strip_html_removes_tags():
    assert strip_html("<b>学校</b>") == "学校"


def test_strip_html_handles_plain_text():
    assert strip_html("猫") == "猫"


def test_strip_html_removes_nested_tags():
    assert strip_html("<span class='x'><b>学校</b></span>") == "学校"


def test_strip_html_collapses_whitespace():
    assert strip_html("  猫\n 犬 ") == "猫 犬"


def test_strip_html_empty_string():
    assert strip_html("") == ""
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `.venv/bin/pytest tests/test_parse_jlpt.py -v`
Expected: 5 new tests FAIL with `ImportError: cannot import name 'strip_html'`.

- [ ] **Step 3: Implement `strip_html`**

Add to `migaku_queue.py`:

```python
import re

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(s: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    no_tags = _TAG_RE.sub("", s)
    return _WS_RE.sub(" ", no_tags).strip()
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `.venv/bin/pytest tests/test_parse_jlpt.py -v`
Expected: 9 PASS (4 from Task 2 + 5 new).

- [ ] **Step 5: Commit**

```bash
git -C /Users/distiled/Dev/migaku add migaku_queue.py tests/test_parse_jlpt.py
git -C /Users/distiled/Dev/migaku commit -m "feat: strip HTML from Anki field values"
```

---

## Task 4: `build_known_set` — TDD

Takes a list of AnkiConnect `notesInfo` result dicts and returns a set of all known surfaces and readings (HTML stripped).

**Files:**
- Modify: `/Users/distiled/Dev/migaku/migaku_queue.py`
- Test: `/Users/distiled/Dev/migaku/tests/test_known_set.py`

- [ ] **Step 1: Write failing tests**

`tests/test_known_set.py`:

```python
import json

from migaku_queue import build_known_set

from conftest import load_fixture


def test_build_known_set_extracts_surfaces_and_readings():
    notes = json.loads(load_fixture("notes_info_sample.json"))
    known = build_known_set(notes)
    # 猫 surface + ねこ reading
    assert "猫" in known
    assert "ねこ" in known
    # 学校 was wrapped in <b>...</b> — should be stripped
    assert "学校" in known
    assert "がっこう" in known
    # Note 3 has empty surface but a reading
    assert "いぬ" in known


def test_build_known_set_is_deduped():
    notes = [
        {"fields": {"Vocabulary-Kanji": {"value": "猫"}, "Vocabulary-Kana": {"value": "ねこ"}}},
        {"fields": {"Vocabulary-Kanji": {"value": "猫"}, "Vocabulary-Kana": {"value": "ねこ"}}},
    ]
    known = build_known_set(notes)
    assert known == {"猫", "ねこ"}


def test_build_known_set_skips_empty_values():
    notes = [{"fields": {"Vocabulary-Kanji": {"value": ""}, "Vocabulary-Kana": {"value": ""}}}]
    known = build_known_set(notes)
    assert known == set()


def test_build_known_set_handles_missing_fields():
    # Defensive: a note missing one of the fields should not crash
    notes = [{"fields": {"Vocabulary-Kanji": {"value": "猫"}}}]
    known = build_known_set(notes)
    assert known == {"猫"}
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `.venv/bin/pytest tests/test_known_set.py -v`
Expected: 4 FAIL with `ImportError: cannot import name 'build_known_set'`.

- [ ] **Step 3: Implement `build_known_set`**

Add to `migaku_queue.py`:

```python
from typing import Set


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
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `.venv/bin/pytest tests/test_known_set.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git -C /Users/distiled/Dev/migaku add migaku_queue.py tests/test_known_set.py
git -C /Users/distiled/Dev/migaku commit -m "feat: build known-words set from AnkiConnect notesInfo"
```

---

## Task 5: `is_known` — TDD

Matching rule: a word is "already known" if either its surface OR its reading is in the known set.

**Files:**
- Modify: `/Users/distiled/Dev/migaku/migaku_queue.py`
- Test: `/Users/distiled/Dev/migaku/tests/test_known_set.py` (same file — both about known-set logic)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_known_set.py`:

```python
from migaku_queue import is_known


def test_is_known_true_when_surface_in_set():
    assert is_known("猫", "ねこ", {"猫", "ねこ"}) is True


def test_is_known_true_when_only_reading_in_set():
    # JLPT.json surface form might differ from deck, but reading matches
    assert is_known("未知", "みち", {"みち"}) is True


def test_is_known_true_when_only_surface_in_set():
    assert is_known("学校", "がっこう", {"学校"}) is True


def test_is_known_false_when_neither_in_set():
    assert is_known("猫", "ねこ", {"犬", "いぬ"}) is False
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `.venv/bin/pytest tests/test_known_set.py -v`
Expected: 4 new tests FAIL with `ImportError: cannot import name 'is_known'`.

- [ ] **Step 3: Implement `is_known`**

Add to `migaku_queue.py`:

```python
def is_known(word: str, reading: str, known_set: Set[str]) -> bool:
    """A word is known if its surface or reading is already in the known set."""
    return word in known_set or reading in known_set
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `.venv/bin/pytest tests/test_known_set.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
git -C /Users/distiled/Dev/migaku add migaku_queue.py tests/test_known_set.py
git -C /Users/distiled/Dev/migaku commit -m "feat: matching rule for known words (surface or reading)"
```

---

## Task 6: `select_candidates` — TDD

Walk parsed JLPT entries in order, skip known, return the first `x` survivors as `(word, reading)` tuples. If fewer than `x` survive, return what's available (caller warns).

**Files:**
- Modify: `/Users/distiled/Dev/migaku/migaku_queue.py`
- Test: `/Users/distiled/Dev/migaku/tests/test_select_candidates.py`

- [ ] **Step 1: Write failing tests**

`tests/test_select_candidates.py`:

```python
from migaku_queue import select_candidates


def test_select_candidates_returns_first_x_unknown_in_order():
    entries = [
        ("N5", "猫", "ねこ"),
        ("N5", "犬", "いぬ"),
        ("N5", "鳥", "とり"),
        ("N5", "魚", "さかな"),
    ]
    known = {"犬", "いぬ"}
    result = select_candidates(entries, known, x=2)
    assert result == [("猫", "ねこ"), ("鳥", "とり")]


def test_select_candidates_returns_fewer_when_exhausted():
    entries = [("N5", "猫", "ねこ"), ("N5", "犬", "いぬ")]
    known = set()
    result = select_candidates(entries, known, x=5)
    assert result == [("猫", "ねこ"), ("犬", "いぬ")]


def test_select_candidates_returns_empty_when_all_known():
    entries = [("N5", "猫", "ねこ")]
    known = {"猫", "ねこ"}
    assert select_candidates(entries, known, x=1) == []


def test_select_candidates_x_zero_returns_empty():
    entries = [("N5", "猫", "ねこ")]
    assert select_candidates(entries, set(), x=0) == []


def test_select_candidates_dedupes_within_input():
    # If the same word appears twice in JLPT.json, only the first occurrence is selected
    entries = [("N5", "猫", "ねこ"), ("N4", "猫", "ねこ")]
    result = select_candidates(entries, set(), x=2)
    assert result == [("猫", "ねこ")]
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `.venv/bin/pytest tests/test_select_candidates.py -v`
Expected: 5 FAIL with `ImportError: cannot import name 'select_candidates'`.

- [ ] **Step 3: Implement `select_candidates`**

Add to `migaku_queue.py`:

```python
from typing import List, Tuple as PyTuple


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
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `.venv/bin/pytest tests/test_select_candidates.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Run all tests — verify nothing regressed**

Run: `.venv/bin/pytest -q`
Expected: all tests PASS (4 + 5 + 8 + 5 = 22).

- [ ] **Step 6: Commit**

```bash
git -C /Users/distiled/Dev/migaku add migaku_queue.py tests/test_select_candidates.py
git -C /Users/distiled/Dev/migaku commit -m "feat: select first x unknown candidates from JLPT entries"
```

---

## Task 7: AnkiConnect client — `anki_get_deck_config_x` — TDD with mocked HTTP

Generic AnkiConnect POST helper plus the deck-config query. Tests mock `requests.post`.

**Files:**
- Modify: `/Users/distiled/Dev/migaku/migaku_queue.py`
- Test: `/Users/distiled/Dev/migaku/tests/test_anki_client.py`

- [ ] **Step 1: Write failing tests**

`tests/test_anki_client.py`:

```python
from unittest.mock import patch, MagicMock

import pytest

from migaku_queue import anki_post, anki_get_deck_config_x, AnkiError


def _mock_response(json_data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    return resp


def test_anki_post_returns_result_on_success():
    with patch("migaku_queue.requests.post", return_value=_mock_response({"result": 42, "error": None})) as p:
        assert anki_post("deckNames", {}, url="http://localhost:8765") == 42
    p.assert_called_once()
    body = p.call_args.kwargs["json"]
    assert body == {"action": "deckNames", "version": 6, "params": {}}


def test_anki_post_raises_on_error_field():
    with patch("migaku_queue.requests.post", return_value=_mock_response({"result": None, "error": "deck not found"})):
        with pytest.raises(AnkiError) as exc:
            anki_post("getDeckConfig", {})
        assert "deck not found" in str(exc.value)


def test_anki_post_raises_on_http_error():
    with patch("migaku_queue.requests.post", return_value=_mock_response({}, status=500)):
        with pytest.raises(AnkiError):
            anki_post("deckNames", {})


def test_anki_get_deck_config_x_returns_per_day():
    config = {
        "result": {"new": {"perDay": 17}, "id": 1, "name": "Main"},
        "error": None,
    }
    with patch("migaku_queue.requests.post", return_value=_mock_response(config)):
        assert anki_get_deck_config_x("Main deck") == 17
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `.venv/bin/pytest tests/test_anki_client.py -v`
Expected: 4 FAIL with `ImportError: cannot import name 'anki_post'`.

- [ ] **Step 3: Implement AnkiConnect helpers**

Add to `migaku_queue.py` (after the imports at top):

```python
import requests


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
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `.venv/bin/pytest tests/test_anki_client.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git -C /Users/distiled/Dev/migaku add migaku_queue.py tests/test_anki_client.py
git -C /Users/distiled/Dev/migaku commit -m "feat: AnkiConnect client and deck-config query"
```

---

## Task 8: AnkiConnect client — `anki_get_deck_words` — TDD with mocked HTTP

Two-step flow: `findNotes` → note IDs, `notesInfo` (batched 500) → field values. Returns the known set.

**Files:**
- Modify: `/Users/distiled/Dev/migaku/migaku_queue.py`
- Test: `/Users/distiled/Dev/migaku/tests/test_anki_client.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_anki_client.py`:

```python
from migaku_queue import anki_get_deck_words


def test_anki_get_deck_words_returns_known_set():
    note_ids = [1, 2, 3]
    notes_info = [
        {"noteId": 1, "fields": {"Vocabulary-Kanji": {"value": "猫"}, "Vocabulary-Kana": {"value": "ねこ"}}},
        {"noteId": 2, "fields": {"Vocabulary-Kanji": {"value": "学校"}, "Vocabulary-Kana": {"value": "がっこう"}}},
        {"noteId": 3, "fields": {"Vocabulary-Kanji": {"value": ""}, "Vocabulary-Kana": {"value": "いぬ"}}},
    ]
    responses = [
        _mock_response({"result": note_ids, "error": None}),
        _mock_response({"result": notes_info, "error": None}),
    ]
    with patch("migaku_queue.requests.post", side_effect=responses) as p:
        known = anki_get_deck_words("Main deck")
    assert known == {"猫", "ねこ", "学校", "がっこう", "いぬ"}
    # findNotes + one notesInfo call (3 IDs < 500 batch size)
    assert p.call_count == 2


def test_anki_get_deck_words_batches_notes_info_in_groups_of_500():
    note_ids = list(range(1, 1201))  # 1200 notes → 3 batches
    # Each batch returns one note
    notes_info_batch_1 = [{"noteId": 1, "fields": {"Vocabulary-Kanji": {"value": "猫"}, "Vocabulary-Kana": {"value": "ねこ"}}}]
    notes_info_batch_2 = [{"noteId": 501, "fields": {"Vocabulary-Kanji": {"value": "犬"}, "Vocabulary-Kana": {"value": "いぬ"}}}]
    notes_info_batch_3 = [{"noteId": 1001, "fields": {"Vocabulary-Kanji": {"value": "鳥"}, "Vocabulary-Kana": {"value": "とり"}}}]
    responses = [
        _mock_response({"result": note_ids, "error": None}),
        _mock_response({"result": notes_info_batch_1, "error": None}),
        _mock_response({"result": notes_info_batch_2, "error": None}),
        _mock_response({"result": notes_info_batch_3, "error": None}),
    ]
    with patch("migaku_queue.requests.post", side_effect=responses) as p:
        known = anki_get_deck_words("Main deck")
    assert known == {"猫", "ねこ", "犬", "いぬ", "鳥", "とり"}
    assert p.call_count == 4  # 1 findNotes + 3 notesInfo


def test_anki_get_deck_words_empty_deck_returns_empty_set():
    responses = [
        _mock_response({"result": [], "error": None}),
    ]
    with patch("migaku_queue.requests.post", side_effect=responses):
        known = anki_get_deck_words("Main deck")
    assert known == set()
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `.venv/bin/pytest tests/test_anki_client.py -v`
Expected: 3 new tests FAIL with `ImportError: cannot import name 'anki_get_deck_words'`.

- [ ] **Step 3: Implement `anki_get_deck_words`**

Add to `migaku_queue.py`:

```python
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
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `.venv/bin/pytest tests/test_anki_client.py -v`
Expected: 7 PASS (4 + 3).

- [ ] **Step 5: Commit**

```bash
git -C /Users/distiled/Dev/migaku add migaku_queue.py tests/test_anki_client.py
git -C /Users/distiled/Dev/migaku commit -m "feat: pull known-words set from Anki deck via notesInfo batching"
```

---

## Task 9: CLI argument parsing — TDD

`argparse` with all flags from the spec. Bare command produces sensible defaults.

**Files:**
- Modify: `/Users/distiled/Dev/migaku/migaku_queue.py`
- Test: `/Users/distiled/Dev/migaku/tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

`tests/test_cli.py`:

```python
from migaku_queue import parse_args


def test_parse_args_defaults():
    args = parse_args([])
    assert args.deck == "Main deck"
    assert args.count is None  # None means "use Anki deck config"
    assert args.dry_run is False
    assert args.leave_open is True
    assert args.headless is False
    assert args.jlpt_path.endswith("JLPT.json")
    assert args.extension_path == ""  # auto-detect when empty


def test_parse_args_dry_run():
    args = parse_args(["--dry-run"])
    assert args.dry_run is True


def test_parse_args_count_override():
    args = parse_args(["--count", "5"])
    assert args.count == 5


def test_parse_args_no_leave_open():
    args = parse_args(["--no-leave-open"])
    assert args.leave_open is False


def test_parse_args_headless():
    args = parse_args(["--headless"])
    assert args.headless is True


def test_parse_args_extension_path_override():
    args = parse_args(["--extension-path", "/tmp/ext"])
    assert args.extension_path == "/tmp/ext"


def test_parse_args_custom_jlpt_path():
    args = parse_args(["--jlpt-path", "/tmp/x.json"])
    assert args.jlpt_path == "/tmp/x.json"


def test_parse_args_custom_deck():
    args = parse_args(["--deck", "Other deck"])
    assert args.deck == "Other deck"
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: 8 FAIL with `ImportError: cannot import name 'parse_args'`.

- [ ] **Step 3: Implement `parse_args`**

Add to `migaku_queue.py`:

```python
import argparse
import os


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
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Run all tests — verify nothing regressed**

Run: `.venv/bin/pytest -q`
Expected: 37 PASS (22 + 7 + 8).

- [ ] **Step 6: Commit**

```bash
git -C /Users/distiled/Dev/migaku add migaku_queue.py tests/test_cli.py
git -C /Users/distiled/Dev/migaku commit -m "feat: CLI argument parsing with sensible defaults"
```

---

## Task 10: Migaku extension path auto-detection — TDD

Find the installed Migaku extension folder. Default location: `~/Library/Application Support/Google/Chrome/Default/Extensions/lkhiljgmbeecmljiogckofcalncmfnfo/<version>/`. If multiple versions exist, pick the highest.

**Files:**
- Modify: `/Users/distiled/Dev/migaku/migaku_queue.py`
- Test: `/Users/distiled/Dev/migaku/tests/test_cli.py` (add detection tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_cli.py`:

```python
import os
from migaku_queue import detect_extension_path, ExtensionNotFound


def test_detect_extension_path_returns_highest_version(tmp_path):
    ext_root = tmp_path / "Extensions" / "lkhiljgmbeecmljiogckofcalncmfnfo"
    ext_root.mkdir(parents=True)
    (ext_root / "1.30.7.0_0").mkdir()
    (ext_root / "1.30.8.0_0").mkdir()
    (ext_root / "1.30.9.0_0").mkdir()
    result = detect_extension_path(str(ext_root))
    assert result.endswith("1.30.9.0_0")


def test_detect_extension_path_raises_when_missing(tmp_path):
    with __import__("pytest").raises(ExtensionNotFound):
        detect_extension_path(str(tmp_path / "nope"))


def test_detect_extension_path_raises_when_no_version_dirs(tmp_path):
    ext_root = tmp_path / "Extensions" / "lkhiljgmbeecmljiogckofcalncmfnfo"
    ext_root.mkdir(parents=True)
    (ext_root / "somefile.txt").write_text("x")
    with __import__("pytest").raises(ExtensionNotFound):
        detect_extension_path(str(ext_root))
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: 3 new tests FAIL with `ImportError: cannot import name 'detect_extension_path'`.

- [ ] **Step 3: Implement `detect_extension_path`**

Add to `migaku_queue.py`:

```python
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
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: 11 PASS (8 + 3).

- [ ] **Step 5: Verify detection works against the real installed extension**

Run: `.venv/bin/python -c "from migaku_queue import detect_extension_path; print(detect_extension_path())"`
Expected: prints a path ending in `lkhiljgmbeecmljiogckofcalncmfnfo/1.30.8.0_0`.

- [ ] **Step 6: Commit**

```bash
git -C /Users/distiled/Dev/migaku add migaku_queue.py tests/test_cli.py
git -C /Users/distiled/Dev/migaku commit -m "feat: auto-detect installed Migaku extension path"
```

---

## Task 11: Playwright chrome launch — integration

Launch a persistent Chromium context with the Migaku extension loaded. **Not TDD-able** — verified manually.

**Files:**
- Modify: `/Users/distiled/Dev/migaku/migaku_queue.py`

- [ ] **Step 1: Implement `launch_chrome`**

Add to `migaku_queue.py`:

```python
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
    # Wait for the extension's service worker to register, then open a page
    page = context.new_page()
    return pw, context, page
```

- [ ] **Step 2: Verify manually**

Run this from the project directory (will open a Chrome window):
```bash
.venv/bin/python -c "
from migaku_queue import launch_chrome, detect_extension_path, DICTIONARY_URL
import time
ext = detect_extension_path()
print('Extension:', ext)
pw, ctx, page = launch_chrome(ext, '/tmp/migaku-test-profile', headless=False)
page.goto(DICTIONARY_URL)
print('Navigated to:', page.url)
print('Title:', page.title())
time.sleep(5)  # keep window open 5s for visual check
ctx.close()
pw.stop()
"
```

Expected: a Chrome window opens, navigates to the Migaku dictionary URL, prints a title, then closes after 5s. If the page shows a login screen, that's expected for a fresh profile (Task 12 handles login).

If you see an "Early Access" / license warning, note it — this is open question 2 in the spec. We'll address it in the README troubleshooting section.

- [ ] **Step 3: Commit**

```bash
git -C /Users/distiled/Dev/migaku add migaku_queue.py
git -C /Users/distiled/Dev/migaku commit -m "feat: launch persistent Chromium with Migaku extension loaded"
```

---

## Task 12: Dictionary navigation + login detection — integration

Open the dictionary page, detect the login screen, and if present pause for the user to log in.

**Files:**
- Modify: `/Users/distiled/Dev/migaku/migaku_queue.py`

- [ ] **Step 1: Implement `open_dictionary` and `ensure_logged_in`**

Add to `migaku_queue.py`:

```python
def open_dictionary(page):
    """Navigate to the Migaku dictionary page. Returns when the page has loaded."""
    page.goto(DICTIONARY_URL, wait_until="domcontentloaded")
    # Give the SPA a moment to render
    page.wait_for_timeout(1500)


def ensure_logged_in(page):
    """Detect login screen and block until the user logs in.

    Heuristic: if the URL hash contains '/login' or the page has a password
    input visible, prompt the user. Loop until the dictionary view is shown.
    """
    import sys
    max_attempts = 10
    for _ in range(max_attempts):
        url = page.url
        # SPA routes: when logged out, the app redirects to a login route
        if "#/login" in url or "/auth" in url or "login" in url.lower():
            print(
                "Migaku dictionary is showing a login page. "
                "Please log in in the Chrome window, then press Enter here.",
                flush=True,
            )
            input()
            page.wait_for_timeout(2000)
            continue
        # Also check for a password field on the current page
        try:
            if page.locator("input[type='password']").count() > 0:
                print(
                    "A password field is visible. Please log in in the Chrome window, "
                    "then press Enter here.",
                    flush=True,
                )
                input()
                page.wait_for_timeout(2000)
                continue
        except Exception:
            pass
        # Looks logged in
        return
    raise RuntimeError("Still showing a login page after 10 attempts; aborting.")
```

- [ ] **Step 2: Verify manually — fresh profile (login required)**

```bash
rm -rf /tmp/migaku-test-profile-2
.venv/bin/python -c "
from migaku_queue import launch_chrome, detect_extension_path, open_dictionary, ensure_logged_in
ext = detect_extension_path()
pw, ctx, page = launch_chrome(ext, '/tmp/migaku-test-profile-2', headless=False)
open_dictionary(page)
ensure_logged_in(page)
print('Logged in! URL:', page.url)
# leave the window open for inspection
input('Press Enter to close... ')
ctx.close()
pw.stop()
"
```

Expected: Chrome opens, navigates to dictionary. If login screen appears, the terminal prompts you. Log in to Migaku in the Chrome window, then press Enter in the terminal. The script confirms login. Close the window with Enter.

- [ ] **Step 3: Verify manually — reuse profile (no login)**

Run the same command again with the same profile dir — it should skip the login prompt entirely.

- [ ] **Step 4: Commit**

```bash
git -C /Users/distiled/Dev/migaku add migaku_queue.py
git -C /Users/distiled/Dev/migaku commit -m "feat: open dictionary and detect/login gate"
```

---

## Task 13: Word search + add to queue — integration with selector discovery

The "add to queue" button selector is unknown until we inspect the running dictionary page. This task includes a discovery script and then pins the selector as a constant.

**Files:**
- Modify: `/Users/distiled/Dev/migaku/migaku_queue.py`

- [ ] **Step 1: Discovery — inspect the dictionary page DOM for the search input and the add-to-queue button**

Run this discovery script (assumes you're logged in via the profile from Task 12):

```bash
.venv/bin/python -c "
from migaku_queue import launch_chrome, detect_extension_path, open_dictionary, ensure_logged_in
ext = detect_extension_path()
pw, ctx, page = launch_chrome(ext, '/tmp/migaku-test-profile-2', headless=False)
open_dictionary(page)
ensure_logged_in(page)
# Type a word into the search box — first find a likely input
page.wait_for_timeout(2000)
# Dump candidate text inputs
inputs = page.eval_on_selector_all(
    'input[type=text], input[type=search], textarea',
    '''els => els.map(e => ({
        placeholder: e.placeholder,
        name: e.name,
        id: e.id,
        className: e.className,
        visible: e.offsetParent !== null,
    }))'''
)
print('INPUTS:', inputs)
# Type into the first visible one
page.fill('input[type=text]:visible', '猫')
page.wait_for_timeout(1500)
# Now dump all visible buttons and clickable elements that mention 'queue' or 'add'
buttons = page.eval_on_selector_all(
    'button, [role=button], [class*=queue i], [class*=add i]',
    '''els => els.slice(0, 50).map(e => ({
        tag: e.tagName,
        text: (e.innerText || '').slice(0, 60),
        className: e.className,
        title: e.title,
        visible: e.offsetParent !== null,
    }))'''
)
print('BUTTONS:')
for b in buttons:
    print(' ', b)
input('Press Enter to close... ')
ctx.close()
pw.stop()
"
```

Record the output. We're looking for:
1. The search input's selector (likely `input[type=text]` with a recognizable placeholder/class).
2. The "add to queue" button — text containing "queue" or "add", class name matching the BEM convention `CardCreatorQueue__…` or similar.

- [ ] **Step 2: Pin the discovered selectors as constants**

Update `migaku_queue.py` with the discovered values. Replace the placeholders below with what Step 1 found:

```python
# Discovered via manual inspection of the Migaku dictionary page.
# Update these if a Migaku extension update breaks the script.
DICTIONARY_SEARCH_INPUT = 'input[type="text"]'  # TODO: pin from Step 1 output
ADD_TO_QUEUE_BUTTON = 'button:has-text("Add to Queue")'  # TODO: pin from Step 1 output
QUEUE_COUNTER = '[data-queue-count]'  # TODO: pin if a counter exists
```

If Step 1's output reveals better selectors, use those instead.

- [ ] **Step 3: Implement `add_word_to_queue`**

Add to `migaku_queue.py`:

```python
import time


def add_word_to_queue(page, word: str, screenshot_dir: str = DEFAULT_SCREENSHOT_DIR) -> bool:
    """Search for `word` in the dictionary and click 'add to queue'.

    Returns True on success, False on failure. On failure, saves a screenshot.
    """
    # Clear and type the search input
    try:
        page.fill(DICTIONARY_SEARCH_INPUT, "")
        page.fill(DICTIONARY_SEARCH_INPUT, word)
        page.wait_for_timeout(800)  # let results populate
    except Exception as e:
        print(f"  [warn] could not search for {word!r}: {e}")
        _screenshot(page, screenshot_dir, word)
        return False

    # Find and click the add-to-queue button
    try:
        btn = page.locator(ADD_TO_QUEUE_BUTTON).first
        btn.click(timeout=3000)
        page.wait_for_timeout(400)  # let the queue update
        return True
    except Exception as e:
        print(f"  [warn] add-to-queue button not clickable for {word!r}: {e}")
        _screenshot(page, screenshot_dir, word)
        return False


def _screenshot(page, screenshot_dir: str, word: str) -> None:
    os.makedirs(screenshot_dir, exist_ok=True)
    ts = int(time.time())
    safe = word.replace("/", "_")
    path = os.path.join(screenshot_dir, f"{ts}_{safe}.png")
    try:
        page.screenshot(path=path, full_page=True)
        print(f"  [screenshot] saved to {path}")
    except Exception as e:
        print(f"  [warn] could not save screenshot: {e}")
```

- [ ] **Step 4: Verify manually — add one word to the queue**

```bash
.venv/bin/python -c "
from migaku_queue import launch_chrome, detect_extension_path, open_dictionary, ensure_logged_in, add_word_to_queue
ext = detect_extension_path()
pw, ctx, page = launch_chrome(ext, '/tmp/migaku-test-profile-2', headless=False)
open_dictionary(page)
ensure_logged_in(page)
ok = add_word_to_queue(page, '猫')
print('Added:', ok)
input('Press Enter to close... ')
ctx.close()
pw.stop()
"
```

Expected: the dictionary searches for 猫, the script prints `Added: True`, and visually the queue counter in the Migaku UI increments by 1.

- [ ] **Step 5: Commit**

```bash
git -C /Users/distiled/Dev/migaku add migaku_queue.py
git -C /Users/distiled/Dev/migaku commit -m "feat: search a word in the Migaku dictionary and click add-to-queue"
```

---

## Task 14: Main orchestration — integration

Wire everything together. Pulls X from Anki, builds the known set, selects candidates, optionally drives Chrome.

**Files:**
- Modify: `/Users/distiled/Dev/migaku/migaku_queue.py`

- [ ] **Step 1: Implement `main`**

Replace the stub `main` in `migaku_queue.py`:

```python
def main(argv=None) -> int:
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
            jlpt_data = __import__("json").load(f)
    except (OSError, ValueError) as e:
        print(f"Error reading {args.jlpt_path}: {e}")
        return 1
    entries = parse_jlpt_json(jlpt_data)
    print(f"JLPT.json: {len(entries)} parsed entries")

    # 3. Build known set
    try:
        known_set = anki_get_deck_words(args.deck, url=args.anki_url)
    except AnkiError as e:
        print(f"Error: {e}")
        return 1
    print(f"Known words in {args.deck!r}: {len(known_set)}")

    # 4. Select candidates
    candidates = select_candidates(entries, known_set, x)
    if len(candidates) < x:
        print(f"Warning: only {len(candidates)} candidates available (requested {x}).")

    print(f"Selected {len(candidates)} new words:")
    for word, reading in candidates:
        print(f"  {word}  ({reading})")

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
        # Pre-pull a few extra candidates in case some fail
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

        print(f"Added {added}/{len(candidates)} words to the Migaku queue.")
        if not args.leave_open:
            ctx.close()
        else:
            print("Leaving the dictionary window open. Press Ctrl+C in terminal to close.")
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
```

- [ ] **Step 2: Verify `--dry-run` works end-to-end**

Make sure Anki is open with the "Main deck" available.

Run: `.venv/bin/python migaku_queue.py --dry-run`
Expected output (numbers approximate):
```
Anki deck 'Main deck': new.perDay = 17
JLPT.json: 8134 parsed entries
Known words in 'Main deck': ~13000
Selected 17 new words:
  <word>  (<reading>)
  ...
Dry run — not touching Chrome.
```

If Anki isn't running, expect: `Error: AnkiConnect not reachable at http://localhost:8765: ...` and exit code 1.

- [ ] **Step 3: Verify a real run with a small count**

Run: `.venv/bin/python migaku_queue.py --count 2`
Expected: prints selection, launches Chrome, navigates to dictionary, adds 2 words to queue, then idles (leaves window open). Press Ctrl+C to exit. Check that the queue counter in Migaku's UI increased by 2.

- [ ] **Step 4: Verify failure path — selector broken**

Temporarily break the selector constant and run with `--count 1`:
```bash
.venv/bin/python -c "
import migaku_queue
migaku_queue.ADD_TO_QUEUE_BUTTON = 'button:has-text(\"nonexistent-button-text-xyz\")'
import sys
sys.argv = ['migaku_queue.py', '--count', '1']
raise SystemExit(migaku_queue.main())
"
```

Expected: prints `[warn] add-to-queue button not clickable...`, saves a screenshot, then "Three consecutive failures — Aborting."

Revert the constant after.

- [ ] **Step 5: Run all unit tests — verify nothing regressed**

Run: `.venv/bin/pytest -q`
Expected: all unit tests PASS (37 + 3 from Task 10 = 40).

- [ ] **Step 6: Commit**

```bash
git -C /Users/distiled/Dev/migaku add migaku_queue.py
git -C /Users/distiled/Dev/migaku commit -m "feat: wire main pipeline from Anki through JLPT to Migaku queue"
```

---

## Task 15: README

**Files:**
- Modify: `/Users/distiled/Dev/migaku/README.md`

- [ ] **Step 1: Write the README**

Overwrite `README.md`:

```markdown
# migaku-queue

Top up the Migaku dictionary queue with new Japanese words from `JLPT.json`,
skipping words already in your Anki "Main deck". Drives the Migaku Chrome
extension with Playwright.

## What it does

1. Reads the daily new-card count (`new.perDay`) from your Anki "Main deck" via AnkiConnect. This is `X`.
2. Pulls every word currently in the deck (surface + reading) into an in-memory set.
3. Walks `JLPT.json` in order (N5 → N4 → N3 → N2 → N1), skipping words already in the deck.
4. Takes the first `X` survivors.
5. Launches Chrome with the Migaku extension loaded, opens the dictionary,
   searches each word, clicks "add to queue", and leaves the dictionary window open.

## One-time setup

```bash
cd /Users/distiled/Dev/migaku
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
```

Anki must be open with AnkiConnect enabled (default port 8765). The "Main deck"
and the Migaku Anki add-on should be installed (you already have both).

## First run

The script will open Chrome with the Migaku extension loaded. **Log in to your
Migaku account in the Chrome window when prompted**, then press Enter in the
terminal. The session is saved to `~/Library/Application Support/Migaku-Automation/chrome-profile/`
so subsequent runs won't ask you to log in again.

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

## Troubleshooting

### "Migaku extension not found at ..."

The script looks for the extension at
`~/Library/Application Support/Google/Chrome/Default/Extensions/lkhiljgmbeecmljiogckofcalncmfnfo/`.
If you installed Migaku in a different Chrome profile or it's missing, pass
`--extension-path /path/to/extension/version-folder`.

### "Three consecutive failures — extension UI may have changed"

The "add to queue" button selector is pinned in `migaku_queue.py` as
`ADD_TO_QUEUE_BUTTON`. If Migaku updates their UI, this selector breaks. Check
the screenshots saved to `./screenshots/` to find the new selector and update
the constant.

### Migaku shows an "Early Access" or license warning

The extension may detect it's being loaded as unpacked and show a license gate.
If this blocks you, the fallback is to use your normal Chrome profile via
Chrome's remote debugging:

```bash
# Close all Chrome windows, then:
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/Library/Application Support/Google/Chrome/Default"
```

Then connect Playwright to `http://localhost:9222` instead of launching a
persistent context. This is a troubleshooting path, not the default flow —
update the `launch_chrome` function if you need it.

### "AnkiConnect not reachable at http://localhost:8765"

Open Anki. AnkiConnect only works while Anki is running.

### Login prompt every run

The persistent profile at
`~/Library/Application Support/Migaku-Automation/chrome-profile/` stores your
session. If you deleted it, or if Migaku's session expired, you'll be prompted
to log in again. Just log in and press Enter.

### Headless mode doesn't load the extension

Chrome historically disabled extensions in headless mode. If `--headless`
launches but the extension page is blank, run without `--headless` (the
default). Headless mode is a future nice-to-have, not the primary flow.

## Running the tests

```bash
.venv/bin/pytest -q
```

Unit tests cover the pure functions (JLPT parsing, HTML stripping, known-set
building, candidate selection, CLI parsing, AnkiConnect client with mocked
HTTP). The Playwright integration is verified manually.

## Files

- `migaku_queue.py` — the script
- `requirements.txt` — runtime deps (`requests`, `playwright`)
- `requirements-dev.txt` — adds `pytest`
- `tests/` — unit tests and fixtures
- `docs/superpowers/specs/` — design spec
- `docs/superpowers/plans/` — this implementation plan
```

- [ ] **Step 2: Commit**

```bash
git -C /Users/distiled/Dev/migaku add README.md
git -C /Users/distiled/Dev/migaku commit -m "docs: README with setup, usage, and troubleshooting"
```

---

## Final verification

- [ ] **Step 1: Run all unit tests one more time**

Run: `.venv/bin/pytest -q`
Expected: all tests PASS.

- [ ] **Step 2: Run a real dry-run**

Make sure Anki is open, then:

Run: `.venv/bin/python migaku_queue.py --dry-run`
Expected: prints X (= 17), the size of the known set, and the 17 selected candidates. Exit code 0.

- [ ] **Step 3: Run a real full run**

Run: `.venv/bin/python migaku_queue.py`
Expected: launches Chrome, navigates to the Migaku dictionary, adds 17 words to the queue, leaves the window open. Visually verify the queue counter increased by 17.

- [ ] **Step 4: Final commit if any tweaks were made**

```bash
git -C /Users/distiled/Dev/migaku add -A
git -C /Users/distiled/Dev/migaku commit -m "chore: post-verification tweaks"
```

---

## Self-Review (run by plan author after writing)

**Spec coverage:**

- ✅ Get X from Anki deck config → Task 7 + Task 14
- ✅ Pull all words from "Main deck" → Task 8 + Task 14
- ✅ Build known set (surface ∪ reading) → Task 4 + Task 5
- ✅ Parse JLPT.json (skip markers, empty rows) → Task 2
- ✅ Strip HTML from Anki fields → Task 3
- ✅ Sequential by JLPT level → Task 2 (preserves order) + Task 6
- ✅ Take first X unknown → Task 6
- ✅ Match on surface or reading → Task 5
- ✅ Playwright + load extension → Task 11
- ✅ Persistent profile + login detection → Task 12
- ✅ Search each word, click add-to-queue → Task 13
- ✅ Skip on failure, pull next candidate → Task 14 (consecutive-failure abort)
- ✅ 3-strike abort with screenshots → Task 13 (`_screenshot`) + Task 14
- ✅ Leave dictionary open → Task 14
- ✅ Stdout summary → Task 14
- ✅ CLI flags: `--dry-run`, `--count`, `--no-leave-open`, `--extension-path`, `--headless` → Task 9
- ✅ One-time setup documented → Task 15
- ✅ Troubleshooting (Early Access / CDP fallback) → Task 15
- ✅ Error handling for AnkiConnect not running, deck missing, JLPT missing, extension missing, fewer than X candidates, no results, button not found, not logged in → Tasks 7, 8, 10, 14
- ✅ Unit tests for pure functions → Tasks 2–6, 7–9, 10
- ✅ File layout matches spec → Task 1

**Placeholder scan:** Three `TODO: pin from Step 1 output` markers in Task 13 Step 2. These are intentional — Task 13 Step 1 is a discovery script whose output determines the actual values. They are not plan placeholders; they are instructions to the implementer. No other red flags.

**Type consistency:**
- `parse_jlpt_json(data: list) -> List[Tuple[str, str, str]]` — used consistently in Tasks 2, 6, 14.
- `build_known_set(notes_info: list) -> Set[str]` — used in Tasks 4, 8, 14.
- `is_known(word, reading, known_set) -> bool` — used in Tasks 5, 6.
- `select_candidates(entries, known_set, x) -> List[Tuple[str, str]]` — used in Tasks 6, 14.
- `anki_post(action, params, url=...) -> Any` — used in Tasks 7, 8.
- `anki_get_deck_config_x(deck, url) -> int` — used in Tasks 7, 14.
- `anki_get_deck_words(deck, url) -> Set[str]` — used in Tasks 8, 14.
- `parse_args(argv) -> argparse.Namespace` — used in Tasks 9, 14.
- `detect_extension_path(extensions_dir) -> str` — used in Tasks 10, 14.
- `launch_chrome(extension_path, profile_dir, headless) -> (pw, ctx, page)` — used in Tasks 11, 14.
- `open_dictionary(page)` — used in Tasks 12, 14.
- `ensure_logged_in(page)` — used in Tasks 12, 14.
- `add_word_to_queue(page, word, screenshot_dir) -> bool` — used in Tasks 13, 14.

All signatures match. No name drift.

---
