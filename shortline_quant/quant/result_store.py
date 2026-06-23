import csv
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List


class ResultStore:
    def __init__(self, root: Path, keep_last: int = 5):
        self.root = root
        self.keep_last = keep_last
        self.root.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        summary: Dict[str, Any],
        trades: List[Dict[str, Any]],
        equity_curve: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        run_id = summary["run_id"]
        run_dir = self.root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        _write_json(run_dir / "summary.json", summary)
        _write_csv(run_dir / "trades.csv", trades)
        _write_csv(run_dir / "equity_curve.csv", equity_curve)
        self._prune()
        return {"summary": summary, "trades": trades, "equity_curve": equity_curve}

    def list_runs(self) -> List[Dict[str, Any]]:
        runs = []
        for run_dir in self._run_dirs():
            summary_path = run_dir / "summary.json"
            if summary_path.exists():
                with summary_path.open("r", encoding="utf-8") as fp:
                    runs.append(json.load(fp))
        return sorted(runs, key=lambda item: item.get("run_id", ""), reverse=True)

    def load(self, run_id: str) -> Dict[str, Any]:
        run_dir = self.root / run_id
        summary_path = run_dir / "summary.json"
        if not summary_path.exists():
            raise FileNotFoundError(f"backtest run not found: {run_id}")
        with summary_path.open("r", encoding="utf-8") as fp:
            summary = json.load(fp)
        return {
            "summary": summary,
            "trades": _read_csv(run_dir / "trades.csv"),
            "equity_curve": _read_csv(run_dir / "equity_curve.csv"),
        }

    def _prune(self) -> None:
        for run_dir in self._run_dirs()[self.keep_last :]:
            shutil.rmtree(run_dir)

    def _run_dirs(self) -> List[Path]:
        dirs = [path for path in self.root.iterdir() if path.is_dir()]
        return sorted(dirs, key=lambda path: path.name, reverse=True)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    keys = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _read_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fp:
        return list(csv.DictReader(fp))
