import pytest

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
    assert args.level == "all"  # default from config.yaml or "all"
    assert args.no_confirm is False  # interactive selection by default


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


def test_parse_args_level_override():
    args = parse_args(["--level", "N3"])
    assert args.level == "N3"


def test_parse_args_no_confirm():
    args = parse_args(["--no-confirm"])
    assert args.no_confirm is True


def test_parse_args_config_file(tmp_path):
    cfg = tmp_path / "myconfig.yaml"
    cfg.write_text("level: N2\ncount: 3\ndeck: Custom\n", encoding="utf-8")
    args = parse_args(["--config", str(cfg)])
    assert args.level == "N2"
    assert args.count == 3
    assert args.deck == "Custom"


def test_parse_args_cli_overrides_config(tmp_path):
    cfg = tmp_path / "myconfig.yaml"
    cfg.write_text("level: N2\ncount: 3\n", encoding="utf-8")
    args = parse_args(["--config", str(cfg), "--level", "N1", "--count", "10"])
    assert args.level == "N1"
    assert args.count == 10


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
    with pytest.raises(ExtensionNotFound):
        detect_extension_path(str(tmp_path / "nope"))


def test_detect_extension_path_raises_when_no_version_dirs(tmp_path):
    ext_root = tmp_path / "Extensions" / "lkhiljgmbeecmljiogckofcalncmfnfo"
    ext_root.mkdir(parents=True)
    (ext_root / "somefile.txt").write_text("x")
    with pytest.raises(ExtensionNotFound):
        detect_extension_path(str(tmp_path / "Extensions"))
