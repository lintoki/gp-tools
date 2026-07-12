from a_share_research.cli import main


def test_cli_help_returns_zero(capsys) -> None:
    assert main(["--help"]) == 0
    output = capsys.readouterr().out
    assert "daily-report" in output
    assert "validate-data" in output
