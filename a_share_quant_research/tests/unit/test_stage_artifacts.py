import json
from pathlib import Path

import pytest

from a_share_research.cli import _read_stage_artifact, _write_stage_artifact
from a_share_research.quality.gate import QualityReport, QualityStatus


def gate() -> QualityReport:
    return QualityReport(
        status=QualityStatus.PASS,
        run_ids=("TEST_ONLY_run",),
        dataset_hashes={"daily_bars": ("a" * 64,)},
        artifact_hashes={"source": "b" * 64},
    )


def test_stage_artifact_detects_payload_tampering(tmp_path: Path) -> None:
    path = tmp_path / "factors.json"
    _write_stage_artifact(
        path,
        run_id="TEST_ONLY_run",
        gate=gate(),
        artifact_type="factors",
        payload=[{"score": 80.0}],
    )
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["payload"][0]["score"] = 99.0
    path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(ValueError, match="payload hash mismatch"):
        _read_stage_artifact(
            path,
            run_id="TEST_ONLY_run",
            gate=gate(),
            artifact_type="factors",
        )
