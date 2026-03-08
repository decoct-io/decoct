"""Tests for decoct CLI."""

from click.testing import CliRunner

from decoct.cli import cli


def test_cli_version() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_cli_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "infrastructure context compression" in result.output.lower()


def test_compress_stub() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["compress"])
    assert "not yet implemented" in result.output
