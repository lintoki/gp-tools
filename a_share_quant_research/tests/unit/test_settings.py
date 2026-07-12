from pathlib import Path

import pytest

from a_share_research.settings import load_settings


def _write_yaml(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_load_settings_reads_factor_weights(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "factors.yaml", "weights:\n  trend: 0.6\n  relative_strength: 0.4\n")
    _write_yaml(tmp_path / "universe.yaml", "main_board_only: true\n")
    _write_yaml(tmp_path / "quality.yaml", "max_attempts: 3\n")
    _write_yaml(tmp_path / "providers.yaml", "dataset_deadline_seconds: 60\n")
    _write_yaml(tmp_path / "backtest.yaml", "lot_size: 100\n")

    settings = load_settings(tmp_path)

    assert sum(settings.factor_weights.values()) == pytest.approx(1.0)
    assert settings.max_attempts == 3
    assert settings.lot_size == 100


def test_load_settings_rejects_weights_that_do_not_sum_to_one(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "factors.yaml", "weights:\n  trend: 0.7\n")
    _write_yaml(tmp_path / "universe.yaml", "main_board_only: true\n")
    _write_yaml(tmp_path / "quality.yaml", "max_attempts: 3\n")
    _write_yaml(tmp_path / "providers.yaml", "dataset_deadline_seconds: 60\n")
    _write_yaml(tmp_path / "backtest.yaml", "lot_size: 100\n")

    with pytest.raises(ValueError, match="factor weights must sum to 1"):
        load_settings(tmp_path)
