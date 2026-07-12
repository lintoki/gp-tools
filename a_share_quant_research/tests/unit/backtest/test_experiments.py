from pathlib import Path

from a_share_research.backtest.experiments import ExperimentLedger


def test_failed_experiment_is_persisted(tmp_path: Path) -> None:
    ledger = ExperimentLedger(tmp_path / "experiments.duckdb")
    ledger.record_failure(
        experiment_id="TEST_ONLY_exp_1",
        config_hash="a" * 64,
        data_manifest_hash="b" * 64,
        error=ValueError("bad data"),
    )
    record = ledger.get("TEST_ONLY_exp_1")
    assert record["status"] == "FAILED"
    assert record["error_message"] == "bad data"
