import datetime as dt
from pathlib import Path

from pomodoro import storage
from pomodoro.storage import SavedState


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    assert storage.load(tmp_path / "state.json") == SavedState()


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "state.json"
    state = SavedState(bank_seconds=1234.5, interest_date=dt.date(2026, 10, 26), auto_start=False, always_on_top=True)
    storage.save(path, state)
    assert storage.load(path) == state
    assert not path.with_suffix(".tmp").exists()


def test_corrupt_file_gives_defaults(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")
    assert storage.load(path) == SavedState()


def test_bad_values_give_defaults(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text('{"bank_seconds": "lots", "interest_date": "yesterday"}', encoding="utf-8")
    assert storage.load(path) == SavedState()


def test_negative_balance_is_clamped(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text('{"bank_seconds": -50}', encoding="utf-8")
    assert storage.load(path).bank_seconds == 0
