import html
import json
from pathlib import Path
from typing import Any, Iterable, List, Optional

from .models import CandidateReport
from .retention import prepare_output_file
from .workflow import build_scan_advice


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _fmt_number(value: Any, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return "-"


def _snapshot_value(report: CandidateReport, key: str) -> Optional[Any]:
    return report.snapshot.get(key)


def _reason_list(reasons: List[str], css_class: str) -> str:
    if not reasons:
        return '<span class="muted">-</span>'
    items = "".join(f'<li class="{css_class}">{_esc(reason)}</li>' for reason in reasons)
    return f"<ul>{items}</ul>"


def _report_row(report: CandidateReport) -> str:
    status = "通过" if report.passed else "未通过"
    status_class = "pass" if report.passed else "fail"
    price = _fmt_number(report.entry_price, 3)
    change = _fmt_number(_snapshot_value(report, "change_pct"), 2, "%")
    volume_ratio = _fmt_number(_snapshot_value(report, "volume_ratio"), 2)
    turnover = _fmt_number(_snapshot_value(report, "turnover_pct"), 2, "%")
    market_value = _snapshot_value(report, "total_market_value_yuan")
    market_value_text = "-" if market_value is None else f"{float(market_value) / 100000000:.2f} 亿"
    return f"""
      <tr>
        <td><strong>{_esc(report.code)}</strong><span>{_esc(report.name)}</span></td>
        <td><span class="badge {status_class}">{status}</span></td>
        <td class="num">{price}</td>
        <td class="num">{report.score:.2f}</td>
        <td class="num">{change}</td>
        <td class="num">{volume_ratio}</td>
        <td class="num">{turnover}</td>
        <td class="num">{market_value_text}</td>
        <td>{_reason_list(report.pass_reasons, "ok")}</td>
        <td>{_reason_list(report.fail_reasons, "bad")}</td>
      </tr>
    """


def build_scan_html(scan_time: str, reports: Iterable[CandidateReport]) -> str:
    rows = list(reports)
    advice = build_scan_advice(rows)
    passed_count = sum(1 for report in rows if report.passed)
    failed_count = len(rows) - passed_count
    top_watch = advice.get("watchlist") or []
    watch_items = "".join(f"<li>{_esc(item)}</li>" for item in top_watch) or '<li class="muted">无</li>'
    table_rows = "".join(_report_row(report) for report in rows) or """
      <tr><td colspan="10" class="empty">本轮没有候选进入明细评估。</td></tr>
    """
    payload_json = json.dumps(
        {
            "scan_time": scan_time,
            "advice": advice,
            "reports": [report.__dict__ for report in rows],
        },
        ensure_ascii=False,
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>尾盘隔夜策略扫描 {scan_time}</title>
  <style>
    :root {{
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #17202a;
      --subtle: #667085;
      --line: #d9dee7;
      --green: #137a45;
      --green-bg: #e8f6ee;
      --red: #b42318;
      --red-bg: #fdecec;
      --amber: #98690c;
      --amber-bg: #fff5d6;
      --blue: #175cd3;
      --blue-bg: #e9f1ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }}
    main {{ max-width: 1280px; margin: 0 auto; padding: 28px 24px 40px; }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 24px;
      margin-bottom: 18px;
    }}
    h1 {{ margin: 0; font-size: 28px; letter-spacing: 0; }}
    .time {{ color: var(--subtle); margin-top: 6px; }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin: 16px 0 18px;
    }}
    .metric, .advice, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .metric {{ padding: 14px 16px; }}
    .metric .label {{ color: var(--subtle); font-size: 13px; }}
    .metric .value {{ font-size: 24px; font-weight: 700; margin-top: 4px; }}
    .advice {{
      padding: 18px;
      border-left: 6px solid var(--amber);
      background: var(--amber-bg);
    }}
    .advice.buy {{ border-left-color: var(--green); background: var(--green-bg); }}
    .advice.nodata {{ border-left-color: var(--blue); background: var(--blue-bg); }}
    .advice h2 {{ margin: 0 0 8px; font-size: 20px; }}
    .advice p {{ margin: 6px 0; }}
    .watchlist {{ display: flex; gap: 12px; align-items: flex-start; margin-top: 10px; }}
    .watchlist strong {{ white-space: nowrap; }}
    .watchlist ul {{ margin: 0; padding-left: 18px; }}
    .panel {{ margin-top: 18px; overflow: hidden; }}
    .panel-head {{ padding: 14px 16px; border-bottom: 1px solid var(--line); }}
    .panel-head h2 {{ margin: 0; font-size: 18px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ padding: 12px 10px; border-bottom: 1px solid var(--line); vertical-align: top; text-align: left; }}
    th {{ background: #eef1f5; color: #384250; font-size: 13px; position: sticky; top: 0; }}
    td:first-child span {{ display: block; color: var(--subtle); margin-top: 2px; }}
    .num {{ text-align: right; white-space: nowrap; }}
    .badge {{ display: inline-block; padding: 3px 8px; border-radius: 999px; font-weight: 700; font-size: 12px; }}
    .badge.pass {{ color: var(--green); background: var(--green-bg); }}
    .badge.fail {{ color: var(--red); background: var(--red-bg); }}
    ul {{ margin: 0; padding-left: 18px; }}
    li {{ margin: 2px 0; overflow-wrap: anywhere; }}
    .ok {{ color: var(--green); }}
    .bad {{ color: var(--red); }}
    .muted {{ color: var(--subtle); }}
    .empty {{ text-align: center; color: var(--subtle); padding: 28px; }}
    .raw {{ display: none; }}
    @media (max-width: 860px) {{
      main {{ padding: 18px 12px 28px; }}
      header {{ display: block; }}
      .summary-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .table-wrap {{ overflow-x: auto; }}
      table {{ min-width: 980px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>尾盘隔夜策略扫描</h1>
        <div class="time">执行时间：{_esc(scan_time)}</div>
      </div>
    </header>

    <section class="advice {'buy' if advice['level'] == 'BUY_CANDIDATE' else 'nodata' if advice['level'] == 'NO_DATA' else ''}">
      <h2>{_esc(advice['level'])} · {_esc(advice['summary'])}</h2>
      <p>{_esc(advice['action'])}</p>
      <div class="watchlist">
        <strong>重点观察</strong>
        <ul>{watch_items}</ul>
      </div>
    </section>

    <section class="summary-grid">
      <div class="metric"><div class="label">入选</div><div class="value">{passed_count}</div></div>
      <div class="metric"><div class="label">未通过</div><div class="value">{failed_count}</div></div>
      <div class="metric"><div class="label">明细评估</div><div class="value">{len(rows)}</div></div>
      <div class="metric"><div class="label">策略</div><div class="value">T+1</div></div>
    </section>

    <section class="panel">
      <div class="panel-head"><h2>候选明细</h2></div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>股票</th>
              <th>状态</th>
              <th class="num">参考价</th>
              <th class="num">评分</th>
              <th class="num">涨幅</th>
              <th class="num">量比</th>
              <th class="num">换手</th>
              <th class="num">总市值</th>
              <th>通过项</th>
              <th>过滤项</th>
            </tr>
          </thead>
          <tbody>{table_rows}</tbody>
        </table>
      </div>
    </section>
    <script type="application/json" class="raw">{_esc(payload_json)}</script>
  </main>
</body>
</html>
"""


def write_scan_html(path: Path, scan_time: str, reports: Iterable[CandidateReport]) -> None:
    prepare_output_file(path, "*.html")
    path.write_text(build_scan_html(scan_time, reports), encoding="utf-8")
