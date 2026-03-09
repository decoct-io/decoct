"""Tests for decoct CLI."""

from pathlib import Path

from click.testing import CliRunner

from decoct.cli import cli

FIXTURES = Path(__file__).parent / "fixtures"
YAML_FIXTURES = FIXTURES / "yaml"
SCHEMA_FIXTURES = FIXTURES / "schemas"
ASSERTION_FIXTURES = FIXTURES / "assertions"
PROFILE_FIXTURES = FIXTURES / "profiles"


# ── Basic CLI tests ──


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


def test_compress_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["compress", "--help"])
    assert result.exit_code == 0
    assert "--schema" in result.output
    assert "--assertions" in result.output
    assert "--profile" in result.output


# ── Compress from file ──


def test_compress_basic_file() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["compress", str(YAML_FIXTURES / "with-defaults.yaml")])
    assert result.exit_code == 0
    assert "services" in result.output


def test_compress_with_schema() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [
        "compress",
        str(YAML_FIXTURES / "with-defaults.yaml"),
        "--schema", str(SCHEMA_FIXTURES / "docker-compose.yaml"),
    ])
    assert result.exit_code == 0
    # Schema defaults should be stripped — e.g. restart: "no" is a default
    assert result.output  # produces output


def test_compress_with_assertions() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [
        "compress",
        str(YAML_FIXTURES / "with-assertions.yaml"),
        "--assertions", str(ASSERTION_FIXTURES / "test-must-assertions.yaml"),
    ])
    assert result.exit_code == 0
    # Conformant values should be stripped (web service)
    # Deviating values should remain annotated (db service)
    assert "postgres:latest" in result.output
    assert "deviations from standards" in result.output


def test_compress_with_schema_and_assertions() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [
        "compress",
        str(YAML_FIXTURES / "with-assertions.yaml"),
        "--schema", str(SCHEMA_FIXTURES / "docker-compose.yaml"),
        "--assertions", str(ASSERTION_FIXTURES / "test-must-assertions.yaml"),
    ])
    assert result.exit_code == 0
    assert result.output


# ── Stdin support ──


def test_compress_stdin() -> None:
    runner = CliRunner()
    input_yaml = "db:\n  password: hunter2\n  host: localhost\n"
    result = runner.invoke(cli, ["compress"], input=input_yaml)
    assert result.exit_code == 0
    assert "host: localhost" in result.output
    # db.password matches *.password secret path pattern
    assert "[REDACTED]" in result.output


# ── Output file ──


def test_compress_output_file(tmp_path: Path) -> None:
    runner = CliRunner()
    out_file = tmp_path / "output.yaml"
    result = runner.invoke(cli, [
        "compress",
        str(YAML_FIXTURES / "with-defaults.yaml"),
        "--output", str(out_file),
    ])
    assert result.exit_code == 0
    assert out_file.exists()
    content = out_file.read_text()
    assert "services" in content


# ── Stats options ──


def test_compress_stats() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [
        "compress",
        str(YAML_FIXTURES / "with-defaults.yaml"),
        "--stats",
    ])
    assert result.exit_code == 0
    # Stats go to stderr, YAML to stdout
    # CliRunner mixes them by default
    assert "Tokens:" in result.output or "saved" in result.output


def test_compress_stats_only() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [
        "compress",
        str(YAML_FIXTURES / "with-defaults.yaml"),
        "--stats-only",
    ])
    assert result.exit_code == 0
    # Should show stats but NOT the YAML output
    assert "Tokens:" in result.output or "saved" in result.output


# ── Show removed ──


def test_compress_show_removed() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [
        "compress",
        str(YAML_FIXTURES / "with-assertions.yaml"),
        "--assertions", str(ASSERTION_FIXTURES / "test-must-assertions.yaml"),
        "--show-removed",
    ])
    assert result.exit_code == 0
    # Should show pass results
    assert "strip-conformant" in result.output or "Removed:" in result.output


# ── Profile-based compression ──


def test_compress_with_profile() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [
        "compress",
        str(YAML_FIXTURES / "with-defaults.yaml"),
        "--profile", str(PROFILE_FIXTURES / "docker.yaml"),
    ])
    assert result.exit_code == 0
    assert result.output


# ── Error handling ──


def test_compress_invalid_schema() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [
        "compress",
        str(YAML_FIXTURES / "with-defaults.yaml"),
        "--schema", str(YAML_FIXTURES / "with-defaults.yaml"),  # not a valid schema
    ])
    assert result.exit_code != 0


def test_compress_nonexistent_file() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["compress", "/nonexistent/file.yaml"])
    assert result.exit_code != 0


# ── Multiple files ──


def test_compress_multiple_files() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [
        "compress",
        str(YAML_FIXTURES / "with-defaults.yaml"),
        str(YAML_FIXTURES / "with-assertions.yaml"),
    ])
    assert result.exit_code == 0
    # Should output both documents
    assert "services" in result.output
