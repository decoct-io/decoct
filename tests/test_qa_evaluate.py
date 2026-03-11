"""Tests for QA evaluation module (LLM calls mocked)."""

from __future__ import annotations

from pathlib import Path

from decoct.qa.evaluate import (
    AnswerResult,
    EvaluationReport,
    EvaluationRun,
    build_compressed_context,
    build_raw_context,
    format_evaluation_json,
    format_evaluation_markdown,
)
from decoct.qa.questions import QuestionCategory

FIXTURES = Path(__file__).parent / "fixtures"
IOSXR_CONFIGS = FIXTURES / "iosxr" / "configs"
ENTITY_GRAPH_OUTPUT = Path(__file__).parent.parent / "output" / "iosxr"
MANUAL_PATH = Path(__file__).parent.parent / "docs" / "entity-graph-data-manual.md"


class TestBuildRawContext:
    def test_contains_hostname(self) -> None:
        ctx = build_raw_context(IOSXR_CONFIGS)
        assert "hostname" in ctx

    def test_contains_file_separators(self) -> None:
        ctx = build_raw_context(IOSXR_CONFIGS)
        assert "--- APE-R1-01.cfg ---" in ctx

    def test_max_entities_limits_files(self) -> None:
        full = build_raw_context(IOSXR_CONFIGS)
        limited = build_raw_context(IOSXR_CONFIGS, max_entities=5)
        assert len(limited) < len(full)


class TestBuildCompressedContext:
    def test_contains_types(self) -> None:
        ctx = build_compressed_context(ENTITY_GRAPH_OUTPUT)
        assert "types:" in ctx

    def test_contains_tier_a_separator(self) -> None:
        ctx = build_compressed_context(ENTITY_GRAPH_OUTPUT)
        assert "--- tier_a.yaml ---" in ctx

    def test_with_manual(self) -> None:
        if MANUAL_PATH.exists():
            ctx = build_compressed_context(ENTITY_GRAPH_OUTPUT, MANUAL_PATH)
            assert "--- Reader Manual ---" in ctx


class TestEvaluationRunProperties:
    def test_accuracy_all_correct(self) -> None:
        run = EvaluationRun(condition="test", model="test")
        run.results = [
            AnswerResult("q1", QuestionCategory.SINGLE_VALUE, "?", "a", "a", True),
            AnswerResult("q2", QuestionCategory.SINGLE_VALUE, "?", "b", "b", True),
        ]
        assert run.accuracy == 1.0

    def test_accuracy_half_correct(self) -> None:
        run = EvaluationRun(condition="test", model="test")
        run.results = [
            AnswerResult("q1", QuestionCategory.SINGLE_VALUE, "?", "a", "a", True),
            AnswerResult("q2", QuestionCategory.SINGLE_VALUE, "?", "b", "x", False),
        ]
        assert run.accuracy == 0.5

    def test_accuracy_empty(self) -> None:
        run = EvaluationRun(condition="test", model="test")
        assert run.accuracy == 0.0

    def test_accuracy_by_category(self) -> None:
        run = EvaluationRun(condition="test", model="test")
        run.results = [
            AnswerResult("q1", QuestionCategory.SINGLE_VALUE, "?", "a", "a", True),
            AnswerResult("q2", QuestionCategory.SINGLE_VALUE, "?", "b", "x", False),
            AnswerResult("q3", QuestionCategory.COUNT, "?", "3", "3", True),
        ]
        by_cat = run.accuracy_by_category
        assert by_cat["SINGLE_VALUE"] == 0.5
        assert by_cat["COUNT"] == 1.0

    def test_total_answer_tokens(self) -> None:
        run = EvaluationRun(condition="test", model="test")
        run.results = [
            AnswerResult("q1", QuestionCategory.SINGLE_VALUE, "?", "a", "a", True, output_tokens=10),
            AnswerResult("q2", QuestionCategory.SINGLE_VALUE, "?", "b", "b", True, output_tokens=15),
        ]
        assert run.total_answer_tokens == 25


class TestFormatEvaluationMarkdown:
    def test_contains_headers(self) -> None:
        report = EvaluationReport(
            timestamp="2026-01-01T00:00:00+00:00",
            question_count=2,
            runs=[
                EvaluationRun(
                    condition="raw", model="test", context_tokens=1000,
                    results=[
                        AnswerResult("q1", QuestionCategory.SINGLE_VALUE, "?", "a", "a", True),
                    ],
                ),
            ],
        )
        md = format_evaluation_markdown(report)
        assert "# QA Comprehension Evaluation" in md
        assert "## Summary" in md
        assert "## Accuracy by Category" in md

    def test_comparison_section_with_two_runs(self) -> None:
        report = EvaluationReport(
            timestamp="2026-01-01T00:00:00+00:00",
            question_count=1,
            runs=[
                EvaluationRun(
                    condition="raw", model="test", context_tokens=1000,
                    results=[AnswerResult("q1", QuestionCategory.SINGLE_VALUE, "?", "a", "a", True)],
                ),
                EvaluationRun(
                    condition="compressed", model="test", context_tokens=500,
                    results=[AnswerResult("q1", QuestionCategory.SINGLE_VALUE, "?", "a", "a", True)],
                ),
            ],
        )
        md = format_evaluation_markdown(report)
        assert "## Comparison" in md


class TestFormatEvaluationJson:
    def test_valid_json(self) -> None:
        import json

        report = EvaluationReport(
            timestamp="2026-01-01T00:00:00+00:00",
            question_count=1,
            runs=[
                EvaluationRun(
                    condition="raw", model="test", context_tokens=1000,
                    results=[
                        AnswerResult("q1", QuestionCategory.SINGLE_VALUE, "?", "a", "a", True),
                    ],
                ),
            ],
        )
        raw = format_evaluation_json(report)
        data = json.loads(raw)
        assert "runs" in data
        assert len(data["runs"]) == 1
        assert data["runs"][0]["accuracy"] == 1.0


class TestParseBatchResponse:
    def test_parse_json_array(self) -> None:
        from decoct.qa.evaluate import _parse_batch_response

        text = '[{"id": "q1", "answer": "hello"}, {"id": "q2", "answer": "world"}]'
        result = _parse_batch_response(text)
        assert result == {"q1": "hello", "q2": "world"}

    def test_parse_code_block(self) -> None:
        from decoct.qa.evaluate import _parse_batch_response

        text = '```json\n[{"id": "q1", "answer": "42"}]\n```'
        result = _parse_batch_response(text)
        assert result == {"q1": "42"}

    def test_parse_invalid_json(self) -> None:
        from decoct.qa.evaluate import _parse_batch_response

        result = _parse_batch_response("not json at all")
        assert result == {}
