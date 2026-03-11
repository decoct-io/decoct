"""Tests for eval_evaluate.py — weighted evaluation harness."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

from decoct.qa.eval_evaluate import (
    _parse_batch_response,
    format_eval_report_json,
    format_eval_report_markdown,
)
from decoct.qa.eval_models import (
    Difficulty,
    EvalAnswerResult,
    EvalEvaluationReport,
    EvalEvaluationRun,
    EvalQuestion,
    EvalQuestionBank,
    EvalQuestionClass,
)


class TestParseBatchResponse:
    def test_plain_json(self) -> None:
        text = json.dumps([{"id": "FR-001", "answer": "9000"}, {"id": "FR-002", "answer": "1500"}])
        result = _parse_batch_response(text)
        assert result == {"FR-001": "9000", "FR-002": "1500"}

    def test_json_in_code_block(self) -> None:
        text = '```json\n[{"id": "FR-001", "answer": "yes"}]\n```'
        result = _parse_batch_response(text)
        assert result == {"FR-001": "yes"}

    def test_malformed_json_returns_empty(self) -> None:
        result = _parse_batch_response("not json at all")
        assert result == {}

    def test_empty_string(self) -> None:
        result = _parse_batch_response("")
        assert result == {}


class TestFormatEvalReportMarkdown:
    def test_empty_report(self) -> None:
        report = EvalEvaluationReport(
            timestamp="2026-01-01T00:00:00Z",
            source="test",
            question_count=0,
        )
        md = format_eval_report_markdown(report)
        assert "No evaluation runs" in md

    def test_single_run(self) -> None:
        run = EvalEvaluationRun(
            condition="raw",
            model_answer="test-model",
            model_judge="judge-model",
            context_tokens=5000,
            results=[
                EvalAnswerResult(
                    question_id="FR-001",
                    question_class=EvalQuestionClass.FACTUAL_RETRIEVAL,
                    question="Q?",
                    reference_answer="A",
                    model_answer="A",
                    score=1,
                    max_score=1,
                ),
            ],
        )
        report = EvalEvaluationReport(
            timestamp="2026-01-01",
            source="test",
            question_count=1,
            runs=[run],
        )
        md = format_eval_report_markdown(report)
        assert "test" in md
        assert "raw" in md
        assert "FACTUAL_RETRIEVAL" in md

    def test_two_runs_show_comparison(self) -> None:
        run1 = EvalEvaluationRun(
            condition="raw",
            context_tokens=10000,
            results=[
                EvalAnswerResult(
                    question_id="FR-001",
                    question_class=EvalQuestionClass.FACTUAL_RETRIEVAL,
                    question="Q?",
                    reference_answer="A",
                    model_answer="A",
                    score=1,
                    max_score=1,
                ),
            ],
        )
        run2 = EvalEvaluationRun(
            condition="compressed",
            context_tokens=2000,
            results=[
                EvalAnswerResult(
                    question_id="FR-001",
                    question_class=EvalQuestionClass.FACTUAL_RETRIEVAL,
                    question="Q?",
                    reference_answer="A",
                    model_answer="A",
                    score=1,
                    max_score=1,
                ),
            ],
        )
        report = EvalEvaluationReport(
            timestamp="2026-01-01",
            source="test",
            question_count=1,
            runs=[run1, run2],
        )
        md = format_eval_report_markdown(report)
        assert "Comparison" in md
        assert "delta" in md.lower()


class TestFormatEvalReportJson:
    def test_valid_json(self) -> None:
        report = EvalEvaluationReport(
            timestamp="2026-01-01",
            source="test",
            question_count=1,
            runs=[
                EvalEvaluationRun(
                    condition="raw",
                    model_answer="m",
                    model_judge="j",
                    context_tokens=100,
                    results=[
                        EvalAnswerResult(
                            question_id="FR-001",
                            question_class=EvalQuestionClass.FACTUAL_RETRIEVAL,
                            question="Q?",
                            reference_answer="A",
                            model_answer="A",
                            score=1,
                            max_score=1,
                        ),
                    ],
                ),
            ],
        )
        result = format_eval_report_json(report)
        data = json.loads(result)
        assert data["source"] == "test"
        assert data["runs"][0]["total_score"] == 1
        assert data["runs"][0]["results"][0]["question_class"] == "FACTUAL_RETRIEVAL"


class TestEvaluateEvalQuestions:
    @patch("decoct.qa.eval_evaluate._call_llm")
    def test_factual_auto_scored(self, mock_llm: MagicMock, tmp_path: Path) -> None:
        """Factual questions are auto-scored without judge LLM call."""
        cfg_dir = tmp_path / "configs"
        cfg_dir.mkdir()
        (cfg_dir / "test.cfg").write_text("hostname test-router\nmtu 9000")

        bank = EvalQuestionBank(
            questions=[
                EvalQuestion(
                    id="FR-001",
                    question_class=EvalQuestionClass.FACTUAL_RETRIEVAL,
                    difficulty=Difficulty.EASY,
                    question="What is the MTU?",
                    reference_answer="9000",
                ),
            ],
            source="test",
        )

        # Mock answer batch — return correct answer
        mock_llm.return_value = json.dumps([{"id": "FR-001", "answer": "9000"}])

        from decoct.qa.eval_evaluate import evaluate_eval_questions

        run = evaluate_eval_questions(
            bank,
            config_dir=cfg_dir,
            output_dir=None,
            condition="raw",
            model_answer="test",
            model_judge="judge",
            base_url="http://fake",
            api_key_env="FAKE_KEY",
        )

        assert len(run.results) == 1
        assert run.results[0].score == 1
        assert run.results[0].max_score == 1
        assert run.results[0].judge_reasoning == ""  # No judge for factual

    @patch("decoct.qa.eval_evaluate._call_llm")
    def test_non_factual_uses_judge(self, mock_llm: MagicMock, tmp_path: Path) -> None:
        """Non-factual questions go through LLM judge."""
        cfg_dir = tmp_path / "configs"
        cfg_dir.mkdir()
        (cfg_dir / "test.cfg").write_text("hostname test-router")

        bank = EvalQuestionBank(
            questions=[
                EvalQuestion(
                    id="CR-001",
                    question_class=EvalQuestionClass.CROSS_REFERENCE,
                    difficulty=Difficulty.MEDIUM,
                    question="Which routers share OSPF area?",
                    reference_answer="router-01, router-02",
                ),
            ],
            source="test",
        )

        # First call = answer, second call = judge
        mock_llm.side_effect = [
            json.dumps([{"id": "CR-001", "answer": "router-01 and router-02"}]),
            textwrap.dedent("""\
            ```yaml
            - id: "CR-001"
              score: 2
              reasoning: "Correct relationship identified"
            ```
            """),
        ]

        from decoct.qa.eval_evaluate import evaluate_eval_questions

        run = evaluate_eval_questions(
            bank,
            config_dir=cfg_dir,
            output_dir=None,
            condition="raw",
            model_answer="test",
            model_judge="judge",
            base_url="http://fake",
            api_key_env="FAKE_KEY",
        )

        assert len(run.results) == 1
        assert run.results[0].score == 2
        assert run.results[0].max_score == 2
        assert run.results[0].judge_reasoning == "Correct relationship identified"

    @patch("decoct.qa.eval_evaluate._call_llm")
    def test_score_clamped_to_max(self, mock_llm: MagicMock, tmp_path: Path) -> None:
        """Scores from judge are clamped to valid range."""
        cfg_dir = tmp_path / "configs"
        cfg_dir.mkdir()
        (cfg_dir / "test.cfg").write_text("hostname test-router")

        bank = EvalQuestionBank(
            questions=[
                EvalQuestion(
                    id="CR-001",
                    question_class=EvalQuestionClass.CROSS_REFERENCE,
                    difficulty=Difficulty.MEDIUM,
                    question="Q?",
                    reference_answer="A",
                ),
            ],
            source="test",
        )

        mock_llm.side_effect = [
            json.dumps([{"id": "CR-001", "answer": "some answer"}]),
            textwrap.dedent("""\
            ```yaml
            - id: "CR-001"
              score: 99
              reasoning: "Overscored"
            ```
            """),
        ]

        from decoct.qa.eval_evaluate import evaluate_eval_questions

        run = evaluate_eval_questions(
            bank,
            config_dir=cfg_dir,
            output_dir=None,
            condition="raw",
            model_answer="test",
            model_judge="judge",
            base_url="http://fake",
            api_key_env="FAKE_KEY",
        )

        # Score should be clamped to max_score (2 for CROSS_REFERENCE)
        assert run.results[0].score == 2
