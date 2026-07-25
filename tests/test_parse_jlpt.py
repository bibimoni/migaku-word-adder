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
