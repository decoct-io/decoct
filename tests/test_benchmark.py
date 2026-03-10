"""Tests for the benchmark harness."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from decoct.benchmark import (
    BenchmarkReport,
    FileResult,
    TierResult,
    _expand_paths,
    benchmark_file,
    format_report_json,
    format_report_markdown,
    run_benchmark,
)
from decoct.cli import cli

FIXTURES = Path(__file__).parent / "fixtures"
YAML_FIXTURES = FIXTURES / "yaml"
JSON_FIXTURES = FIXTURES / "json"
INI_FIXTURES = FIXTURES / "ini"


class TestExpandPaths:
    def test_expands_directory_non_recursive(self) -> None:
        paths = _expand_paths([YAML_FIXTURES])
        assert len(paths) > 0
        assert all(p.suffix.lower() in {".yaml", ".yml"} for p in paths)

    def test_expands_directory_recursive(self) -> None:
        paths = _expand_paths([FIXTURES], recursive=True)
        suffixes = {p.suffix.lower() for p in paths}
        assert ".yaml" in suffixes or ".yml" in suffixes
        assert ".json" in suffixes

    def test_single_file(self) -> None:
        paths = _expand_paths([YAML_FIXTURES / "realistic-compose.yaml"])
        assert len(paths) == 1
        assert paths[0].name == "realistic-compose.yaml"

    def test_nonexistent_path_skipped(self, tmp_path: Path) -> None:
        paths = _expand_paths([tmp_path / "nope.yaml"])
        assert paths == []


class TestBenchmarkFile:
    def test_yaml_file_has_generic_tier(self) -> None:
        result = benchmark_file(YAML_FIXTURES / "realistic-compose.yaml")
        assert isinstance(result, FileResult)
        assert result.format == "yaml"
        assert "generic" in result.tiers
        assert result.input_tokens > 0
        assert result.input_lines > 0

    def test_docker_compose_has_schema_tier(self) -> None:
        result = benchmark_file(YAML_FIXTURES / "realistic-compose.yaml")
        assert result.platform == "docker-compose"
        assert "schema" in result.tiers

    def test_json_file(self) -> None:
        result = benchmark_file(JSON_FIXTURES / "tfstate-sample.json")
        assert result.format == "json"
        assert "generic" in result.tiers

    def test_ini_file(self) -> None:
        result = benchmark_file(INI_FIXTURES / "simple-config.ini")
        assert result.format == "ini"
        assert "generic" in result.tiers

    def test_generic_tier_saves_tokens(self) -> None:
        result = benchmark_file(YAML_FIXTURES / "with-secrets.yaml")
        tier = result.tiers["generic"]
        assert isinstance(tier, TierResult)
        assert tier.input_tokens > 0
        assert tier.savings_tokens >= 0
        assert 0 <= tier.savings_pct <= 100
        assert tier.total_time >= 0

    def test_tier_independence(self) -> None:
        """Each tier runs on its own deepcopy, so results are independent."""
        result = benchmark_file(YAML_FIXTURES / "realistic-compose.yaml")
        # Both tiers should exist and have valid token counts
        assert "generic" in result.tiers
        assert "schema" in result.tiers
        # Each tier computes its own output tokens independently
        generic = result.tiers["generic"]
        schema = result.tiers["schema"]
        assert generic.input_tokens == schema.input_tokens == result.input_tokens
        # Output tokens differ because tiers apply different passes
        assert generic.output_tokens != schema.output_tokens

    def test_with_assertions_enables_full_tier(self) -> None:
        from decoct.assertions.loader import load_assertions

        assertions_path = FIXTURES / "assertions" / "deployment-standards.yaml"
        assertions = load_assertions(assertions_path)
        result = benchmark_file(
            YAML_FIXTURES / "realistic-compose.yaml",
            assertions=assertions,
        )
        assert "full" in result.tiers


class TestRunBenchmark:
    def test_single_directory(self) -> None:
        report = run_benchmark([YAML_FIXTURES])
        assert isinstance(report, BenchmarkReport)
        assert len(report.files) > 0
        assert report.encoding == "cl100k_base"
        assert report.timestamp != ""

    def test_recursive(self) -> None:
        report = run_benchmark([FIXTURES], recursive=True)
        formats = {f.format for f in report.files}
        assert len(formats) > 1

    def test_with_assertions(self) -> None:
        assertions_path = str(FIXTURES / "assertions" / "deployment-standards.yaml")
        report = run_benchmark(
            [YAML_FIXTURES / "realistic-compose.yaml"],
            assertions_path=assertions_path,
        )
        assert len(report.files) == 1
        assert "full" in report.files[0].tiers

    def test_empty_directory(self, tmp_path: Path) -> None:
        report = run_benchmark([tmp_path])
        assert len(report.files) == 0


class TestFormatReportMarkdown:
    def test_contains_header_and_table(self) -> None:
        report = run_benchmark([YAML_FIXTURES])
        md = format_report_markdown(report)
        assert "# decoct benchmark" in md
        assert "## Per-File Results" in md
        assert "## Aggregate Summary" in md
        assert "generic" in md

    def test_verbose_includes_timings(self) -> None:
        report = run_benchmark([YAML_FIXTURES / "realistic-compose.yaml"])
        md = format_report_markdown(report, verbose=True)
        assert "## Pass Timings" in md
        assert "strip-secrets" in md

    def test_empty_report(self) -> None:
        report = BenchmarkReport(timestamp="2026-01-01T00:00:00+00:00")
        md = format_report_markdown(report)
        assert "No files processed." in md


class TestFormatReportJson:
    def test_valid_json(self) -> None:
        report = run_benchmark([YAML_FIXTURES / "realistic-compose.yaml"])
        raw = format_report_json(report)
        data = json.loads(raw)
        assert "files" in data
        assert "summary" in data
        assert len(data["files"]) == 1

    def test_summary_has_tier_aggregates(self) -> None:
        report = run_benchmark([YAML_FIXTURES])
        data = json.loads(format_report_json(report))
        assert "generic" in data["summary"]
        assert "input_tokens" in data["summary"]["generic"]
        assert "savings_pct" in data["summary"]["generic"]


class TestBenchmarkCLI:
    def test_basic_invocation(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["benchmark", str(YAML_FIXTURES)])
        assert result.exit_code == 0
        assert "decoct benchmark" in result.output

    def test_json_format(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["benchmark", str(YAML_FIXTURES), "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "files" in data

    def test_recursive(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["benchmark", str(FIXTURES), "-r"])
        assert result.exit_code == 0
        assert "decoct benchmark" in result.output

    def test_verbose(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["benchmark", str(YAML_FIXTURES), "-v"])
        assert result.exit_code == 0
        assert "Pass Timings" in result.output

    def test_output_to_file(self, tmp_path: Path) -> None:
        out = tmp_path / "report.md"
        runner = CliRunner()
        result = runner.invoke(cli, ["benchmark", str(YAML_FIXTURES), "-o", str(out)])
        assert result.exit_code == 0
        assert out.exists()
        assert "decoct benchmark" in out.read_text()

    def test_no_files_error(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["benchmark"])
        assert result.exit_code != 0

    def test_with_assertions(self) -> None:
        assertions = str(FIXTURES / "assertions" / "deployment-standards.yaml")
        runner = CliRunner()
        result = runner.invoke(cli, [
            "benchmark",
            str(YAML_FIXTURES / "realistic-compose.yaml"),
            "--assertions", assertions,
        ])
        assert result.exit_code == 0
        assert "full" in result.output
