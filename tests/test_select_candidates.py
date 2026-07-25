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


def test_select_candidates_negative_x_returns_empty():
    entries = [("N5", "猫", "ねこ")]
    assert select_candidates(entries, set(), x=-1) == []


def test_select_candidates_dedupes_within_input():
    # If the same word appears twice in JLPT.json, only the first occurrence is selected
    entries = [("N5", "猫", "ねこ"), ("N4", "猫", "ねこ")]
    result = select_candidates(entries, set(), x=2)
    assert result == [("猫", "ねこ")]


def test_select_candidates_level_filter():
    entries = [
        ("N5", "猫", "ねこ"),
        ("N4", "学校", "がっこう"),
        ("N3", "読む", "よむ"),
        ("N2", "複雑", "ふくざつ"),
    ]
    # Only N3
    assert select_candidates(entries, set(), x=10, level="N3") == [("読む", "よむ")]
    # Only N4
    assert select_candidates(entries, set(), x=10, level="N4") == [("学校", "がっこう")]


def test_select_candidates_level_all_means_no_filter():
    entries = [("N5", "猫", "ねこ"), ("N4", "学校", "がっこう")]
    assert select_candidates(entries, set(), x=10, level="all") == [("猫", "ねこ"), ("学校", "がっこう")]
    assert select_candidates(entries, set(), x=10, level=None) == [("猫", "ねこ"), ("学校", "がっこう")]


def test_select_candidates_level_exhausted_returns_fewer():
    entries = [("N5", "猫", "ねこ"), ("N4", "学校", "がっこう")]
    # Only 1 N4 entry
    assert select_candidates(entries, set(), x=5, level="N4") == [("学校", "がっこう")]
