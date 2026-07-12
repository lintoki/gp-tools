from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
SKILL = ROOT / ".agents" / "skills" / "a-share-daily-research" / "SKILL.md"


def test_skill_has_valid_frontmatter_and_required_sequence() -> None:
    text = SKILL.read_text(encoding="utf-8")
    _, frontmatter, body = text.split("---", 2)
    metadata = yaml.safe_load(frontmatter)
    assert set(metadata) == {"name", "description"}
    assert metadata["name"] == "a-share-daily-research"
    assert metadata["description"].startswith("Use when")
    steps = [
        "update-data",
        "validate-data",
        "run-evidence-gate",
        "compute-factors",
        "rank-industries",
        "select-candidates",
        "backtest",
        "daily-report",
    ]
    positions = [body.index(step) for step in steps]
    assert positions == sorted(positions)


def test_skill_forbids_uncomputed_data_and_trading() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert "不得生成未经程序计算的数据" in text
    assert "数据门禁失败" in text
    assert "停止" in text
    assert "不得自动交易" in text
    assert "不得无限重试" in text


def test_skill_can_run_from_any_workspace() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert r"D:\Dev\Code\gp-tools\a_share_quant_research" in text
    assert "Set-Location" in text
