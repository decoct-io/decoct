"""Tests for entity-graph compression statistics."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from decoct.cli import cli
from decoct.entity_graph_stats import (
    EntityGraphStatsReport,
    compute_stats,
    format_stats_json,
    format_stats_markdown,
)

FIXTURES = Path(__file__).parent / "fixtures"
IOSXR_CONFIGS = FIXTURES / "iosxr" / "configs"
ENTITY_GRAPH_OUTPUT = Path(__file__).parent.parent / "output" / "entity-graph"


class TestComputeStats:
    def test_input_file_count(self) -> None:
        report = compute_stats(IOSXR_CONFIGS, ENTITY_GRAPH_OUTPUT)
        assert report.input_stats.file_count == 86

    def test_output_file_count(self) -> None:
        report = compute_stats(IOSXR_CONFIGS, ENTITY_GRAPH_OUTPUT)
        # 1 tier_a + 5 classes + 5 instances = 11
        assert report.output_total_files == 11

    def test_five_types(self) -> None:
        report = compute_stats(IOSXR_CONFIGS, ENTITY_GRAPH_OUTPUT)
        assert len(report.type_stats) == 5
        type_ids = {ts.type_id for ts in report.type_stats}
        assert type_ids == {
            "iosxr-access-pe",
            "iosxr-bng",
            "iosxr-p-core",
            "iosxr-rr",
            "iosxr-services-pe",
        }

    def test_output_tokens_less_than_input(self) -> None:
        report = compute_stats(IOSXR_CONFIGS, ENTITY_GRAPH_OUTPUT)
        assert report.output_total_tokens < report.input_stats.total_tokens
        assert report.savings_pct_tokens > 0

    def test_per_type_entity_counts(self) -> None:
        report = compute_stats(IOSXR_CONFIGS, ENTITY_GRAPH_OUTPUT)
        by_type = {ts.type_id: ts for ts in report.type_stats}
        assert by_type["iosxr-access-pe"].entity_count == 60
        assert by_type["iosxr-rr"].entity_count == 4
        assert by_type["iosxr-bng"].entity_count == 8

    def test_phone_book_width_positive(self) -> None:
        report = compute_stats(IOSXR_CONFIGS, ENTITY_GRAPH_OUTPUT)
        for ts in report.type_stats:
            assert ts.phone_book_width > 0, f"{ts.type_id} has zero phone_book_width"

    def test_access_pe_has_classes(self) -> None:
        report = compute_stats(IOSXR_CONFIGS, ENTITY_GRAPH_OUTPUT)
        by_type = {ts.type_id: ts for ts in report.type_stats}
        ape = by_type["iosxr-access-pe"]
        assert ape.class_count > 0
        assert ape.subclass_count > 0

    def test_rr_base_only_ratio(self) -> None:
        report = compute_stats(IOSXR_CONFIGS, ENTITY_GRAPH_OUTPUT)
        by_type = {ts.type_id: ts for ts in report.type_stats}
        assert by_type["iosxr-rr"].base_only_ratio == 1.0

    def test_encoding_parameter(self) -> None:
        report = compute_stats(IOSXR_CONFIGS, ENTITY_GRAPH_OUTPUT, encoding="o200k_base")
        assert report.encoding == "o200k_base"
        assert report.input_stats.total_tokens > 0

    def test_timestamp_set(self) -> None:
        report = compute_stats(IOSXR_CONFIGS, ENTITY_GRAPH_OUTPUT)
        assert report.timestamp != ""

    def test_base_attr_count_positive(self) -> None:
        report = compute_stats(IOSXR_CONFIGS, ENTITY_GRAPH_OUTPUT)
        for ts in report.type_stats:
            assert ts.base_attr_count > 0, f"{ts.type_id} has zero base_attr_count"


class TestFormatStatsMarkdown:
    def test_contains_section_headers(self) -> None:
        report = compute_stats(IOSXR_CONFIGS, ENTITY_GRAPH_OUTPUT)
        md = format_stats_markdown(report)
        assert "# Entity-Graph Compression Statistics" in md
        assert "## Input Corpus" in md
        assert "## Output Summary" in md
        assert "## Compression Ratios" in md
        assert "## Per-Type Breakdown" in md
        assert "## Entity-Graph Structure" in md

    def test_contains_type_names(self) -> None:
        report = compute_stats(IOSXR_CONFIGS, ENTITY_GRAPH_OUTPUT)
        md = format_stats_markdown(report)
        assert "iosxr-access-pe" in md
        assert "iosxr-rr" in md


class TestFormatStatsJson:
    def test_valid_json(self) -> None:
        report = compute_stats(IOSXR_CONFIGS, ENTITY_GRAPH_OUTPUT)
        raw = format_stats_json(report)
        data = json.loads(raw)
        assert "input_stats" in data
        assert "output" in data
        assert "compression" in data
        assert "type_stats" in data

    def test_json_has_expected_keys(self) -> None:
        report = compute_stats(IOSXR_CONFIGS, ENTITY_GRAPH_OUTPUT)
        data = json.loads(format_stats_json(report))
        assert data["input_stats"]["file_count"] == 86
        assert data["output"]["total_files"] == 11
        assert data["compression"]["savings_pct_tokens"] > 0
        assert len(data["type_stats"]) == 5


class TestEntityGraphStatsCLI:
    def test_markdown_output(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, [
            "entity-graph", "stats",
            "-i", str(IOSXR_CONFIGS),
            "-o", str(ENTITY_GRAPH_OUTPUT),
        ])
        assert result.exit_code == 0
        assert "Entity-Graph Compression Statistics" in result.output

    def test_json_output(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, [
            "entity-graph", "stats",
            "-i", str(IOSXR_CONFIGS),
            "-o", str(ENTITY_GRAPH_OUTPUT),
            "--format", "json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "input_stats" in data

    def test_output_to_file(self, tmp_path: Path) -> None:
        out = tmp_path / "report.md"
        runner = CliRunner()
        result = runner.invoke(cli, [
            "entity-graph", "stats",
            "-i", str(IOSXR_CONFIGS),
            "-o", str(ENTITY_GRAPH_OUTPUT),
            "--output", str(out),
        ])
        assert result.exit_code == 0
        assert out.exists()
        assert "Entity-Graph Compression Statistics" in out.read_text()

    def test_missing_input_dir_error(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, [
            "entity-graph", "stats",
            "-i", "/nonexistent/path",
            "-o", str(ENTITY_GRAPH_OUTPUT),
        ])
        assert result.exit_code != 0
