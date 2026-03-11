"""Tests for eval_models dataclasses."""

from __future__ import annotations

from decoct.qa.eval_models import (
    MAX_SCORE,
    Difficulty,
    EvalAnswerResult,
    EvalEvaluationReport,
    EvalEvaluationRun,
    EvalQuestion,
    EvalQuestionBank,
    EvalQuestionClass,
)


def _make_question(
    qid: str = "FR-001",
    qclass: EvalQuestionClass = EvalQuestionClass.FACTUAL_RETRIEVAL,
    difficulty: Difficulty = Difficulty.EASY,
) -> EvalQuestion:
    return EvalQuestion(
        id=qid,
        question_class=qclass,
        difficulty=difficulty,
        question="What is the MTU?",
        reference_answer="9000",
        evidence_locations=["router-01.cfg → interfaces"],
        reasoning_required="Direct lookup",
    )


def _make_result(
    qid: str = "FR-001",
    qclass: EvalQuestionClass = EvalQuestionClass.FACTUAL_RETRIEVAL,
    score: int = 1,
    max_score: int = 1,
) -> EvalAnswerResult:
    return EvalAnswerResult(
        question_id=qid,
        question_class=qclass,
        question="What is the MTU?",
        reference_answer="9000",
        model_answer="9000",
        score=score,
        max_score=max_score,
    )


class TestEvalQuestionClass:
    def test_all_classes_have_max_score(self) -> None:
        for cls in EvalQuestionClass:
            assert cls in MAX_SCORE

    def test_max_scores(self) -> None:
        assert MAX_SCORE[EvalQuestionClass.FACTUAL_RETRIEVAL] == 1
        assert MAX_SCORE[EvalQuestionClass.CROSS_REFERENCE] == 2
        assert MAX_SCORE[EvalQuestionClass.OPERATIONAL_INFERENCE] == 3
        assert MAX_SCORE[EvalQuestionClass.DESIGN_COMPLIANCE] == 2
        assert MAX_SCORE[EvalQuestionClass.NEGATIVE_ABSENCE] == 2


class TestEvalQuestion:
    def test_fields(self) -> None:
        q = _make_question()
        assert q.id == "FR-001"
        assert q.question_class == EvalQuestionClass.FACTUAL_RETRIEVAL
        assert q.difficulty == Difficulty.EASY
        assert q.evidence_locations == ["router-01.cfg → interfaces"]

    def test_default_fields(self) -> None:
        q = EvalQuestion(
            id="X",
            question_class=EvalQuestionClass.FACTUAL_RETRIEVAL,
            difficulty=Difficulty.EASY,
            question="Q?",
            reference_answer="A",
        )
        assert q.evidence_locations == []
        assert q.reasoning_required == ""


class TestEvalQuestionBank:
    def test_by_class(self) -> None:
        bank = EvalQuestionBank(questions=[
            _make_question("FR-001", EvalQuestionClass.FACTUAL_RETRIEVAL),
            _make_question("CR-001", EvalQuestionClass.CROSS_REFERENCE),
            _make_question("FR-002", EvalQuestionClass.FACTUAL_RETRIEVAL),
        ])
        by_cls = bank.by_class
        assert len(by_cls[EvalQuestionClass.FACTUAL_RETRIEVAL]) == 2
        assert len(by_cls[EvalQuestionClass.CROSS_REFERENCE]) == 1

    def test_class_counts(self) -> None:
        bank = EvalQuestionBank(questions=[
            _make_question("FR-001", EvalQuestionClass.FACTUAL_RETRIEVAL),
            _make_question("CR-001", EvalQuestionClass.CROSS_REFERENCE),
            _make_question("FR-002", EvalQuestionClass.FACTUAL_RETRIEVAL),
        ])
        counts = bank.class_counts
        assert counts["FACTUAL_RETRIEVAL"] == 2
        assert counts["CROSS_REFERENCE"] == 1

    def test_empty_bank(self) -> None:
        bank = EvalQuestionBank()
        assert bank.by_class == {}
        assert bank.class_counts == {}

    def test_defaults(self) -> None:
        bank = EvalQuestionBank()
        assert bank.version == 1
        assert bank.generated_by == "decoct-generate-eval"
        assert bank.source == ""


class TestEvalEvaluationRun:
    def test_total_score(self) -> None:
        run = EvalEvaluationRun(
            condition="raw",
            results=[
                _make_result("FR-001", score=1, max_score=1),
                _make_result("CR-001", EvalQuestionClass.CROSS_REFERENCE, score=2, max_score=2),
            ],
        )
        assert run.total_score == 3
        assert run.max_total_score == 3

    def test_score_by_class(self) -> None:
        run = EvalEvaluationRun(
            condition="raw",
            results=[
                _make_result("FR-001", score=1, max_score=1),
                _make_result("FR-002", score=0, max_score=1),
                _make_result("CR-001", EvalQuestionClass.CROSS_REFERENCE, score=2, max_score=2),
            ],
        )
        by_cls = run.score_by_class
        assert by_cls["FACTUAL_RETRIEVAL"] == (1, 2)
        assert by_cls["CROSS_REFERENCE"] == (2, 2)

    def test_pct_by_class(self) -> None:
        run = EvalEvaluationRun(
            condition="raw",
            results=[
                _make_result("FR-001", score=1, max_score=1),
                _make_result("FR-002", score=0, max_score=1),
            ],
        )
        pct = run.pct_by_class
        assert pct["FACTUAL_RETRIEVAL"] == 0.5

    def test_empty_run(self) -> None:
        run = EvalEvaluationRun(condition="raw")
        assert run.total_score == 0
        assert run.max_total_score == 0
        assert run.score_by_class == {}
        assert run.pct_by_class == {}


class TestEvalEvaluationReport:
    def test_defaults(self) -> None:
        report = EvalEvaluationReport()
        assert report.timestamp == ""
        assert report.source == ""
        assert report.question_count == 0
        assert report.runs == []
