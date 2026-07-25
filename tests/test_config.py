import os
import textwrap

from migaku_queue import load_config


def test_load_config_missing_file_returns_empty(tmp_path):
    assert load_config(str(tmp_path / "nonexistent.yaml")) == {}


def test_load_config_reads_level(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("level: N3\n", encoding="utf-8")
    assert load_config(str(p)) == {"level": "N3"}


def test_load_config_reads_multiple_keys(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("level: N3\ncount: 5\ndeck: Other\n", encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg == {"level": "N3", "count": 5, "deck": "Other"}


def test_load_config_empty_file_returns_empty(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("", encoding="utf-8")
    assert load_config(str(p)) == {}


def test_load_config_non_dict_yaml_returns_empty(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("- just\n- a\n- list\n", encoding="utf-8")
    assert load_config(str(p)) == {}


def test_load_config_auto_creates_from_template(tmp_path):
    p = tmp_path / "config.yaml"
    assert not p.exists()
    result = load_config(str(p))
    # Returns empty dict (template has only commented-out values except level: all)
    assert result == {"level": "all"} or result == {}
    # File should now exist with template content
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert "level: all" in content
    assert "count:" in content  # template mentions count (commented)


def test_load_config_multi_level_in_yaml(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("level: N3,N4\ncount: 5\n", encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg["level"] == "N3,N4"
    # parse_levels should handle it
    from migaku_queue import parse_levels
    assert parse_levels(cfg["level"]) == ["N3", "N4"]
