from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import yaml
from pydantic import TypeAdapter

from a_share_research.backtest.engine import BacktestEngine
from a_share_research.backtest.models import BacktestConfig, Order, OrderSide
from a_share_research.context.models import GlobalContext
from a_share_research.core.models import DataBatch
from a_share_research.core.retry import BoundedRetryPolicy
from a_share_research.evidence.gate import EvidenceGate
from a_share_research.evidence.models import Event, EvidenceItem, VerificationResult, VerificationStatus
from a_share_research.factors.base import FactorResult, FactorSnapshot
from a_share_research.factors.scoring import CandidateStatus, CompositeScorer, FactorEngine
from a_share_research.providers.akshare import AkshareProvider
from a_share_research.providers.base import FetchRequest, ProviderRegistry
from a_share_research.quality.contracts import DataContract
from a_share_research.quality.gate import QualityGate, QualityReport, QualityStatus
from a_share_research.reporting.models import DailyReport, ReportStatus
from a_share_research.reporting.render import write_report
from a_share_research.settings import load_settings
from a_share_research.storage.lake import DataLake
from a_share_research.universe.rules import UniverseBuilder, UniverseConfig, UniverseResult

COMMANDS = (
    "init-db",
    "update-data",
    "validate-data",
    "build-universe",
    "compute-factors",
    "run-evidence-gate",
    "rank-industries",
    "select-candidates",
    "backtest",
    "walk-forward",
    "daily-report",
)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("datetime must include a timezone offset")
    return parsed


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(payload, "model_dump_json"):
        text = payload.model_dump_json(indent=2)
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    path.write_text(text, encoding="utf-8")


def _to_jsonable(payload):
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    if isinstance(payload, (list, tuple)):
        return [_to_jsonable(item) for item in payload]
    if isinstance(payload, dict):
        return {str(key): _to_jsonable(value) for key, value in payload.items()}
    return payload


def _payload_hash(payload) -> str:
    return hashlib.sha256(
        json.dumps(
            _to_jsonable(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _write_stage_artifact(
    path: Path,
    *,
    run_id: str,
    gate: QualityReport,
    artifact_type: str,
    payload,
) -> None:
    normalized = _to_jsonable(payload)
    _write_json(
        path,
        {
            "run_id": run_id,
            "gate_snapshot_id": gate.snapshot_id(),
            "artifact_type": artifact_type,
            "payload_sha256": _payload_hash(normalized),
            "payload": normalized,
        },
    )


def _read_stage_artifact(path: Path, *, run_id: str, gate: QualityReport, artifact_type: str):
    envelope = json.loads(path.read_text(encoding="utf-8"))
    if envelope.get("run_id") != run_id:
        raise ValueError(f"BLOCKED_DATA: stage artifact run ID mismatch: {path}")
    if envelope.get("gate_snapshot_id") != gate.snapshot_id():
        raise ValueError(f"BLOCKED_DATA: stage artifact gate snapshot mismatch: {path}")
    if envelope.get("artifact_type") != artifact_type:
        raise ValueError(f"BLOCKED_DATA: unexpected stage artifact type: {path}")
    payload = envelope.get("payload")
    if envelope.get("payload_sha256") != _payload_hash(payload):
        raise ValueError(f"BLOCKED_DATA: stage artifact payload hash mismatch: {path}")
    return payload


def _init_db(args: argparse.Namespace) -> int:
    root = Path(args.data_dir)
    for name in ("raw", "normalized", "curated", "manifests", "quarantine"):
        (root / name).mkdir(parents=True, exist_ok=True)
    print(root.resolve())
    return 0


def _update_data(args: argparse.Namespace) -> int:
    as_of = _parse_datetime(args.as_of)
    request = FetchRequest(
        dataset="daily_bars",
        symbols=tuple(item.strip() for item in args.symbols.split(",") if item.strip()),
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date),
        as_of=as_of,
        run_id=args.run_id,
    )
    settings = load_settings(Path(args.config_dir))
    provider = AkshareProvider(minimum_interval_seconds=settings.minimum_request_interval_seconds)
    registry = ProviderRegistry(
        provider,
        policy=BoundedRetryPolicy(
            max_attempts=settings.max_attempts,
            delays=settings.retry_delays_seconds,
        ),
        maximum_backups=settings.maximum_backup_sources,
    )
    try:
        batch = registry.fetch_with_fallback(request)
    except RuntimeError as exc:
        print(f"BLOCKED_DATA: {exc}")
        return 3
    root = Path(args.data_dir)
    manifest_path = root / "manifests" / f"{args.run_id}-daily_bars.json"
    _write_json(manifest_path, batch)
    lake = DataLake(root)
    lake.write_raw(batch, provider.last_raw_payload)
    artifact = lake.write_normalized(batch)
    print(artifact.path.resolve())
    return 0


def _validate_data(args: argparse.Namespace) -> int:
    batches = TypeAdapter(list[DataBatch]).validate_json(Path(args.batches_json).read_text(encoding="utf-8"))
    contracts = TypeAdapter(list[DataContract]).validate_json(
        Path(args.contracts_json).read_text(encoding="utf-8")
    )
    artifact_manifest_path = Path(args.artifacts_json)
    artifact_paths = json.loads(artifact_manifest_path.read_text(encoding="utf-8"))
    if not isinstance(artifact_paths, dict) or not artifact_paths:
        raise ValueError("artifact manifest must be a non-empty object")
    artifact_hashes = {}
    for name, value in artifact_paths.items():
        path = Path(value)
        if not path.is_absolute():
            path = artifact_manifest_path.parent / path
        artifact_hashes[str(name)] = hashlib.sha256(path.read_bytes()).hexdigest()
    report = QualityGate().validate(
        batches,
        contracts,
        _parse_datetime(args.as_of),
        artifact_hashes=artifact_hashes,
    )
    _write_json(Path(args.output_json), report)
    print(report.status)
    return 0 if report.status == "PASS" else 3


def _load_bound_gate(path: str, run_id: str) -> QualityReport:
    report = QualityReport.model_validate_json(Path(path).read_text(encoding="utf-8"))
    if report.run_ids != (run_id,):
        raise ValueError(f"BLOCKED_DATA: gate run IDs {report.run_ids} do not match expected run ID {run_id}")
    if not report.dataset_hashes:
        raise ValueError("BLOCKED_DATA: quality gate has no dataset hashes")
    if not report.artifact_hashes:
        raise ValueError("BLOCKED_DATA: quality gate has no authorized input artifacts")
    if report.as_of is None:
        raise ValueError("BLOCKED_DATA: quality gate has no validation as-of timestamp")
    return report


def _require_authorized_file(gate: QualityReport, name: str, path: Path) -> None:
    expected = gate.artifact_hashes.get(name)
    if expected is None:
        raise ValueError(f"BLOCKED_DATA: input artifact is not authorized: {name}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"BLOCKED_DATA: input artifact hash mismatch: {name}")


def _require_pass_gate(path: str, run_id: str) -> QualityReport:
    report = _load_bound_gate(path, run_id)
    if report.status != QualityStatus.PASS:
        raise ValueError("BLOCKED_DATA: quality gate is not PASS")
    return report


def _load_factor_snapshot(bundle_dir: Path) -> FactorSnapshot:
    def read(name: str) -> pd.DataFrame:
        path = bundle_dir / f"{name}.csv"
        if not path.is_file():
            raise FileNotFoundError(f"required factor input not found: {path}")
        return pd.read_csv(path)

    return FactorSnapshot(
        bars=read("bars"),
        benchmark=read("benchmark"),
        financials=read("financials"),
        valuations=read("valuations"),
        industry=read("industry"),
        events=read("events"),
    )


def _build_universe(args: argparse.Namespace) -> int:
    gate = _require_pass_gate(args.gate_json, args.run_id)
    _require_authorized_file(gate, "universe_securities", Path(args.securities_csv))
    _require_authorized_file(gate, "universe_bars", Path(args.bars_csv))
    payload = yaml.safe_load((Path(args.config_dir) / "universe.yaml").read_text(encoding="utf-8"))
    config = UniverseConfig(
        allowed_prefixes=tuple(payload["allowed_prefixes"]),
        minimum_listing_trading_days=int(payload["minimum_listing_trading_days"]),
        minimum_20d_average_amount=float(payload["minimum_20d_average_amount_cny"]),
        minimum_20d_valid_days=int(payload["minimum_20d_valid_trading_days"]),
    )
    result = UniverseBuilder(config).build(
        date.fromisoformat(args.as_of),
        pd.read_csv(args.securities_csv),
        pd.read_csv(args.bars_csv),
    )
    _write_stage_artifact(
        Path(args.output_json),
        run_id=args.run_id,
        gate=gate,
        artifact_type="universe",
        payload=result,
    )
    return 0


def _compute_factors(args: argparse.Namespace) -> int:
    gate = _require_pass_gate(args.gate_json, args.run_id)
    bundle = Path(args.bundle_dir)
    for name in ("bars", "benchmark", "financials", "valuations", "industry", "events"):
        _require_authorized_file(gate, f"factor_{name}", bundle / f"{name}.csv")
    results = FactorEngine().compute(
        _load_factor_snapshot(Path(args.bundle_dir)),
        _parse_datetime(args.as_of),
    )
    _write_stage_artifact(
        Path(args.output_json),
        run_id=args.run_id,
        gate=gate,
        artifact_type="factors",
        payload=results,
    )
    print(f"factor_results={len(results)}")
    return 0


def _run_evidence_gate(args: argparse.Namespace) -> int:
    gate = _require_pass_gate(args.gate_json, args.run_id)
    _require_authorized_file(gate, "event", Path(args.event_json))
    _require_authorized_file(gate, "evidence", Path(args.evidence_json))
    event = Event.model_validate_json(Path(args.event_json).read_text(encoding="utf-8"))
    evidence = TypeAdapter(list[EvidenceItem]).validate_json(
        Path(args.evidence_json).read_text(encoding="utf-8")
    )
    result = EvidenceGate().evaluate(
        event,
        evidence,
        counter_search_performed=bool(args.counter_search_performed),
        as_of=_parse_datetime(args.as_of),
    )
    _write_stage_artifact(
        Path(args.output_json),
        run_id=args.run_id,
        gate=gate,
        artifact_type="evidence",
        payload=[result],
    )
    print(result.status)
    return 0 if result.status == "VERIFIED" else 3


def _rank_industries(args: argparse.Namespace) -> int:
    gate = _require_pass_gate(args.gate_json, args.run_id)
    _require_authorized_file(gate, "context", Path(args.context_json))
    context = GlobalContext.model_validate_json(Path(args.context_json).read_text(encoding="utf-8"))
    rows = []
    for item in context.industries:
        score = 100.0 if item.direction == "POSITIVE" else 0.0 if item.direction == "NEGATIVE" else 50.0
        rows.append(
            {
                "industry": item.industry,
                "score": score,
                "direction": item.direction,
                "evidence_ids": item.evidence_ids,
            }
        )
    rows.sort(key=lambda item: (-item["score"], item["industry"]))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    _write_stage_artifact(
        Path(args.output_json),
        run_id=args.run_id,
        gate=gate,
        artifact_type="industry_ranking",
        payload=rows,
    )
    return 0


def _select_candidates(args: argparse.Namespace) -> int:
    gate = _require_pass_gate(args.gate_json, args.run_id)
    factors = TypeAdapter(list[FactorResult]).validate_python(
        _read_stage_artifact(
            Path(args.factors_json),
            run_id=args.run_id,
            gate=gate,
            artifact_type="factors",
        )
    )
    evidence_payload = []
    for value in args.evidence_json.split(","):
        evidence_payload.extend(
            _read_stage_artifact(
                Path(value.strip()),
                run_id=args.run_id,
                gate=gate,
                artifact_type="evidence",
            )
        )
    evidence = TypeAdapter(list[VerificationResult]).validate_python(evidence_payload)
    settings = load_settings(Path(args.config_dir))
    universe = UniverseResult.model_validate(
        _read_stage_artifact(
            Path(args.universe_json),
            run_id=args.run_id,
            gate=gate,
            artifact_type="universe",
        )
    )
    scores = CompositeScorer(settings.required_factors).score(factors, settings.factor_weights)
    verified_entities = {item.entity_id for item in evidence if item.status == VerificationStatus.VERIFIED}
    rows = [
        score.model_dump(mode="json")
        for score in scores
        if score.status == CandidateStatus.READY
        and score.instrument_id in verified_entities
        and score.instrument_id in universe.eligible
        and not universe.trade_flags[score.instrument_id].suspended
        and not universe.trade_flags[score.instrument_id].limit_up_locked
        and not universe.trade_flags[score.instrument_id].limit_down_locked
    ]
    rows.sort(key=lambda item: (-item["composite_score"], item["instrument_id"]))
    _write_stage_artifact(
        Path(args.output_json),
        run_id=args.run_id,
        gate=gate,
        artifact_type="candidates",
        payload=rows[:5],
    )
    return 0


def _backtest_config(path: Path) -> BacktestConfig:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    costs = payload.get("costs", {})
    portfolio = payload.get("portfolio", {})
    return BacktestConfig(
        initial_cash=float(portfolio.get("initial_cash_cny", 1_000_000)),
        lot_size=int(payload.get("lot_size", 100)),
        commission_rate=float(costs.get("commission_rate", 0.0003)),
        minimum_commission=float(costs.get("minimum_commission_cny", 5.0)),
        sell_stamp_tax_rate=float(costs.get("sell_stamp_tax_rate", 0.0005)),
        slippage_bps=float(costs.get("slippage_bps", 5.0)),
        signal_time=str(payload.get("signal_time", "close")),
        execution_time=str(payload.get("execution_time", "next_open")),
        t_plus_one=bool(payload.get("t_plus_one", True)),
    )


def _orders_from_csv(path: Path) -> list[Order]:
    frame = pd.read_csv(path)
    return [
        Order(
            instrument_id=str(row["instrument_id"]),
            trade_date=date.fromisoformat(str(row["trade_date"])),
            side=OrderSide(str(row["side"]).upper()),
            quantity=int(row["quantity"]),
        )
        for row in frame.to_dict(orient="records")
    ]


def _backtest(args: argparse.Namespace) -> int:
    gate = _require_pass_gate(args.gate_json, args.run_id)
    _require_authorized_file(gate, "orders", Path(args.orders_csv))
    _require_authorized_file(gate, "backtest_bars", Path(args.bars_csv))
    _require_authorized_file(gate, "backtest_config", Path(args.config))
    _require_authorized_file(gate, "historical_universe", Path(args.historical_universe_csv))
    try:
        result = BacktestEngine(_backtest_config(Path(args.config))).run(
            _orders_from_csv(Path(args.orders_csv)),
            pd.read_csv(args.bars_csv),
            as_of=date.fromisoformat(args.as_of),
            benchmark_return=float(args.benchmark_return),
            historical_universe=pd.read_csv(args.historical_universe_csv),
        )
    except Exception as exc:
        _write_stage_artifact(
            Path(args.output_json),
            run_id=args.run_id,
            gate=gate,
            artifact_type="backtest",
            payload={
                "status": "FAILED",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        )
        return 3
    _write_stage_artifact(
        Path(args.output_json),
        run_id=args.run_id,
        gate=gate,
        artifact_type="backtest",
        payload={"status": "SUCCEEDED", "result": result},
    )
    return 0


def _walk_forward(args: argparse.Namespace) -> int:
    gate = _require_pass_gate(args.gate_json, args.run_id)
    _require_authorized_file(gate, "orders", Path(args.orders_csv))
    _require_authorized_file(gate, "backtest_bars", Path(args.bars_csv))
    _require_authorized_file(gate, "backtest_config", Path(args.config))
    _require_authorized_file(gate, "walk_windows", Path(args.windows_json))
    _require_authorized_file(gate, "historical_universe", Path(args.historical_universe_csv))
    config = _backtest_config(Path(args.config))
    orders = _orders_from_csv(Path(args.orders_csv))
    bars = pd.read_csv(args.bars_csv)
    windows = json.loads(Path(args.windows_json).read_text(encoding="utf-8"))
    historical_universe = pd.read_csv(args.historical_universe_csv)
    results = []
    failed = False
    for window in windows:
        start = date.fromisoformat(window["start"])
        end = date.fromisoformat(window["end"])
        window_orders = [order for order in orders if start <= order.trade_date <= end]
        window_bars = bars.copy()
        dates = pd.to_datetime(window_bars["trade_date"]).dt.date
        window_bars = window_bars[(dates >= start) & (dates <= end)]
        try:
            result = BacktestEngine(config).run(
                window_orders,
                window_bars,
                as_of=end,
                benchmark_return=float(window["benchmark_return"]),
                historical_universe=historical_universe,
            )
            results.append(
                {"status": "SUCCEEDED", "window": window, "result": result.model_dump(mode="json")}
            )
        except Exception as exc:
            failed = True
            results.append(
                {
                    "status": "FAILED",
                    "window": window,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
    _write_stage_artifact(
        Path(args.output_json),
        run_id=args.run_id,
        gate=gate,
        artifact_type="walk_forward",
        payload=results,
    )
    return 3 if failed else 0


def _daily_report(args: argparse.Namespace) -> int:
    gate = _load_bound_gate(args.gate_json, args.run_id)
    report = DailyReport.model_validate_json(Path(args.report_json).read_text(encoding="utf-8"))
    if report.run_id != args.run_id:
        raise ValueError("BLOCKED_DATA: report run ID does not match quality gate run ID")
    if gate.status == QualityStatus.FAIL:
        if report.status != ReportStatus.BLOCKED_DATA:
            raise ValueError("BLOCKED_DATA: failed gate can only render a blocked report")
        if report.data_integrity.errors != gate.blocking_errors:
            raise ValueError("BLOCKED_DATA: report errors do not match quality gate errors")
    elif report.status == ReportStatus.BLOCKED_DATA:
        raise ValueError("BLOCKED_DATA: PASS gate cannot render a blocked-data report")
    elif report.data_integrity.snapshot_id != gate.snapshot_id():
        raise ValueError("BLOCKED_DATA: report snapshot does not match quality gate inputs")
    if report.status == ReportStatus.SUCCEEDED:
        settings = load_settings(Path(args.config_dir))
        if report.required_factors != settings.required_factors:
            raise ValueError("BLOCKED_DATA: report required factors do not match project config")
        if report.factor_weights != settings.factor_weights:
            raise ValueError("BLOCKED_DATA: report factor weights do not match project config")
        if not args.candidates_json or not args.factors_json:
            raise ValueError("BLOCKED_DATA: successful report requires candidate and factor artifacts")
        candidate_payload = _read_stage_artifact(
            Path(args.candidates_json),
            run_id=args.run_id,
            gate=gate,
            artifact_type="candidates",
        )
        factor_payload = _read_stage_artifact(
            Path(args.factors_json),
            run_id=args.run_id,
            gate=gate,
            artifact_type="factors",
        )
        candidate_scores = {
            item["instrument_id"]: float(item["composite_score"]) for item in candidate_payload
        }
        if set(candidate_scores) != {item.instrument_id for item in report.candidates}:
            raise ValueError("BLOCKED_DATA: report candidates do not match candidate artifact")
        factors = TypeAdapter(list[FactorResult]).validate_python(factor_payload)
        factor_map = {(item.instrument_id, item.factor_name): item for item in factors}
        for candidate in report.candidates:
            if abs(candidate_scores[candidate.instrument_id] - candidate.composite_score) > 1e-6:
                raise ValueError("BLOCKED_DATA: report score does not match candidate artifact")
            for detail in candidate.factor_details:
                source = factor_map.get((candidate.instrument_id, detail.name))
                if source is None or (
                    detail.raw_value != source.raw_value
                    or detail.z_value != source.z_value
                    or detail.score != source.score
                    or detail.as_of != source.as_of
                    or detail.dependencies != source.dependencies
                ):
                    raise ValueError("BLOCKED_DATA: report factor detail does not match factor artifact")
    paths = write_report(report, Path(args.output_dir))
    print(paths.json.resolve())
    print(paths.markdown.resolve())
    print(paths.csv.resolve())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="a-share-research",
        description="Fail-closed A-share daily quantitative research system",
    )
    subparsers = parser.add_subparsers(dest="command")

    init_db = subparsers.add_parser("init-db")
    init_db.add_argument("--data-dir", required=True)
    init_db.set_defaults(handler=_init_db)

    update = subparsers.add_parser("update-data")
    update.add_argument("--symbols", required=True)
    update.add_argument("--start-date", required=True)
    update.add_argument("--end-date", required=True)
    update.add_argument("--as-of", required=True)
    update.add_argument("--run-id", required=True)
    update.add_argument("--data-dir", required=True)
    update.add_argument("--config-dir", required=True)
    update.set_defaults(handler=_update_data)

    validate = subparsers.add_parser("validate-data")
    validate.add_argument("--batches-json", required=True)
    validate.add_argument("--contracts-json", required=True)
    validate.add_argument("--as-of", required=True)
    validate.add_argument("--output-json", required=True)
    validate.add_argument("--artifacts-json", required=True)
    validate.set_defaults(handler=_validate_data)

    universe = subparsers.add_parser("build-universe")
    universe.add_argument("--securities-csv", required=True)
    universe.add_argument("--bars-csv", required=True)
    universe.add_argument("--as-of", required=True)
    universe.add_argument("--config-dir", required=True)
    universe.add_argument("--gate-json", required=True)
    universe.add_argument("--run-id", required=True)
    universe.add_argument("--output-json", required=True)
    universe.set_defaults(handler=_build_universe)

    compute = subparsers.add_parser("compute-factors")
    compute.add_argument("--bundle-dir", required=True)
    compute.add_argument("--as-of", required=True)
    compute.add_argument("--output-json", required=True)
    compute.add_argument("--gate-json", required=True)
    compute.add_argument("--run-id", required=True)
    compute.set_defaults(handler=_compute_factors)

    evidence = subparsers.add_parser("run-evidence-gate")
    evidence.add_argument("--event-json", required=True)
    evidence.add_argument("--evidence-json", required=True)
    evidence.add_argument("--counter-search-performed", action="store_true")
    evidence.add_argument("--as-of", required=True)
    evidence.add_argument("--output-json", required=True)
    evidence.add_argument("--gate-json", required=True)
    evidence.add_argument("--run-id", required=True)
    evidence.set_defaults(handler=_run_evidence_gate)

    rank = subparsers.add_parser("rank-industries")
    rank.add_argument("--context-json", required=True)
    rank.add_argument("--output-json", required=True)
    rank.add_argument("--gate-json", required=True)
    rank.add_argument("--run-id", required=True)
    rank.set_defaults(handler=_rank_industries)

    select = subparsers.add_parser("select-candidates")
    select.add_argument("--factors-json", required=True)
    select.add_argument("--evidence-json", required=True)
    select.add_argument("--config-dir", required=True)
    select.add_argument("--output-json", required=True)
    select.add_argument("--universe-json", required=True)
    select.add_argument("--gate-json", required=True)
    select.add_argument("--run-id", required=True)
    select.set_defaults(handler=_select_candidates)

    backtest = subparsers.add_parser("backtest")
    backtest.add_argument("--orders-csv", required=True)
    backtest.add_argument("--bars-csv", required=True)
    backtest.add_argument("--as-of", required=True)
    backtest.add_argument("--config", required=True)
    backtest.add_argument("--output-json", required=True)
    backtest.add_argument("--benchmark-return", required=True, type=float)
    backtest.add_argument("--historical-universe-csv", required=True)
    backtest.add_argument("--gate-json", required=True)
    backtest.add_argument("--run-id", required=True)
    backtest.set_defaults(handler=_backtest)

    walk = subparsers.add_parser("walk-forward")
    walk.add_argument("--orders-csv", required=True)
    walk.add_argument("--bars-csv", required=True)
    walk.add_argument("--windows-json", required=True)
    walk.add_argument("--config", required=True)
    walk.add_argument("--output-json", required=True)
    walk.add_argument("--historical-universe-csv", required=True)
    walk.add_argument("--gate-json", required=True)
    walk.add_argument("--run-id", required=True)
    walk.set_defaults(handler=_walk_forward)

    daily = subparsers.add_parser("daily-report")
    daily.add_argument("--report-json", required=True)
    daily.add_argument("--output-dir", required=True)
    daily.add_argument("--gate-json", required=True)
    daily.add_argument("--run-id", required=True)
    daily.add_argument("--config-dir", required=True)
    daily.add_argument("--candidates-json")
    daily.add_argument("--factors-json")
    daily.set_defaults(handler=_daily_report)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        return int(args.handler(args))
    except (FileNotFoundError, ValueError) as exc:
        print(f"BLOCKED_DATA: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
