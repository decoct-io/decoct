"""Weighted evaluation harness for LLM-generated evaluation questions.

Two-phase evaluation:
1. Answer phase — batch questions to an LLM with raw/compressed context
2. Judge phase — score answers using class-specific rubrics

Factual questions are auto-scored via fuzzy match.
All other classes use LLM-as-judge with weighted rubrics.

LLM provider: OpenAI SDK with configurable ``--base-url``.

Requires the [llm] extra: pip install decoct[llm]
"""

from __future__ import annotations

import json
import os
import time
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from decoct.llm_utils import extract_yaml_block
from decoct.qa.eval_models import (
    MAX_SCORE,
    EvalAnswerResult,
    EvalEvaluationReport,
    EvalEvaluationRun,
    EvalQuestion,
    EvalQuestionBank,
    EvalQuestionClass,
)
from decoct.qa.evaluate import (
    _compare_answers,
    build_compressed_context,
    build_raw_context,
)
from decoct.tokens import count_tokens

_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_API_KEY_ENV = "OPENROUTER_API_KEY"

# --- Answer phase prompts ---

_ANSWER_SYSTEM_PROMPT = """\
You are answering questions about infrastructure configuration data.
For each question, provide a concise, factual answer based only on the provided context.
Respond in JSON format: a list of objects with 'id' and 'answer' fields.
Keep answers detailed enough to demonstrate understanding but concise."""

# --- Judge rubrics per class ---

_JUDGE_RUBRICS: dict[EvalQuestionClass, str] = {
    EvalQuestionClass.CROSS_REFERENCE: """\
You are judging answers to CROSS_REFERENCE questions about infrastructure configs.
These questions require correlating facts across 2+ config files.

Scoring rubric (0-2):
- Score 2: All referenced facts correct AND relationship accurately stated
- Score 1: Correct facts but incomplete or imprecise relationship
- Score 0: Incorrect facts or wrong relationship

For each question, output a score and brief reasoning.""",

    EvalQuestionClass.OPERATIONAL_INFERENCE: """\
You are judging answers to OPERATIONAL_INFERENCE questions about infrastructure configs.
These questions require reasoning about operational impact and causal chains.

Scoring rubric (0-3):
- Score 3: Correct components identified, accurate causal reasoning, actionable conclusion
- Score 2: Most components correct, reasoning mostly sound but gaps
- Score 1: Some correct elements but material gaps in reasoning
- Score 0: Materially wrong or unable to reason about scenario

For each question, output a score and brief reasoning.""",

    EvalQuestionClass.DESIGN_COMPLIANCE: """\
You are judging answers to DESIGN_COMPLIANCE questions about infrastructure configs.
These questions ask whether configs follow a standard or best practice.

Scoring rubric (0-2):
- Score 2: Correct compliance assessment with specific evidence cited
- Score 1: Correct conclusion but vague or missing evidence
- Score 0: Wrong conclusion

For each question, output a score and brief reasoning.""",

    EvalQuestionClass.NEGATIVE_ABSENCE: """\
You are judging answers to NEGATIVE_ABSENCE questions about infrastructure configs.
These questions ask about things that are NOT present or configured.

Scoring rubric (0-2):
- Score 2: Correctly identifies presence/absence with evidence
- Score 1: Correct conclusion but incomplete enumeration
- Score 0: Wrong conclusion or fails to identify clear absence

For each question, output a score and brief reasoning.""",
}

_JUDGE_USER_TEMPLATE = """\
## Questions to Judge

{items_yaml}

For each item, return YAML:
```yaml
- id: "..."
  score: <integer>
  reasoning: "..."
```
"""


def evaluate_eval_questions(
    bank: EvalQuestionBank,
    config_dir: Path | None,
    output_dir: Path | None,
    *,
    condition: str,
    model_answer: str = "google/gemini-2.5-flash",
    model_judge: str = "google/gemini-2.5-flash",
    base_url: str = _DEFAULT_BASE_URL,
    api_key_env: str = _DEFAULT_API_KEY_ENV,
    manual_path: Path | None = None,
    encoding: str = "cl100k_base",
    batch_size: int = 10,
    on_progress: Callable[[str], None] | None = None,
) -> EvalEvaluationRun:
    """Evaluate a question bank with weighted scoring.

    Phase 1: Answer questions in batches.
    Phase 2: Judge non-factual answers with class-specific rubrics.

    Args:
        bank: Validated question bank.
        config_dir: Raw config directory (for "raw" condition).
        output_dir: Entity-graph output directory (for "compressed" condition).
        condition: "raw" or "compressed".
        model_answer: Model for answering questions.
        model_judge: Model for judging answers.
        base_url: OpenAI-compatible API base URL.
        api_key_env: Environment variable holding the API key.
        manual_path: Optional reader manual for compressed context.
        encoding: Tiktoken encoding for token counting.
        batch_size: Questions per answer API call.
        on_progress: Optional progress callback.

    Returns:
        EvalEvaluationRun with per-question scored results.
    """
    def _progress(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    # Build context
    if condition == "raw":
        if not config_dir:
            msg = "config_dir required for raw condition"
            raise ValueError(msg)
        context = build_raw_context(config_dir)
    else:
        if not output_dir:
            msg = "output_dir required for compressed condition"
            raise ValueError(msg)
        context = build_compressed_context(output_dir, manual_path)

    context_tokens = count_tokens(context, encoding)
    _progress(f"Context ({condition}): {context_tokens:,} tokens")

    # Phase 1: Answer
    _progress(f"Phase 1: Answering {len(bank.questions)} questions in batches of {batch_size}...")
    answers: dict[str, str] = {}
    total_input_tokens = 0
    total_output_tokens = 0
    total_latency_ms = 0.0

    for i in range(0, len(bank.questions), batch_size):
        batch = bank.questions[i : i + batch_size]
        batch_num = i // batch_size + 1
        _progress(f"  Batch {batch_num}: {len(batch)} questions...")

        try:
            batch_answers, in_toks, out_toks, lat_ms = _answer_batch(
                context, batch,
                model=model_answer, base_url=base_url, api_key_env=api_key_env,
            )
            answers.update(batch_answers)
            total_input_tokens += in_toks
            total_output_tokens += out_toks
            total_latency_ms += lat_ms
        except Exception as exc:  # noqa: BLE001
            warnings.warn(f"Answer batch {batch_num} failed: {exc}", stacklevel=2)
            _progress(f"  WARN: Batch {batch_num} failed: {exc}")

    _progress(f"  Got {len(answers)} answers")

    # Phase 2: Judge
    _progress("Phase 2: Scoring answers...")
    results: list[EvalAnswerResult] = []

    # Auto-score factual questions
    factual_qs = [q for q in bank.questions if q.question_class == EvalQuestionClass.FACTUAL_RETRIEVAL]
    for q in factual_qs:
        model_ans = answers.get(q.id, "")
        correct = _compare_answers(q.reference_answer, model_ans)
        results.append(EvalAnswerResult(
            question_id=q.id,
            question_class=q.question_class,
            question=q.question,
            reference_answer=q.reference_answer,
            model_answer=model_ans,
            score=1 if correct else 0,
            max_score=MAX_SCORE[q.question_class],
            judge_reasoning="",
        ))
    _progress(f"  Factual: {sum(1 for r in results if r.score > 0)}/{len(factual_qs)} correct")

    # LLM-judge non-factual classes
    for qclass in EvalQuestionClass:
        if qclass == EvalQuestionClass.FACTUAL_RETRIEVAL:
            continue

        class_qs = [q for q in bank.questions if q.question_class == qclass]
        if not class_qs:
            continue

        _progress(f"  Judging {len(class_qs)} {qclass.value} questions...")

        items = [
            {
                "id": q.id,
                "question": q.question,
                "reference_answer": q.reference_answer,
                "model_answer": answers.get(q.id, "(no answer)"),
            }
            for q in class_qs
        ]

        try:
            scores = _judge_class(
                qclass, items,
                model=model_judge, base_url=base_url, api_key_env=api_key_env,
            )
            score_map = {s[0]: (s[1], s[2]) for s in scores}
        except Exception as exc:  # noqa: BLE001
            warnings.warn(f"Judge failed for {qclass.value}: {exc}", stacklevel=2)
            _progress(f"  WARN: Judge failed for {qclass.value}: {exc}")
            score_map = {}

        max_sc = MAX_SCORE[qclass]
        for q in class_qs:
            model_ans = answers.get(q.id, "")
            sc, reasoning = score_map.get(q.id, (0, "Judge call failed"))
            # Clamp score to valid range
            sc = max(0, min(sc, max_sc))
            results.append(EvalAnswerResult(
                question_id=q.id,
                question_class=q.question_class,
                question=q.question,
                reference_answer=q.reference_answer,
                model_answer=model_ans,
                score=sc,
                max_score=max_sc,
                judge_reasoning=reasoning,
            ))

    run = EvalEvaluationRun(
        condition=condition,
        model_answer=model_answer,
        model_judge=model_judge,
        context_tokens=context_tokens,
        results=results,
    )
    _progress(f"  Total: {run.total_score}/{run.max_total_score} ({run.total_score / run.max_total_score:.1%})")
    return run


def _answer_batch(
    context: str,
    questions: list[EvalQuestion],
    *,
    model: str,
    base_url: str,
    api_key_env: str,
) -> tuple[dict[str, str], int, int, float]:
    """Answer a batch of questions. Returns (answers, input_tokens, output_tokens, latency_ms)."""
    q_list = "\n".join(
        f"{i + 1}. [ID: {q.id}] {q.question}"
        for i, q in enumerate(questions)
    )

    user_prompt = (
        f"Here is the configuration data:\n\n{context}\n\n"
        f"Answer these questions:\n{q_list}\n\n"
        f"Respond as JSON: [{{\"id\": \"...\", \"answer\": \"...\"}}, ...]"
    )

    t0 = time.monotonic()
    response_text = _call_llm(
        _ANSWER_SYSTEM_PROMPT, user_prompt,
        model=model, base_url=base_url, api_key_env=api_key_env, max_tokens=4096,
    )
    latency_ms = (time.monotonic() - t0) * 1000

    answers = _parse_batch_response(response_text)

    # Approximate token counts (real counts from API would be better but OpenAI compat varies)
    input_tokens = 0
    output_tokens = 0

    return answers, input_tokens, output_tokens, latency_ms


def _parse_batch_response(text: str) -> dict[str, str]:
    """Parse a batch JSON response into {id: answer} mapping."""
    text = text.strip()

    # Handle markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        json_lines: list[str] = []
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
            return {str(item["id"]): str(item.get("answer", "")) for item in data if "id" in item}
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    return {}


def _judge_class(
    qclass: EvalQuestionClass,
    items: list[dict[str, str]],
    *,
    model: str,
    base_url: str,
    api_key_env: str,
) -> list[tuple[str, int, str]]:
    """Judge answers for a single question class. Returns [(id, score, reasoning)]."""
    rubric = _JUDGE_RUBRICS[qclass]

    yaml_obj = YAML(typ="rt")
    yaml_obj.default_flow_style = False
    from io import StringIO
    stream = StringIO()
    yaml_obj.dump(items, stream)
    items_yaml = stream.getvalue()

    user_prompt = _JUDGE_USER_TEMPLATE.format(items_yaml=items_yaml)

    response_text = _call_llm(
        rubric, user_prompt,
        model=model, base_url=base_url, api_key_env=api_key_env, max_tokens=8192,
    )

    yaml_str = extract_yaml_block(response_text)
    yaml_safe = YAML(typ="safe")
    data = yaml_safe.load(yaml_str)

    if not isinstance(data, list):
        return []

    results: list[tuple[str, int, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            qid = str(item["id"])
            score = int(item.get("score", 0))
            reasoning = str(item.get("reasoning", ""))
            results.append((qid, score, reasoning))
        except (KeyError, ValueError, TypeError):
            continue

    return results


def _call_llm(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str,
    base_url: str,
    api_key_env: str,
    max_tokens: int = 8192,
) -> str:
    """Call LLM via OpenAI-compatible API. Lazy-imports openai."""
    try:
        from openai import OpenAI
    except ImportError:
        msg = "The openai SDK is required for eval evaluation. Install with: pip install decoct[llm]"
        raise ImportError(msg)  # noqa: B904

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.environ.get(api_key_env)
    if not api_key:
        msg = f"Environment variable {api_key_env} is not set"
        raise ValueError(msg)

    client = OpenAI(base_url=base_url, api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


def format_eval_report_markdown(report: EvalEvaluationReport) -> str:
    """Format an EvalEvaluationReport as markdown."""
    lines: list[str] = []
    lines.append(f"# Weighted Evaluation Report — {report.source}")
    lines.append(f"Timestamp: {report.timestamp}")
    lines.append(f"Questions: {report.question_count}")
    lines.append("")

    if not report.runs:
        lines.append("No evaluation runs.")
        return "\n".join(lines)

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Condition | Answer Model | Judge Model | Context Tokens | Score | Max | Pct |")
    lines.append("|-----------|-------------|-------------|---------------:|------:|----:|----:|")
    for run in report.runs:
        pct = run.total_score / run.max_total_score if run.max_total_score else 0
        lines.append(
            f"| {run.condition} | {run.model_answer} | {run.model_judge} "
            f"| {run.context_tokens:,} | {run.total_score} | {run.max_total_score} | {pct:.1%} |"
        )
    lines.append("")

    # Per-class breakdown
    lines.append("## Score by Class")
    lines.append("")
    header_parts = ["| Class"]
    sep_parts = ["|------"]
    for run in report.runs:
        header_parts.append(f" | {run.condition} Score | {run.condition} Pct")
        sep_parts.append(" | -----:| ---:")
    lines.append("".join(header_parts) + " |")
    lines.append("".join(sep_parts) + " |")

    all_classes = sorted({cls for run in report.runs for cls in run.score_by_class})
    for cls in all_classes:
        row = f"| {cls}"
        for run in report.runs:
            scored, mx = run.score_by_class.get(cls, (0, 0))
            pct = scored / mx if mx > 0 else 0
            row += f" | {scored}/{mx} | {pct:.1%}"
        lines.append(row + " |")
    lines.append("")

    # Delta (if both conditions)
    if len(report.runs) == 2:
        r1, r2 = report.runs
        p1 = r1.total_score / r1.max_total_score if r1.max_total_score else 0
        p2 = r2.total_score / r2.max_total_score if r2.max_total_score else 0
        delta = p2 - p1
        token_ratio = r2.context_tokens / r1.context_tokens if r1.context_tokens else 0
        lines.append("## Comparison")
        lines.append("")
        lines.append(f"- **Score delta** ({r2.condition} vs {r1.condition}): {delta:+.1%}")
        lines.append(f"- **Context token ratio**: {token_ratio:.2f}x ({r2.context_tokens:,} / {r1.context_tokens:,})")
        lines.append("")

    return "\n".join(lines)


def format_eval_report_json(report: EvalEvaluationReport) -> str:
    """Format an EvalEvaluationReport as JSON."""
    data: dict[str, Any] = {
        "timestamp": report.timestamp,
        "source": report.source,
        "question_count": report.question_count,
        "runs": [],
    }

    for run in report.runs:
        run_data: dict[str, Any] = {
            "condition": run.condition,
            "model_answer": run.model_answer,
            "model_judge": run.model_judge,
            "context_tokens": run.context_tokens,
            "total_score": run.total_score,
            "max_total_score": run.max_total_score,
            "score_by_class": {
                cls: {"scored": s, "max": m, "pct": round(s / m, 4) if m else 0}
                for cls, (s, m) in run.score_by_class.items()
            },
            "results": [
                {
                    "question_id": r.question_id,
                    "question_class": r.question_class.value,
                    "question": r.question,
                    "reference_answer": r.reference_answer,
                    "model_answer": r.model_answer,
                    "score": r.score,
                    "max_score": r.max_score,
                    "judge_reasoning": r.judge_reasoning,
                    "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens,
                    "latency_ms": round(r.latency_ms, 1),
                }
                for r in run.results
            ],
        }
        data["runs"].append(run_data)

    return json.dumps(data, indent=2)
