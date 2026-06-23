from pathlib import Path
from datetime import date
from typing import Any, Callable, Dict, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from quant.backtest_engine import BacktestEngine
from quant.registry import StrategyRegistry
from quant.real_data import DEFAULT_MAX_SYMBOLS, fetch_a_share_bars, fetch_recent_a_share_bars
from quant.realtime_screener import AkshareRealtimeProvider, RealtimeStrategyScreener
from quant.result_store import ResultStore


class BacktestPayload(BaseModel):
    strategy_id: str
    start_date: str
    end_date: str
    initial_cash: float = 100000
    commission: float = 0.0003
    slippage: float = 0.001
    params: Dict[str, Any] = Field(default_factory=dict)


class SignalPayload(BaseModel):
    strategy_id: str
    params: Dict[str, Any] = Field(default_factory=dict)


class LimitUpCachePayload(BaseModel):
    trade_date: Optional[date] = None


def create_app(
    base_dir: Optional[Path] = None,
    history_provider: Optional[Callable[[str, str, Optional[int]], Dict[str, Any]]] = None,
    recent_provider: Optional[Callable[[Optional[int]], Dict[str, Any]]] = None,
    realtime_provider: Optional[Any] = None,
    now_func: Optional[Callable[[], Any]] = None,
) -> FastAPI:
    root = base_dir or Path(__file__).resolve().parent
    data_dir = root / "data"
    runs_dir = data_dir / "runs"
    get_history = history_provider or fetch_a_share_bars
    get_recent = recent_provider or fetch_recent_a_share_bars

    registry = StrategyRegistry.load_builtin()
    engine = BacktestEngine(registry)
    realtime_data = realtime_provider or AkshareRealtimeProvider(data_dir)
    signal_screener = RealtimeStrategyScreener(realtime_data, now_func=now_func) if now_func else RealtimeStrategyScreener(realtime_data)
    result_store = ResultStore(runs_dir, keep_last=5)
    app = FastAPI(title="短线量化回测系统")

    @app.get("/", response_class=HTMLResponse)
    def index():
        page = Path(__file__).resolve().parent / "static" / "index.html"
        if page.exists():
            return FileResponse(page)
        return HTMLResponse("<h1>短线量化回测系统</h1>")

    @app.get("/api/strategies")
    def list_strategies():
        return {"strategies": registry.list_specs()}

    @app.get("/api/backtests")
    def list_backtests():
        return {"runs": result_store.list_runs()}

    @app.get("/api/backtests/{run_id}")
    def get_backtest(run_id: str):
        try:
            return result_store.load(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/backtests")
    def run_backtest(payload: BacktestPayload):
        if payload.start_date > payload.end_date:
            raise HTTPException(status_code=400, detail="start_date cannot be after end_date")
        bars_by_symbol = get_history(payload.start_date, payload.end_date, DEFAULT_MAX_SYMBOLS)
        if not bars_by_symbol:
            raise HTTPException(status_code=502, detail="no market data fetched")

        try:
            result = engine.run(
                strategy_id=payload.strategy_id,
                bars_by_symbol=bars_by_symbol,
                initial_cash=payload.initial_cash,
                commission=payload.commission,
                slippage=payload.slippage,
                params={**payload.params, "start_date": payload.start_date, "end_date": payload.end_date},
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        saved = result_store.save(result.summary, result.trades, result.equity_curve)
        return saved

    @app.post("/api/signals")
    def run_signals(payload: SignalPayload):
        try:
            return signal_screener.run(payload.strategy_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail="实时行情源暂时不可用，请稍后重试。") from exc

    @app.post("/api/limit-up-cache/refresh")
    def refresh_limit_up_cache(payload: LimitUpCachePayload):
        if not hasattr(realtime_data, "refresh_limit_up_cache"):
            raise HTTPException(status_code=400, detail="realtime provider does not support limit-up cache refresh")
        try:
            count = realtime_data.refresh_limit_up_cache(payload.trade_date)
            return {"trade_date": (payload.trade_date or date.today()).isoformat(), "cached_limit_up_count": count}
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"limit-up cache refresh failed: {exc}") from exc

    return app


if __name__ == "__main__":
    uvicorn.run(create_app(), host="127.0.0.1", port=17777)
