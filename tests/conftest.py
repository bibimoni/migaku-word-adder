from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def pytest_configure():
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    sys.path.insert(0, str(Path(__file__).parent.parent))


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")
