"""Data models for LLM-based evaluation question generation and weighted scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EvalQuestionClass(Enum):
    """Question classes with different scoring weights."""

    FACTUAL_RETRIEVAL = "FACTUAL_RETRIEVAL"
    CROSS_REFERENCE = "CROSS_REFERENCE"
    OPERATIONAL_INFERENCE = "OPERATIONAL_INFERENCE"
    DESIGN_COMPLIANCE = "DESIGN_COMPLIANCE"
    NEGATIVE_ABSENCE = "NEGATIVE_ABSENCE"


MAX_SCORE: dict[EvalQuestionClass, int] = {
    EvalQuestionClass.FACTUAL_RETRIEVAL: 1,
    EvalQuestionClass.CROSS_REFERENCE: 2,
    EvalQuestionClass.OPERATIONAL_INFERENCE: 3,
    EvalQuestionClass.DESIGN_COMPLIANCE: 2,
    EvalQuestionClass.NEGATIVE_ABSENCE: 2,
}


class Difficulty(Enum):
    """Question difficulty level."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass
class EvalQuestion:
    """A single evaluation question with metadata."""

    id: str
    question_class: EvalQuestionClass
    difficulty: Difficulty
    question: str
    reference_answer: str
    evidence_locations: list[str] = field(default_factory=list)
    reasoning_required: str = ""


@dataclass
class EvalQuestionBank:
    """A collection of evaluation questions with generation metadata."""

    questions: list[EvalQuestion] = field(default_factory=list)
    version: int = 1
    source: str = ""
    generated_by: str = "decoct-generate-eval"
    model_generate: str = ""
    model_validate: str = ""

    @property
    def by_class(self) -> dict[EvalQuestionClass, list[EvalQuestion]]:
        result: dict[EvalQuestionClass, list[EvalQuestion]] = {}
        for q in self.questions:
            result.setdefault(q.question_class, []).append(q)
        return result

    @property
    def class_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for q in self.questions:
            counts[q.question_class.value] = counts.get(q.question_class.value, 0) + 1
        return dict(sorted(counts.items()))


@dataclass
class EvalAnswerResult:
    """Result from evaluating a single question with weighted scoring."""

    question_id: str
    question_class: EvalQuestionClass
    question: str
    reference_answer: str
    model_answer: str
    score: int
    max_score: int
    judge_reasoning: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0


@dataclass
class EvalEvaluationRun:
    """Results from evaluating a question bank under one condition."""

    condition: str  # "raw" or "compressed"
    model_answer: str = ""
    model_judge: str = ""
    context_tokens: int = 0
    results: list[EvalAnswerResult] = field(default_factory=list)

    @property
    def total_score(self) -> int:
        return sum(r.score for r in self.results)

    @property
    def max_total_score(self) -> int:
        return sum(r.max_score for r in self.results)

    @property
    def score_by_class(self) -> dict[str, tuple[int, int]]:
        """Return {class_name: (scored, max)} per question class."""
        by_cls: dict[str, list[EvalAnswerResult]] = {}
        for r in self.results:
            by_cls.setdefault(r.question_class.value, []).append(r)
        return {
            cls: (sum(r.score for r in results), sum(r.max_score for r in results))
            for cls, results in sorted(by_cls.items())
        }

    @property
    def pct_by_class(self) -> dict[str, float]:
        """Return {class_name: pct} per question class."""
        return {
            cls: scored / mx if mx > 0 else 0.0
            for cls, (scored, mx) in self.score_by_class.items()
        }


@dataclass
class EvalEvaluationReport:
    """Report comparing weighted evaluation runs across conditions."""

    timestamp: str = ""
    source: str = ""
    question_count: int = 0
    runs: list[EvalEvaluationRun] = field(default_factory=list)
