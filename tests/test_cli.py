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
