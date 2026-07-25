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
