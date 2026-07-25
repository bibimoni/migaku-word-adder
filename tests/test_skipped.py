import os

from migaku_queue import load_skipped, save_skipped


def test_load_skipped_missing_file_returns_empty(tmp_path):
    assert load_skipped(str(tmp_path / "nope.txt")) == set()


def test_load_skipped_reads_lines(tmp_path):
    p = tmp_path / "skipped.txt"
    p.write_text("猫\n犬\n鳥\n", encoding="utf-8")
    assert load_skipped(str(p)) == {"猫", "犬", "鳥"}


def test_load_skipped_ignores_comments_and_blanks(tmp_path):
    p = tmp_path / "skipped.txt"
    p.write_text("# comment\n\n猫\n\n# another\n犬\n", encoding="utf-8")
    assert load_skipped(str(p)) == {"猫", "犬"}


def test_save_skipped_appends_new_words(tmp_path):
    p = tmp_path / "skipped.txt"
    p.write_text("猫\n", encoding="utf-8")
    save_skipped({"猫", "犬", "鳥"}, str(p))
    assert load_skipped(str(p)) == {"猫", "犬", "鳥"}


def test_save_skipped_no_new_does_not_touch_file(tmp_path):
    p = tmp_path / "skipped.txt"
    p.write_text("猫\n犬\n", encoding="utf-8")
    mtime_before = os.path.getmtime(p)
    save_skipped({"猫", "犬"}, str(p))
    mtime_after = os.path.getmtime(p)
    assert mtime_before == mtime_after


def test_save_skipped_creates_file_if_missing(tmp_path):
    p = tmp_path / "skipped.txt"
    save_skipped({"猫"}, str(p))
    assert p.exists()
    assert load_skipped(str(p)) == {"猫"}
