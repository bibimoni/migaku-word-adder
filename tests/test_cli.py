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


import os
from migaku_queue import detect_extension_path, ExtensionNotFound


def test_detect_extension_path_returns_highest_version(tmp_path):
    ext_root = tmp_path / "Extensions" / "lkhiljgmbeecmljiogckofcalncmfnfo"
    ext_root.mkdir(parents=True)
    (ext_root / "1.30.7.0_0").mkdir()
    (ext_root / "1.30.8.0_0").mkdir()
    (ext_root / "1.30.9.0_0").mkdir()
    result = detect_extension_path(str(tmp_path / "Extensions"))
    assert result.endswith("1.30.9.0_0")


def test_detect_extension_path_raises_when_missing(tmp_path):
    with __import__("pytest").raises(ExtensionNotFound):
        detect_extension_path(str(tmp_path / "nope"))


def test_detect_extension_path_raises_when_no_version_dirs(tmp_path):
    ext_root = tmp_path / "Extensions" / "lkhiljgmbeecmljiogckofcalncmfnfo"
    ext_root.mkdir(parents=True)
    (ext_root / "somefile.txt").write_text("x")
    with __import__("pytest").raises(ExtensionNotFound):
        detect_extension_path(str(tmp_path / "Extensions"))
