from datetime import UTC, datetime, timedelta

from a_share_research.context.models import ContextStatus, GlobalContext, MarketContext
from a_share_research.core.models import DataBatch, FieldProvenance
from a_share_research.evidence.models import VerificationResult, VerificationStatus
from a_share_research.factors.base import FactorResult, FactorStatus
from a_share_research.factors.scoring import CandidateScore, CandidateStatus
from a_share_research.pipeline import DailyResearchPipeline
from a_share_research.quality.contracts import DataContract
from a_share_research.quality.gate import QualityGate
from a_share_research.universe.rules import TradeFlags, UniverseResult

AS_OF = datetime(2026, 7, 12, tzinfo=UTC)


class MemoryLake:
    def write_normalized(self, batch):
        return batch.dataset

    def publish_curated(self, artifacts, quality_report):
        assert quality_report.status == "PASS"
        return "TEST_ONLY_snapshot"


class StaticFactors:
    def compute(self, snapshot, as_of):
        return [
            FactorResult(
                instrument_id=f"SH60000{index}",
                factor_name="trend",
                raw_value=float(index),
                z_value=float(index),
                score=float(100 - index),
                as_of=as_of,
                dependencies=("daily_bars.close",),
                status=FactorStatus.READY,
            )
            for index in range(6)
        ]


class StaticScorer:
    def score(self, results, weights):
        return [
            CandidateScore(
                instrument_id=result.instrument_id,
                composite_score=result.score,
                status=CandidateStatus.READY,
            )
            for result in results
        ]


class StaticContext:
    def compute(self, snapshot, as_of):
        return GlobalContext(
            status=ContextStatus.READY,
            as_of=as_of,
            market=MarketContext(
                index_trend="UP",
                volatility_direction="DOWN",
                yield_direction="DOWN",
                credit_direction="DOWN",
                latest_observations={},
            ),
            industries=(),
            futures=(),
        )


class StaticAnalysis:
    def __call__(self, context, factors, evidence):
        return {instrument: "TEST_ONLY explanation" for instrument in evidence}


def batch() -> DataBatch:
    provenance = FieldProvenance(
        source_name="TEST_ONLY_source",
        source_uri="https://example.invalid/test-only",
        source_record_id="1",
        fetched_at=AS_OF,
        effective_at=AS_OF,
        available_at=AS_OF,
        run_id="TEST_ONLY_run",
        payload_sha256="f" * 64,
    )
    row = {"instrument_id": "SH600000", "close": 10.0}
    return DataBatch(
        dataset="daily_bars",
        rows=(row,),
        field_provenance={field: provenance for field in row},
        provider_version="TEST_ONLY_1",
    )


def evidence() -> dict[str, VerificationResult]:
    return {
        f"SH60000{index}": VerificationResult(
            event_id=f"event-{index}",
            entity_id=f"SH60000{index}",
            status=VerificationStatus.VERIFIED,
            confidence=1.0,
            catalyst_score=1.0,
            core_evidence_ids=(f"evidence-{index}",),
            counter_evidence_ids=(),
            independent_c_sources=0,
        )
        for index in range(6)
    }


def test_successful_pipeline_limits_candidates_to_five() -> None:
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
        data_lake=MemoryLake(),
        factor_engine=StaticFactors(),
        scorer=StaticScorer(),
        context_engine=StaticContext(),
        analysis_hook=StaticAnalysis(),
        factor_weights={"trend": 1.0},
    )
    report = pipeline.run(
        AS_OF,
        batches=(batch(),),
        factor_snapshot=object(),
        context_snapshot=object(),
        evidence_results=evidence(),
        universe_result=UniverseResult(
            as_of=AS_OF.date(),
            eligible=tuple(f"SH60000{index}" for index in range(6)),
            excluded={},
            trade_flags={f"SH60000{index}": TradeFlags() for index in range(6)},
        ),
        artifact_hashes={"TEST_ONLY_input": "a" * 64},
        run_id="TEST_ONLY_run",
    )
    assert report.status == "SUCCEEDED"
    assert len(report.candidates) == 5
    assert report.candidates[0].instrument_id == "SH600000"
