from migaku_queue import save_last_selection, load_last_selection


def test_save_and_load_last_selection(tmp_path):
    p = tmp_path / "last.txt"
    candidates = [("猫", "ねこ"), ("犬", "いぬ"), ("鳥", "とり")]
    save_last_selection(candidates, str(p))
    loaded = load_last_selection(str(p))
    assert loaded == candidates


def test_load_last_selection_missing_file(tmp_path):
    assert load_last_selection(str(tmp_path / "nope.txt")) == []


def test_load_last_selection_ignores_comments_and_blanks(tmp_path):
    p = tmp_path / "last.txt"
    p.write_text("# comment\n\n猫\tねこ\n\n# another\n犬\tいぬ\n", encoding="utf-8")
    assert load_last_selection(str(p)) == [("猫", "ねこ"), ("犬", "いぬ")]


def test_save_last_selection_overwrites(tmp_path):
    p = tmp_path / "last.txt"
    save_last_selection([("猫", "ねこ")], str(p))
    save_last_selection([("犬", "いぬ")], str(p))
    assert load_last_selection(str(p)) == [("犬", "いぬ")]


def test_save_last_selection_empty_list_creates_empty_file(tmp_path):
    p = tmp_path / "last.txt"
    save_last_selection([], str(p))
    assert p.exists()
    assert load_last_selection(str(p)) == []
