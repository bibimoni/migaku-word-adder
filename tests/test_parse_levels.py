from migaku_queue import parse_levels


def test_parse_levels_single():
    assert parse_levels("N3") == ["N3"]


def test_parse_levels_multi_comma():
    assert parse_levels("N3,N4") == ["N3", "N4"]


def test_parse_levels_multi_with_spaces():
    assert parse_levels("N3, N4, N5") == ["N3", "N4", "N5"]


def test_parse_levels_all_returns_empty():
    assert parse_levels("all") == []
    assert parse_levels("ALL") == []


def test_parse_levels_all_among_others_returns_empty():
    # "all" overrides everything
    assert parse_levels("N3,all") == []


def test_parse_levels_lowercase_normalized():
    assert parse_levels("n3,n4") == ["N3", "N4"]


def test_parse_levels_empty_string():
    assert parse_levels("") == []


def test_parse_levels_none():
    assert parse_levels(None) == []
