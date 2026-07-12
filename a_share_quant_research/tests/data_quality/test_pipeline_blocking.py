from datetime import UTC, datetime, timedelta

from a_share_research.pipeline import DailyResearchPipeline
from a_share_research.quality.contracts import DataContract
from a_share_research.quality.gate import QualityGate

AS_OF = datetime(2026, 7, 12, tzinfo=UTC)


class FailIfCalled:
    def __getattr__(self, name):
        raise AssertionError(f"blocked pipeline called {name}")


def test_blocked_data_never_calls_compute_or_text_analysis() -> None:
    pipeline = DailyResearchPipeline(
        quality_gate=QualityGate(),
        contracts=(
            DataContract(
                dataset="daily_bars",
                required_columns=("instrument_id", "close"),
                primary_key=("instrument_id",),
                max_age=timedelta(days=1),
            ),
        ),
        data_lake=FailIfCalled(),
        factor_engine=FailIfCalled(),
        scorer=FailIfCalled(),
        context_engine=FailIfCalled(),
        analysis_hook=FailIfCalled(),
        factor_weights={"trend": 1.0},
    )

    report = pipeline.run(
        AS_OF,
        batches=(),
        run_id="TEST_ONLY_blocked",
        artifact_hashes={"TEST_ONLY_input": "a" * 64},
    )

    assert report.status == "BLOCKED_DATA"
    assert report.candidates == ()
    assert report.data_integrity.errors[0].code == "DATASET_MISSING"
