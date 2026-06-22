#!/usr/bin/env python3
import base64
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response

from main import BASE_DIR, load_config, load_dotenv_if_available, load_json_file
from monitor_runtime import MonitorRuntime
from web_config import (
    build_watch_item_payload,
    ensure_position_entries,
    import_watchlist_csv,
    import_watchlist_json,
    import_watchlist_yaml,
    load_config_document,
    load_settings,
    mask_webhook_url,
    remove_watch_item,
    save_settings,
    update_position_state,
    upsert_watch_items,
)


CONFIG_PATH = BASE_DIR / "config.yaml"
ALERT_STATE_PATH = BASE_DIR / "alert_state.json"
POSITION_STATE_PATH = BASE_DIR / "position_state.json"
SETTINGS_PATH = BASE_DIR / "settings.json"
SNAPSHOTS_PATH = BASE_DIR / "market_snapshots.jsonl"
INDEX_PATH = BASE_DIR / "static" / "index.html"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 16666
AUTH_REALM = "AStockWatch"

runtime = MonitorRuntime(
    base_dir=BASE_DIR,
    config_path=CONFIG_PATH,
    alert_state_path=ALERT_STATE_PATH,
    position_state_path=POSITION_STATE_PATH,
    settings_path=SETTINGS_PATH,
    snapshots_path=SNAPSHOTS_PATH,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_dotenv_if_available(BASE_DIR / ".env")
    runtime.start()
    yield
    runtime.stop()


app = FastAPI(title="A 股买点监控", lifespan=lifespan)


def get_bind_host() -> str:
    return os.getenv("APP_HOST", DEFAULT_HOST)


def get_bind_port() -> int:
    value = os.getenv("APP_PORT", str(DEFAULT_PORT))
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError("APP_PORT 必须是整数") from exc


def get_auth_config() -> Optional[Tuple[str, str]]:
    username = os.getenv("APP_USERNAME", "").strip()
    password = os.getenv("APP_PASSWORD", "").strip()
    if not username and not password:
        return None
    if not username or not password:
        raise RuntimeError("公网鉴权需要同时设置 APP_USERNAME 和 APP_PASSWORD")
    return username, password


def verify_basic_auth_header(header: Optional[str], username: str, password: str) -> bool:
    if not header or not header.startswith("Basic "):
        return False
    try:
        raw = base64.b64decode(header.removeprefix("Basic ").strip()).decode("utf-8")
    except Exception:
        return False
    provided_username, separator, provided_password = raw.partition(":")
    if separator != ":":
        return False
    return secrets.compare_digest(provided_username, username) and secrets.compare_digest(provided_password, password)


def _auth_required_response() -> Response:
    return Response(
        status_code=401,
        headers={"WWW-Authenticate": f'Basic realm="{AUTH_REALM}"'},
        content="Authentication required",
    )


@app.middleware("http")
async def basic_auth_middleware(request: Request, call_next):
    if request.url.path in {"/api/health", "/favicon.ico"}:
        return await call_next(request)
    auth_config = get_auth_config()
    if auth_config is None:
        return await call_next(request)
    username, password = auth_config
    if not verify_basic_auth_header(request.headers.get("Authorization"), username, password):
        return _auth_required_response()
    return await call_next(request)


def _settings_view() -> Dict[str, Any]:
    settings = load_settings(SETTINGS_PATH)
    webhook_url = settings.get("wechat_webhook_url", "")
    return {
        "webhook_configured": bool(webhook_url),
        "webhook_preview": mask_webhook_url(webhook_url),
    }


def _next_priority() -> int:
    document = load_config_document(CONFIG_PATH)
    priorities = [int(item.get("priority", 0)) for item in document.get("watchlist", [])]
    return max(priorities, default=0) + 1


def _build_watch_item_for_save(payload: Dict[str, Any]) -> Dict[str, Any]:
    item = build_watch_item_payload(payload, priority=_next_priority())
    document = load_config_document(CONFIG_PATH)
    for existing in document.get("watchlist", []):
        if existing.get("code") != item["code"]:
            continue
        item["priority"] = int(existing.get("priority", item["priority"]))
        item["enabled"] = bool(existing.get("enabled", item["enabled"]))
        break
    return item


def _state_payload() -> Dict[str, Any]:
    document = load_config_document(CONFIG_PATH)
    positions = load_json_file(POSITION_STATE_PATH, {})
    return {
        **runtime.snapshot(),
        "watchlist": document.get("watchlist", []),
        "ai_core_watch": document.get("ai_core_watch", []),
        "positions": positions,
        "settings": _settings_view(),
    }


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INDEX_PATH)


@app.head("/")
def index_head() -> Response:
    return Response(status_code=200)


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "running": runtime.snapshot().get("running", False)}


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api/state")
def get_state() -> Dict[str, Any]:
    try:
        return _state_payload()
    except Exception as exc:
        raise _bad_request(exc) from exc


@app.post("/api/refresh")
def refresh() -> Dict[str, Any]:
    try:
        runtime.refresh_once(force=True)
        return _state_payload()
    except Exception as exc:
        runtime.add_event("ERROR", f"手动刷新失败: {exc}")
        raise _bad_request(exc) from exc


@app.post("/api/monitor/start")
def start_monitor() -> Dict[str, Any]:
    try:
        runtime.start()
        runtime.add_event("INFO", "已手动启动监控后台")
        return _state_payload()
    except Exception as exc:
        raise _bad_request(exc) from exc


@app.post("/api/monitor/stop")
def stop_monitor() -> Dict[str, Any]:
    try:
        runtime.stop()
        runtime.add_event("INFO", "已手动停止监控后台")
        return _state_payload()
    except Exception as exc:
        raise _bad_request(exc) from exc


@app.post("/api/settings")
async def update_settings(request: Request) -> Dict[str, Any]:
    try:
        payload = await request.json()
        save_settings(SETTINGS_PATH, payload)
        runtime.add_event("INFO", "已更新企业微信群 webhook 配置")
        return _settings_view()
    except Exception as exc:
        raise _bad_request(exc) from exc


@app.post("/api/watchlist")
async def add_or_update_watch_item(request: Request) -> Dict[str, Any]:
    try:
        payload = await request.json()
        item = _build_watch_item_for_save(payload)
        watchlist = upsert_watch_items(CONFIG_PATH, [item])
        ensure_position_entries(POSITION_STATE_PATH, [item])
        runtime.add_event("INFO", f"已保存监控股票: {item['name']} {item['code']}")
        return {"watchlist": watchlist}
    except Exception as exc:
        raise _bad_request(exc) from exc


@app.post("/api/watchlist/import")
async def import_watchlist(request: Request) -> Dict[str, Any]:
    try:
        payload = await request.json()
        content = str(payload.get("content", "")).strip()
        if not content:
            raise ValueError("导入内容不能为空")

        replace = bool(payload.get("replace", False))
        start_priority = 1 if replace else _next_priority()
        fmt = str(payload.get("format", "json")).lower()
        if fmt == "yaml":
            items = import_watchlist_yaml(content, start_priority=start_priority)
        elif fmt == "csv":
            items = import_watchlist_csv(content, start_priority=start_priority)
        elif fmt == "json":
            items = import_watchlist_json(content, start_priority=start_priority)
        else:
            raise ValueError("format 只支持 json、csv 或 yaml")

        watchlist = upsert_watch_items(CONFIG_PATH, items, replace=replace)
        ensure_position_entries(POSITION_STATE_PATH, items)
        runtime.add_event("INFO", f"已导入 {len(items)} 只监控股票")
        return {"watchlist": watchlist, "count": len(items)}
    except Exception as exc:
        raise _bad_request(exc) from exc


@app.delete("/api/watchlist/{code}")
def delete_watch_item(code: str) -> Dict[str, Any]:
    try:
        watchlist = remove_watch_item(CONFIG_PATH, code)
        runtime.add_event("INFO", f"已删除监控股票: {code}")
        return {"watchlist": watchlist}
    except Exception as exc:
        raise _bad_request(exc) from exc


@app.put("/api/positions/{code}")
async def update_position(code: str, request: Request) -> Dict[str, Any]:
    try:
        payload = await request.json()
        positions = update_position_state(POSITION_STATE_PATH, code, payload)
        runtime.add_event("INFO", f"已更新持仓状态: {code}")
        return {"positions": positions}
    except Exception as exc:
        raise _bad_request(exc) from exc


def main() -> None:
    load_dotenv_if_available(BASE_DIR / ".env")
    get_auth_config()
    uvicorn.run("app:app", host=get_bind_host(), port=get_bind_port(), reload=False)


if __name__ == "__main__":
    main()
