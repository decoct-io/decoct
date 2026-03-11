#!/usr/bin/env python3
"""Run all 1,800 eval questions through an LLM and auto-score results.

Batches questions (default 20 per call) with shared context to minimise
API calls. Supports both raw and compressed conditions.

Outputs a JSON results file per source per condition.

Usage:
    # Run all sources, both conditions
    python scripts/run_eval_harness.py

    # One source, one condition
    python scripts/run_eval_harness.py --source iosxr --condition raw

    # Compressed only, custom model
    python scripts/run_eval_harness.py --condition compressed --model claude-sonnet-4-6

    # Use Anthropic API directly (default)
    ANTHROPIC_API_KEY=sk-... python scripts/run_eval_harness.py

    # Use OpenRouter
    OPENROUTER_API_KEY=sk-... python scripts/run_eval_harness.py --provider openrouter
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from decoct.qa.eval_models import EvalQuestion, EvalQuestionBank, EvalQuestionClass, Difficulty
from decoct.qa.generate_eval import load_eval_bank
from decoct.qa.evaluate import build_raw_context, build_compressed_context
from decoct.tokens import count_tokens

ROOT = Path(__file__).resolve().parent.parent

SOURCES = {
    "iosxr": {
        "config_dir": ROOT / "tests/fixtures/iosxr/configs",
        "output_dir": ROOT / "output/iosxr",
        "bank": ROOT / "output/iosxr/eval/candidates.yaml",
    },
    "hybrid-infra": {
        "config_dir": ROOT / "tests/fixtures/hybrid-infra/configs",
        "output_dir": ROOT / "output/hybrid-infra",
        "bank": ROOT / "output/hybrid-infra/eval/candidates.yaml",
    },
    "entra-intune": {
        "config_dir": ROOT / "tests/fixtures/entra-intune/resources",
        "output_dir": ROOT / "output/entra-intune",
        "bank": ROOT / "output/entra-intune/eval/candidates.yaml",
    },
}

SYSTEM_PROMPT = (
    "You are answering questions about infrastructure configuration data. "
    "For each question, provide a concise, factual answer based only on the "
    "provided context. Respond in JSON format: a list of objects with 'id' "
    "and 'answer' fields. Keep answers specific and verifiable."
)

DATA_MANUAL = ROOT / "docs/entity-graph-data-manual.md"


@dataclass
class QuestionResult:
    id: str
    question_class: str
    difficulty: str
    question: str
    reference_answer: str
    model_answer: str
    auto_match: bool | None  # None = not auto-scorable


@dataclass
class RunResult:
    source: str
    condition: str
    model: str
    context_tokens: int
    questions_total: int
    questions_answered: int
    auto_score_total: int  # FR questions auto-scored
    auto_score_correct: int
    results: list[QuestionResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


def _fuzzy_match(reference: str, answer: str) -> bool:
    """Simple fuzzy match for factual retrieval auto-scoring."""
    ref = reference.lower().strip()
    ans = answer.lower().strip()
    # Exact containment either way
    if ref in ans or ans in ref:
        return True
    # Strip common prefixes/suffixes and check
    for ch in ".,;:!?()[]{}\"'":
        ref = ref.replace(ch, "")
        ans = ans.replace(ch, "")
    ref_words = set(ref.split())
    ans_words = set(ans.split())
    if not ref_words:
        return False
    overlap = len(ref_words & ans_words) / len(ref_words)
    return overlap >= 0.7


def _call_anthropic(system: str, user: str, *, model: str, max_tokens: int = 4096) -> str:
    """Call Anthropic API directly."""
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


def _call_openrouter(system: str, user: str, *, model: str, max_tokens: int = 4096) -> str:
    """Call OpenRouter API."""
    from openai import OpenAI
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


def _parse_batch_response(text: str) -> dict[str, str]:
    """Parse JSON batch response into {id: answer}."""
    text = text.strip()
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


def run_eval(
    source: str,
    condition: str,
    *,
    model: str,
    provider: str,
    batch_size: int,
) -> RunResult:
    """Run evaluation for one source + condition."""
    cfg = SOURCES[source]
    bank = load_eval_bank(cfg["bank"])

    # Build context
    if condition == "raw":
        context = build_raw_context(cfg["config_dir"])
    else:
        context = build_compressed_context(cfg["output_dir"], DATA_MANUAL)

    context_tokens = count_tokens(context)
    print(f"\n{'='*70}")
    print(f"  {source} / {condition} — {context_tokens:,} tokens, {len(bank.questions)} questions")
    print(f"{'='*70}")

    call_fn = _call_anthropic if provider == "anthropic" else _call_openrouter

    result = RunResult(
        source=source,
        condition=condition,
        model=model,
        context_tokens=context_tokens,
        questions_total=len(bank.questions),
        questions_answered=0,
        auto_score_total=0,
        auto_score_correct=0,
    )

    t0 = time.monotonic()
    answers: dict[str, str] = {}

    # Batch questions
    for i in range(0, len(bank.questions), batch_size):
        batch = bank.questions[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(bank.questions) + batch_size - 1) // batch_size

        q_list = "\n".join(
            f"{j + 1}. [ID: {q.id}] {q.question}"
            for j, q in enumerate(batch)
        )
        user_prompt = (
            f"Here is the configuration data:\n\n{context}\n\n"
            f"Answer these questions:\n{q_list}\n\n"
            f'Respond as JSON: [{{"id": "...", "answer": "..."}}, ...]'
        )

        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} Qs)...", end=" ", flush=True)

        try:
            resp = call_fn(SYSTEM_PROMPT, user_prompt, model=model)
            batch_answers = _parse_batch_response(resp)
            answers.update(batch_answers)
            print(f"got {len(batch_answers)} answers")
        except Exception as exc:
            err = f"Batch {batch_num} failed: {exc}"
            print(f"FAILED: {exc}")
            result.errors.append(err)

    result.questions_answered = len(answers)

    # Score
    for q in bank.questions:
        model_ans = answers.get(q.id, "")
        auto_match: bool | None = None

        if q.question_class == EvalQuestionClass.FACTUAL_RETRIEVAL:
            result.auto_score_total += 1
            if model_ans:
                auto_match = _fuzzy_match(q.reference_answer, model_ans)
                if auto_match:
                    result.auto_score_correct += 1

        result.results.append(QuestionResult(
            id=q.id,
            question_class=q.question_class.value,
            difficulty=q.difficulty.value,
            question=q.question,
            reference_answer=q.reference_answer,
            model_answer=model_ans,
            auto_match=auto_match,
        ))

    result.elapsed_seconds = time.monotonic() - t0

    # Summary
    fr_pct = (
        f"{result.auto_score_correct}/{result.auto_score_total}"
        f" ({result.auto_score_correct / result.auto_score_total:.0%})"
        if result.auto_score_total else "N/A"
    )
    print(f"\n  Answered: {result.questions_answered}/{result.questions_total}")
    print(f"  FR auto-score: {fr_pct}")
    print(f"  Errors: {len(result.errors)}")
    print(f"  Time: {result.elapsed_seconds:.1f}s")

    return result


def save_result(result: RunResult, out_dir: Path) -> Path:
    """Save result to JSON."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{result.source}_{result.condition}_results.json"
    data = {
        "source": result.source,
        "condition": result.condition,
        "model": result.model,
        "context_tokens": result.context_tokens,
        "questions_total": result.questions_total,
        "questions_answered": result.questions_answered,
        "auto_score_total": result.auto_score_total,
        "auto_score_correct": result.auto_score_correct,
        "auto_score_pct": (
            round(result.auto_score_correct / result.auto_score_total, 4)
            if result.auto_score_total else None
        ),
        "errors": result.errors,
        "elapsed_seconds": round(result.elapsed_seconds, 1),
        "results": [asdict(r) for r in result.results],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run eval harness for all 1,800 questions")
    parser.add_argument("--source", choices=list(SOURCES.keys()), help="Single source (default: all)")
    parser.add_argument("--condition", choices=["raw", "compressed"], help="Single condition (default: both)")
    parser.add_argument("--model", default="claude-sonnet-4-6", help="Model to use")
    parser.add_argument("--provider", choices=["anthropic", "openrouter"], default="anthropic")
    parser.add_argument("--batch-size", type=int, default=20, help="Questions per API call")
    parser.add_argument("--output-dir", type=str, default="output/eval-results", help="Output directory")
    args = parser.parse_args()

    sources = [args.source] if args.source else list(SOURCES.keys())
    conditions = [args.condition] if args.condition else ["raw", "compressed"]

    out_dir = ROOT / args.output_dir
    all_results: list[RunResult] = []

    for source in sources:
        for condition in conditions:
            result = run_eval(
                source, condition,
                model=args.model,
                provider=args.provider,
                batch_size=args.batch_size,
            )
            path = save_result(result, out_dir)
            print(f"  Saved → {path}")
            all_results.append(result)

    # Final summary
    print(f"\n{'='*70}")
    print("  SUMMARY")
    print(f"{'='*70}")
    print(f"  {'Source':<15} {'Condition':<12} {'Answered':<10} {'FR Score':<12} {'Time':<8}")
    print(f"  {'-'*15} {'-'*12} {'-'*10} {'-'*12} {'-'*8}")
    for r in all_results:
        fr = f"{r.auto_score_correct}/{r.auto_score_total}" if r.auto_score_total else "—"
        print(f"  {r.source:<15} {r.condition:<12} {r.questions_answered:<10} {fr:<12} {r.elapsed_seconds:.0f}s")


if __name__ == "__main__":
    main()
