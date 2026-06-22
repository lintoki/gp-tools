import csv
import copy
import io
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from main import DEFAULT_POSITION_STATE, load_json_file, save_json_file


DEFAULT_SETTINGS = {
    "wechat_webhook_url": "",
}


def normalize_stock_code(raw_code: Any) -> str:
    code = str(raw_code).strip().upper()
    if not code:
        raise ValueError("股票代码不能为空")

    if "." in code:
        symbol, market = code.split(".", 1)
        symbol = symbol.zfill(6)
        market = market.upper()
        if market not in {"SH", "SZ", "BJ"}:
            raise ValueError(f"不支持的交易所后缀: {market}")
        return f"{symbol}.{market}"

    symbol = code.zfill(6)
    if not symbol.isdigit() or len(symbol) != 6:
        raise ValueError(f"股票代码格式错误: {raw_code}")

    if symbol.startswith(("60", "68", "90")):
        market = "SH"
    elif symbol.startswith(("00", "30", "20")):
        market = "SZ"
    elif symbol.startswith(("83", "87", "88", "43", "92")):
        market = "BJ"
    else:
        raise ValueError(f"无法从股票代码推断交易所，请使用 代码.SH 或 代码.SZ: {raw_code}")

    return f"{symbol}.{market}"


def infer_market(code: str) -> str:
    return normalize_stock_code(code).split(".", 1)[1]


def _to_bool(value: Any, default: bool = True) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "启用", "是"}:
        return True
    if text in {"0", "false", "no", "n", "off", "停用", "否"}:
        return False
    return default


def _to_float(value: Any, field_name: str) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 必须是数字") from exc


def _to_int(value: Any, field_name: str, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 必须是整数") from exc


def build_watch_item_payload(raw: Dict[str, Any], priority: int) -> Dict[str, Any]:
    normalized_code = normalize_stock_code(raw.get("code", ""))
    name = str(raw.get("name", "")).strip() or normalized_code

    buy_low_raw = raw.get("buy_low")
    buy_high_raw = raw.get("buy_high")
    price_raw = raw.get("price")
    if (buy_low_raw in (None, "")) and (buy_high_raw in (None, "")):
        if price_raw in (None, ""):
            raise ValueError("必须填写 price，或同时填写 buy_low/buy_high")
        buy_low = buy_high = _to_float(price_raw, "price")
    else:
        buy_low = _to_float(buy_low_raw, "buy_low")
        buy_high = _to_float(buy_high_raw, "buy_high")

    if buy_low > buy_high:
        raise ValueError("buy_low 不能大于 buy_high")

    return {
        "name": name,
        "code": normalized_code,
        "market": infer_market(normalized_code),
        "buy_low": buy_low,
        "buy_high": buy_high,
        "shares": _to_int(raw.get("shares"), "shares", 100),
        "type": str(raw.get("type", "")).strip(),
        "priority": _to_int(raw.get("priority"), "priority", priority),
        "enabled": _to_bool(raw.get("enabled"), True),
        "note": str(raw.get("note", "")).strip(),
        **(
            {"depends_on_not_bought": normalize_stock_code(raw["depends_on_not_bought"])}
            if raw.get("depends_on_not_bought")
            else {}
        ),
    }


def import_watchlist_csv(content: str, start_priority: int = 1) -> List[Dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(content.strip()))
    if not reader.fieldnames:
        raise ValueError("CSV 内容必须包含表头")

    items: List[Dict[str, Any]] = []
    for index, row in enumerate(reader):
        if not any(str(value or "").strip() for value in row.values()):
            continue
        items.append(build_watch_item_payload(row, start_priority + index))
    return items


def import_watchlist_json(content: str, start_priority: int = 1) -> List[Dict[str, Any]]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 格式错误: {exc}") from exc

    raw_items = data.get("watchlist") if isinstance(data, dict) else data
    if not isinstance(raw_items, list):
        raise ValueError("JSON 必须是数组，或包含 watchlist 数组")

    return [build_watch_item_payload(item, start_priority + index) for index, item in enumerate(raw_items)]


def import_watchlist_yaml(content: str, start_priority: int = 1) -> List[Dict[str, Any]]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("缺少依赖 PyYAML，请先执行: pip install -r requirements.txt") from exc

    data = yaml.safe_load(content) or {}
    raw_items = data.get("watchlist") if isinstance(data, dict) else data
    if not isinstance(raw_items, list):
        raise ValueError("YAML 必须是列表，或包含 watchlist 列表")

    return [build_watch_item_payload(item, start_priority + index) for index, item in enumerate(raw_items)]


def load_config_document(path: Path) -> Dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("缺少依赖 PyYAML，请先执行: pip install -r requirements.txt") from exc

    if not path.exists():
        return {"watchlist": []}

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if "watchlist" not in data or not isinstance(data["watchlist"], list):
        data["watchlist"] = []
    return data


def save_config_document(path: Path, data: Dict[str, Any]) -> None:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("缺少依赖 PyYAML，请先执行: pip install -r requirements.txt") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(data, file, allow_unicode=True, sort_keys=False)


def upsert_watch_items(config_path: Path, items: Iterable[Dict[str, Any]], replace: bool = False) -> List[Dict[str, Any]]:
    document = {"watchlist": []} if replace else load_config_document(config_path)
    existing_by_code = {str(item.get("code")): index for index, item in enumerate(document["watchlist"])}

    for item in items:
        if item["code"] in existing_by_code:
            document["watchlist"][existing_by_code[item["code"]]] = item
        else:
            document["watchlist"].append(item)

    document["watchlist"].sort(key=lambda item: int(item.get("priority", 999)))
    save_config_document(config_path, document)
    return copy.deepcopy(document["watchlist"])


def remove_watch_item(config_path: Path, code: str) -> List[Dict[str, Any]]:
    normalized_code = normalize_stock_code(code)
    document = load_config_document(config_path)
    document["watchlist"] = [item for item in document["watchlist"] if item.get("code") != normalized_code]
    save_config_document(config_path, document)
    return copy.deepcopy(document["watchlist"])


def ensure_position_entries(position_state_path: Path, items: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    positions = load_json_file(position_state_path, copy.deepcopy(DEFAULT_POSITION_STATE))
    changed = False
    for item in items:
        code = item["code"]
        if code not in positions:
            positions[code] = {"name": item["name"], "bought": False}
            changed = True

    if changed or not position_state_path.exists():
        save_json_file(position_state_path, positions)
    return positions


def update_position_state(position_state_path: Path, code: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    normalized_code = normalize_stock_code(code)
    positions = load_json_file(position_state_path, copy.deepcopy(DEFAULT_POSITION_STATE))
    position = positions.setdefault(normalized_code, {"name": updates.get("name", normalized_code), "bought": False})

    if "name" in updates and updates["name"]:
        position["name"] = str(updates["name"])
    if "bought" in updates:
        position["bought"] = _to_bool(updates["bought"], False)
    if "current_holding" in updates and updates["current_holding"] not in (None, ""):
        position["current_holding"] = _to_int(updates["current_holding"], "current_holding", 0)
    if "target_add" in updates and updates["target_add"] not in (None, ""):
        position["target_add"] = _to_int(updates["target_add"], "target_add", 0)

    save_json_file(position_state_path, positions)
    return positions


def load_settings(path: Path) -> Dict[str, Any]:
    settings = DEFAULT_SETTINGS.copy()
    file_settings = load_json_file(path, {}) if path.exists() else {}
    if isinstance(file_settings, dict):
        settings.update({key: value for key, value in file_settings.items() if key in settings})
    if not settings["wechat_webhook_url"]:
        settings["wechat_webhook_url"] = os.getenv("WECHAT_WEBHOOK_URL", "")
    return settings


def save_settings(path: Path, updates: Dict[str, Any]) -> Dict[str, Any]:
    settings = load_settings(path)
    if "wechat_webhook_url" in updates:
        settings["wechat_webhook_url"] = str(updates.get("wechat_webhook_url") or "").strip()
    save_json_file(path, settings)
    return settings


def mask_webhook_url(url: Optional[str]) -> str:
    if not url:
        return ""
    if len(url) <= 12:
        return "****"
    if "key=" in url:
        prefix, key = url.rsplit("key=", 1)
        if len(key) <= 8:
            return f"{prefix}key=****"
        return f"{prefix}key={key[:4]}...{key[-4:]}"
    return f"{url[:8]}...{url[-4:]}"
