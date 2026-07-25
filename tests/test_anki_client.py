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
