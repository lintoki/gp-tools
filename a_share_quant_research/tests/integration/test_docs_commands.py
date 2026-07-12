import re
from pathlib import Path

from a_share_research.cli import COMMANDS

ROOT = Path(__file__).parents[2]


def test_required_documents_exist_and_cover_all_commands() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    plans = (ROOT / "PLANS.md").read_text(encoding="utf-8")
    documented = set(
        re.findall(
            r"`(init-db|update-data|validate-data|build-universe|compute-factors|run-evidence-gate|rank-industries|select-candidates|backtest|walk-forward|daily-report)`",
            readme,
        )
    )
    assert set(COMMANDS) <= documented
    assert "BLOCKED_DATA" in readme
    assert "不自动下单" in readme
    assert "raw" in architecture and "normalized" in architecture and "curated" in architecture
    assert "已知问题" in plans
