#!/usr/bin/env python3
import argparse
import contextlib
import io
import json
import logging
import math
import os
import time
import urllib.error
import urllib.request
import warnings
from datetime import datetime


DEFAULT_CODES = ("159659", "513650")
DEFAULT_INTERVAL_SECONDS = 1800
DEFAULT_WECHAT_INTERVAL_SECONDS = 1800
DEFAULT_WECHAT_WEBHOOK_URL = None


def _to_float(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", "").replace("%", "")
        if value in ("", "-", "--", "None", "nan"):
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def _format_price(value):
    number = _to_float(value)
    return "-" if number is None else f"{number:.4f}"


def _format_percent(value):
    number = _to_float(value)
    return "-" if number is None else f"{number:+.2f}%"


def _format_amount_wan(value):
    number = _to_float(value)
    return "-" if number is None else f"{number / 10000:,.2f} 万"


def build_log_line(row):
    code = str(row.get("代码", "")).zfill(6)
    name = row.get("名称", "-")
    price = _to_float(row.get("最新价"))
    net_value = _to_float(row.get("IOPV实时估值"))

    if price is not None and net_value not in (None, 0):
        premium = (price / net_value - 1) * 100
        premium_text = f"{premium:+.2f}%"
    else:
        premium_text = "-"

    return (
        f"{code} {name} | "
        f"现价 {_format_price(price)} | "
        f"涨跌 {_format_percent(row.get('涨跌幅'))} | "
        f"成交 {_format_amount_wan(row.get('成交额'))} | "
        f"IOPV {_format_price(net_value)} | "
        f"溢价 {premium_text}"
    )


def build_wechat_message(timestamp, log_lines):
    return "\n".join(["ETF 实时行情", f"时间：{timestamp}", "", *log_lines])


def send_wechat_text(webhook_url, content, timeout=10):
    payload = {
        "msgtype": "text",
        "text": {
            "content": content,
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"企业微信推送失败: {exc}") from exc

    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"企业微信返回非 JSON: {body}") from exc

    if result.get("errcode") != 0:
        raise RuntimeError(f"企业微信推送失败: {result}")


def should_send_wechat(last_sent_at, now, interval_seconds):
    return last_sent_at is None or now - last_sent_at >= interval_seconds


def fetch_etf_rows(codes):
    warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError("缺少依赖 akshare，请先执行: python3 -m pip install akshare") from exc

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        df = ak.fund_etf_spot_em()
    df = df.copy()
    df["代码"] = df["代码"].astype(str).str.zfill(6)

    wanted = [str(code).zfill(6) for code in codes]
    indexed_rows = {
        str(row["代码"]).zfill(6): row.to_dict()
        for _, row in df[df["代码"].isin(wanted)].iterrows()
    }
    return [indexed_rows[code] for code in wanted if code in indexed_rows]


def log_once(codes, wechat_webhook_url=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = fetch_etf_rows(codes)
    found_codes = {str(row.get("代码", "")).zfill(6) for row in rows}

    if not rows:
        logging.warning("%s | 未找到 ETF：%s", timestamp, ", ".join(codes))
        return []

    log_lines = []
    for row in rows:
        line = build_log_line(row)
        log_lines.append(line)
        logging.info("%s %s", timestamp, line)

    missing = [code for code in codes if code not in found_codes]
    if missing:
        logging.warning("%s | 未找到 ETF：%s", timestamp, ", ".join(missing))

    if wechat_webhook_url:
        try:
            send_wechat_text(wechat_webhook_url, build_wechat_message(timestamp, log_lines))
        except RuntimeError:
            logging.exception("企业微信推送失败，本轮行情已保留在终端日志")

    return log_lines


def watch(codes, interval_seconds, wechat_webhook_url=None, wechat_interval_seconds=DEFAULT_WECHAT_INTERVAL_SECONDS):
    logging.info(
        "ETF 监控已启动 | 标的：%s | 获取间隔：%s 秒 | 微信间隔：%s 秒 | Ctrl-C 退出",
        ", ".join(codes),
        interval_seconds,
        wechat_interval_seconds if wechat_webhook_url else "不发送",
    )
    last_wechat_sent_at = None
    while True:
        started_at = time.monotonic()
        try:
            webhook_for_this_round = None
            if wechat_webhook_url and should_send_wechat(last_wechat_sent_at, started_at, wechat_interval_seconds):
                webhook_for_this_round = wechat_webhook_url

            log_once(codes, webhook_for_this_round)
            if webhook_for_this_round:
                last_wechat_sent_at = started_at
        except Exception:
            logging.exception("本轮获取失败")

        elapsed = time.monotonic() - started_at
        time.sleep(max(0, interval_seconds - elapsed))


def parse_args():
    parser = argparse.ArgumentParser(description="定时打印指定 ETF 的实时行情。")
    parser.add_argument("--codes", nargs="+", default=DEFAULT_CODES, help="ETF 代码列表")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS, help="行情获取间隔秒数")
    parser.add_argument("--once", action="store_true", help="只获取一次，便于测试")
    parser.add_argument(
        "--wechat-webhook",
        default=os.getenv("WECHAT_WEBHOOK_URL", DEFAULT_WECHAT_WEBHOOK_URL),
        help="企业微信机器人 Webhook；也可通过 WECHAT_WEBHOOK_URL 环境变量配置",
    )
    parser.add_argument("--wechat-interval", type=int, default=DEFAULT_WECHAT_INTERVAL_SECONDS, help="企业微信发送间隔秒数")
    parser.add_argument("--no-wechat", action="store_true", help="只打印日志，不发送企业微信")
    return parser.parse_args()


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args()
    codes = [str(code).zfill(6) for code in args.codes]
    wechat_webhook_url = None if args.no_wechat else args.wechat_webhook

    try:
        if args.once:
            log_once(codes, wechat_webhook_url)
            return

        watch(codes, args.interval, wechat_webhook_url, args.wechat_interval)
    except RuntimeError as exc:
        logging.error("%s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
