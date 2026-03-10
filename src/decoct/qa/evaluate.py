"""LLM-based QA evaluation harness for entity-graph comprehension.

Requires the [llm] extra: pip install decoct[llm]
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from decoct.qa.questions import QAPair, QuestionBank, QuestionCategory
from decoct.tokens import count_tokens

_INPUT_EXTENSIONS = {".yaml", ".yml", ".json", ".ini", ".conf", ".cfg", ".cnf", ".properties"}


@dataclass
class AnswerResult:
    """Result from evaluating a single question."""

    question_id: str
    category: QuestionCategory
    question: str
    expected: str
    actual: str
    correct: bool
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0


@dataclass
class EvaluationRun:
    """Results from evaluating a question bank under one condition."""

    condition: str  # "raw" or "compressed"
    model: str
    context_tokens: int = 0
    results: list[AnswerResult] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.correct) / len(self.results)

    @property
    def accuracy_by_category(self) -> dict[str, float]:
        by_cat: dict[str, list[AnswerResult]] = {}
        for r in self.results:
            by_cat.setdefault(r.category.value, []).append(r)
        return {
            cat: sum(1 for r in results if r.correct) / len(results)
            for cat, results in sorted(by_cat.items())
        }

    @property
    def total_answer_tokens(self) -> int:
        return sum(r.output_tokens for r in self.results)


@dataclass
class EvaluationReport:
    """Report comparing evaluation runs across conditions."""

    timestamp: str = ""
    question_count: int = 0
    runs: list[EvaluationRun] = field(default_factory=list)


def build_raw_context(config_dir: Path, *, max_entities: int | None = None) -> str:
    """Build raw context by concatenating .cfg files.

    Args:
        config_dir: Directory of raw config files.
        max_entities: If set, only include this many files.

    Returns:
        Concatenated config text with filename separators.
    """
    cfg_files = sorted(
        f for f in config_dir.iterdir()
        if f.is_file() and f.suffix.lower() in _INPUT_EXTENSIONS
    )
    if max_entities is not None:
        cfg_files = cfg_files[:max_entities]

    parts: list[str] = []
    for f in cfg_files:
        parts.append(f"--- {f.name} ---")
        parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)


def build_compressed_context(
    output_dir: Path,
    manual_path: Path | None = None,
) -> str:
    """Build compressed context from entity-graph output files.

    Concatenates tier_a + all tier_b (classes) + all tier_c (instances).
    Optionally prepends a reader manual.

    Args:
        output_dir: Directory with entity-graph output YAML files.
        manual_path: Optional reader manual .md file.

    Returns:
        Concatenated compressed representation.
    """
    parts: list[str] = []

    if manual_path and manual_path.exists():
        parts.append("--- Reader Manual ---")
        parts.append(manual_path.read_text(encoding="utf-8"))

    # Tier A
    tier_a = output_dir / "tier_a.yaml"
    if tier_a.exists():
        parts.append("--- tier_a.yaml ---")
        parts.append(tier_a.read_text(encoding="utf-8"))

    # Tier B + C files (sorted for determinism)
    for f in sorted(output_dir.iterdir()):
        if f.name == "tier_a.yaml":
            continue
        if f.suffix.lower() in {".yaml", ".yml"}:
            parts.append(f"--- {f.name} ---")
            parts.append(f.read_text(encoding="utf-8"))

    return "\n".join(parts)


def _compare_answers(expected: str, actual: str) -> bool:
    """Fuzzy comparison of expected and actual answers.

    Handles:
    - Case insensitivity
    - Whitespace normalisation
    - Boolean equivalence (yes/true, no/false)
    - Numeric equivalence (leading zeros, trailing decimals)
    """
    # Normalise whitespace and case
    e = " ".join(expected.strip().lower().split())
    a = " ".join(actual.strip().lower().split())

    if e == a:
        return True

    # Boolean equivalence
    true_vals = {"yes", "true", "1", "enabled"}
    false_vals = {"no", "false", "0", "disabled"}
    if e in true_vals and a in true_vals:
        return True
    if e in false_vals and a in false_vals:
        return True

    # Numeric equivalence
    try:
        if float(e) == float(a):
            return True
    except ValueError:
        pass

    # Check if actual contains expected (for verbose answers)
    if e in a:
        return True

    return False


def evaluate_questions(
    context: str,
    bank: QuestionBank,
    *,
    condition: str,
    model: str = "claude-sonnet-4-20250514",
    encoding: str = "cl100k_base",
    batch_size: int = 10,
) -> EvaluationRun:
    """Evaluate questions against an LLM with the given context.

    Args:
        context: The full context string (raw or compressed).
        bank: Question bank with ground-truth answers.
        condition: Condition label ("raw" or "compressed").
        model: Anthropic model ID.
        encoding: Tiktoken encoding for token counting.
        batch_size: Number of questions per API call.

    Returns:
        EvaluationRun with per-question results.

    Raises:
        ImportError: If anthropic SDK is not installed.
    """
    try:
        import anthropic
    except ImportError as exc:
        raise ImportError(
            "QA evaluation requires the anthropic SDK. Install with: pip install decoct[llm]"
        ) from exc

    client = anthropic.Anthropic()
    context_tokens = count_tokens(context, encoding)

    run = EvaluationRun(
        condition=condition,
        model=model,
        context_tokens=context_tokens,
    )

    # Process in batches
    for i in range(0, len(bank.pairs), batch_size):
        batch = bank.pairs[i : i + batch_size]
        results = _evaluate_batch(client, model, context, batch, encoding)
        run.results.extend(results)

    return run


def _evaluate_batch(
    client: Any,
    model: str,
    context: str,
    questions: list[QAPair],
    encoding: str,
) -> list[AnswerResult]:
    """Evaluate a batch of questions in a single API call."""
    # Build the question list
    q_list = "\n".join(
        f"{i+1}. [ID: {q.id}] {q.question}"
        for i, q in enumerate(questions)
    )

    system_prompt = (
        "You are answering questions about network infrastructure configuration data. "
        "For each question, provide a concise, factual answer. "
        "Respond in JSON format: a list of objects with 'id' and 'answer' fields. "
        "Keep answers brief — just the key fact, not full sentences."
    )

    user_prompt = (
        f"Here is the configuration data:\n\n{context}\n\n"
        f"Answer these questions:\n{q_list}\n\n"
        f"Respond as JSON: [{{'id': '...', 'answer': '...'}}, ...]"
    )

    t0 = time.monotonic()
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    latency_ms = (time.monotonic() - t0) * 1000

    # Parse response
    response_text = response.content[0].text
    input_toks = response.usage.input_tokens
    output_toks = response.usage.output_tokens

    answers = _parse_batch_response(response_text)
    per_q_latency = latency_ms / len(questions) if questions else 0
    per_q_input = input_toks // len(questions) if questions else 0
    per_q_output = output_toks // len(questions) if questions else 0

    results: list[AnswerResult] = []
    for q in questions:
        actual = answers.get(q.id, "")
        results.append(AnswerResult(
            question_id=q.id,
            category=q.category,
            question=q.question,
            expected=q.ground_truth.answer,
            actual=actual,
            correct=_compare_answers(q.ground_truth.answer, actual),
            input_tokens=per_q_input,
            output_tokens=per_q_output,
            latency_ms=per_q_latency,
        ))

    return results


def _parse_batch_response(text: str) -> dict[str, str]:
    """Parse a batch JSON response into {id: answer} mapping."""
    # Try to extract JSON from the response
    text = text.strip()

    # Handle markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        json_lines = []
        in_block = False
        for line in lines:
            if line.startswith("```") and not in_block:
                in_block = True
                continue
            elif line.startswith("```") and in_block:
                break
            elif in_block:
                json_lines.append(line)
        text = "\n".join(json_lines)

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return {item["id"]: str(item.get("answer", "")) for item in data if "id" in item}
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    return {}


def format_evaluation_markdown(report: EvaluationReport) -> str:
    """Format an EvaluationReport as markdown."""
    lines: list[str] = []
    lines.append(f"# QA Comprehension Evaluation — {report.timestamp}")
    lines.append(f"Questions: {report.question_count}")
    lines.append("")

    if not report.runs:
        lines.append("No evaluation runs.")
        return "\n".join(lines)

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Condition | Model | Context Tokens | Accuracy | Answer Tokens |")
    lines.append("|-----------|-------|---------------:|---------:|--------------:|")
    for run in report.runs:
        lines.append(
            f"| {run.condition} | {run.model} | {run.context_tokens:,} "
            f"| {run.accuracy:.1%} | {run.total_answer_tokens:,} |"
        )
    lines.append("")

    # Per-category accuracy
    lines.append("## Accuracy by Category")
    lines.append("")
    cats = sorted({cat for run in report.runs for cat in run.accuracy_by_category})
    header = "| Category | " + " | ".join(run.condition for run in report.runs) + " |"
    sep = "|----------|" + "|".join("---------:" for _ in report.runs) + "|"
    lines.append(header)
    lines.append(sep)
    for cat in cats:
        vals = []
        for run in report.runs:
            acc = run.accuracy_by_category.get(cat, 0.0)
            vals.append(f"{acc:.1%}")
        lines.append(f"| {cat} | " + " | ".join(vals) + " |")
    lines.append("")

    # Delta (if both conditions present)
    if len(report.runs) == 2:
        r1, r2 = report.runs
        delta = r2.accuracy - r1.accuracy
        token_ratio = r2.context_tokens / r1.context_tokens if r1.context_tokens else 0
        lines.append("## Comparison")
        lines.append("")
        lines.append(f"- **Accuracy delta** ({r2.condition} vs {r1.condition}): {delta:+.1%}")
        lines.append(f"- **Context token ratio**: {token_ratio:.2f}x ({r2.context_tokens:,} / {r1.context_tokens:,})")
        lines.append("")

    return "\n".join(lines)


def format_evaluation_json(report: EvaluationReport) -> str:
    """Format an EvaluationReport as JSON."""
    data: dict[str, Any] = {
        "timestamp": report.timestamp,
        "question_count": report.question_count,
        "runs": [],
    }

    for run in report.runs:
        run_data: dict[str, Any] = {
            "condition": run.condition,
            "model": run.model,
            "context_tokens": run.context_tokens,
            "accuracy": round(run.accuracy, 4),
            "accuracy_by_category": {
                k: round(v, 4) for k, v in run.accuracy_by_category.items()
            },
            "total_answer_tokens": run.total_answer_tokens,
            "results": [
                {
                    "question_id": r.question_id,
                    "category": r.category.value,
                    "question": r.question,
                    "expected": r.expected,
                    "actual": r.actual,
                    "correct": r.correct,
                    "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens,
                    "latency_ms": round(r.latency_ms, 1),
                }
                for r in run.results
            ],
        }
        data["runs"].append(run_data)

    return json.dumps(data, indent=2)
