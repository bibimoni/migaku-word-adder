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
