from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from a_share_research.evidence.models import VerificationResult, VerificationStatus
from a_share_research.factors.base import FactorResult
from a_share_research.factors.scoring import CandidateStatus
from a_share_research.quality.gate import QualityError
from a_share_research.reporting.models import (
    CandidateConclusion,
    CandidateReport,
    DailyReport,
    DataIntegrity,
    FactorDetail,
    IndustryRank,
    ReportStatus,
)
from a_share_research.universe.rules import UniverseResult


class DailyResearchPipeline:
    def __init__(
        self,
        *,
        quality_gate,
        contracts,
        data_lake,
        factor_engine,
        scorer,
        context_engine,
        analysis_hook,
        factor_weights: dict[str, float],
    ) -> None:
        self.quality_gate = quality_gate
        self.contracts = contracts
        self.data_lake = data_lake
        self.factor_engine = factor_engine
        self.scorer = scorer
        self.context_engine = context_engine
        self.analysis_hook = analysis_hook
        self.factor_weights = factor_weights

    def run(
        self,
        as_of: datetime,
        *,
        batches,
        run_id: str,
        factor_snapshot: Any | None = None,
        context_snapshot: Any | None = None,
        evidence_results: dict[str, VerificationResult] | None = None,
        universe_result: UniverseResult | None = None,
        artifact_hashes: dict[str, str] | None = None,
    ) -> DailyReport:
        if not artifact_hashes:
            raise ValueError("authorized artifact hashes are required")
        quality = self.quality_gate.validate(batches, self.contracts, as_of, artifact_hashes=artifact_hashes)
        if quality.status != "PASS":
            return DailyReport.blocked(run_id=run_id, as_of=as_of, errors=quality.blocking_errors)
        if quality.run_ids != (run_id,):
            return DailyReport.blocked(
                run_id=run_id,
                as_of=as_of,
                errors=(
                    QualityError(
                        code="RUN_ID_MISMATCH",
                        dataset="run_manifest",
                        message=f"validated run IDs {quality.run_ids} do not match {run_id}",
                    ),
                ),
            )

        artifacts = [self.data_lake.write_normalized(batch) for batch in batches]
        self.data_lake.publish_curated(artifacts, quality)
        snapshot_id = quality.snapshot_id()
        if factor_snapshot is None or context_snapshot is None or universe_result is None:
            raise ValueError("validated factor, context and universe snapshots are required")
        if universe_result.as_of != as_of.date():
            raise ValueError("universe as_of must match pipeline as_of")
        context = self.context_engine.compute(context_snapshot, as_of)
        factors = self.factor_engine.compute(factor_snapshot, as_of)
        scores = self.scorer.score(factors, self.factor_weights)
        evidence_results = evidence_results or {}
        explanations = self.analysis_hook(context, factors, evidence_results)
        candidates = self._candidates(scores, factors, evidence_results, explanations, universe_result)
        industries = self._industry_ranking(context)
        market_environment = context.model_dump(mode="json")
        return DailyReport(
            run_id=run_id,
            as_of=as_of,
            status=ReportStatus.SUCCEEDED,
            conclusion="进入候选池" if candidates else "不推荐：没有股票通过全部门禁",
            data_integrity=DataIntegrity(status="PASS", snapshot_id=snapshot_id),
            market_environment=market_environment,
            industry_ranking=industries,
            candidates=candidates,
            required_factors=tuple(self.factor_weights),
            factor_weights=self.factor_weights,
            known_issues=(
                "系统仅提供研究候选和风险分析，不连接券商、不自动下单、不承诺收益。",
                "历史同类信号统计不足时不会填充或猜测。",
            ),
        )

    @staticmethod
    def _candidates(
        scores, factors, evidence_results, explanations, universe_result
    ) -> tuple[CandidateReport, ...]:
        by_instrument: dict[str, list[FactorResult]] = defaultdict(list)
        for factor in factors:
            by_instrument[factor.instrument_id].append(factor)
        eligible = []
        for score in scores:
            evidence = evidence_results.get(score.instrument_id)
            if (
                score.status != CandidateStatus.READY
                or score.composite_score is None
                or evidence is None
                or evidence.status != VerificationStatus.VERIFIED
                or evidence.entity_id != score.instrument_id
                or score.instrument_id not in universe_result.eligible
            ):
                continue
            eligible.append((score, evidence))
        eligible.sort(key=lambda item: (-float(item[0].composite_score), item[0].instrument_id))
        reports = []
        for score, evidence in eligible[:5]:
            details = tuple(
                FactorDetail(
                    name=factor.factor_name,
                    raw_value=factor.raw_value,
                    z_value=factor.z_value,
                    score=factor.score,
                    as_of=factor.as_of,
                    dependencies=factor.dependencies,
                )
                for factor in sorted(by_instrument[score.instrument_id], key=lambda item: item.factor_name)
            )
            reports.append(
                CandidateReport(
                    instrument_id=score.instrument_id,
                    composite_score=float(score.composite_score),
                    conclusion=CandidateConclusion.ENTER_POOL,
                    factor_details=details,
                    key_evidence_ids=evidence.core_evidence_ids,
                    counter_evidence_ids=evidence.counter_evidence_ids,
                    invalidation_conditions=("必需数据失效或核心证据被正式披露推翻",),
                    historical_signal_summary="无已验证历史统计时保持为空，不作推断",
                    risk_notes=("仅供研究，不构成收益承诺或自动交易指令",),
                    explanation=explanations.get(score.instrument_id, "无合规文本解释"),
                )
            )
        return tuple(reports)

    @staticmethod
    def _industry_ranking(context) -> tuple[IndustryRank, ...]:
        scored = []
        for item in context.industries:
            score = 100.0 if item.direction == "POSITIVE" else 0.0 if item.direction == "NEGATIVE" else 50.0
            scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], pair[1].industry))
        return tuple(
            IndustryRank(
                rank=index,
                industry=item.industry,
                score=score,
                direction=item.direction,
                evidence_ids=item.evidence_ids,
            )
            for index, (score, item) in enumerate(scored, start=1)
        )
