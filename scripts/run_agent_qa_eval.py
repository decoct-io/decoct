#!/usr/bin/env python3
"""Run the two-agent QA harness against OpenRouter Gemini models.

Usage:
    export OPENROUTER_API_KEY=sk-or-...
    python scripts/run_agent_qa_eval.py

Runs 15 questions (1 per category per source) through:
  Router:   google/gemini-2.5-flash-lite  (file selection)
  Answerer: google/gemini-2.5-flash       (answer generation)
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from decoct.agent_qa.bridge import (
    _extract_tier_a_types_section,
    format_answerer_prompt,
    format_router_prompt,
    load_files,
    parse_router_response,
    validate_routed_files,
)
from eval_questions.entra_intune import (
    cross_reference as ei_cr,
    design_compliance as ei_dc,
    factual_retrieval as ei_fr,
    negative_absence as ei_na,
    operational_inference as ei_oi,
)
from eval_questions.hybrid_infra import (
    cross_reference as hi_cr,
    design_compliance as hi_dc,
    factual_retrieval as hi_fr,
    negative_absence as hi_na,
    operational_inference as hi_oi,
)
from eval_questions.iosxr import (
    cross_reference as ix_cr,
    design_compliance as ix_dc,
    factual_retrieval as ix_fr,
    negative_absence as ix_na,
    operational_inference as ix_oi,
)

# ── Config ──────────────────────────────────────────────────────────────────

ROUTER_MODEL = "google/gemini-2.5-flash"
ANSWERER_MODEL = "google/gemini-2.5-flash"
OPENROUTER_BASE = "https://openrouter.ai/api/v1/chat/completions"

OUTPUT_DIRS: dict[str, Path] = {
    "hybrid-infra": Path("output/hybrid-infra"),
    "entra-intune": Path("output/entra-intune"),
    "iosxr": Path("output/iosxr"),
}

TIER_A_FILES: dict[str, str] = {
    "hybrid-infra": "tier_a.yaml",
    "entra-intune": "tier_a.yaml",
    "iosxr": "tier_a.yaml",
}


@dataclass
class TestQuestion:
    source: str
    category: str
    qid: str
    question: str
    reference_answer: str


@dataclass
class TestResult:
    source: str
    category: str
    qid: str
    question: str
    reference_answer: str
    router_model: str
    answerer_model: str
    routed_files: list[str]
    router_reasoning: str
    answer: str
    router_time_s: float
    answerer_time_s: float
    total_time_s: float
    router_input_tokens: int | None = None
    router_output_tokens: int | None = None
    answerer_input_tokens: int | None = None
    answerer_output_tokens: int | None = None
    missing_files: list[str] | None = None
    error: str | None = None


def select_questions(seed: int = 42) -> list[TestQuestion]:
    """Pick 1 medium question per category per source (15 total)."""
    rng = random.Random(seed)

    sources = {
        "hybrid-infra": {
            "FR": hi_fr(), "CR": hi_cr(), "OI": hi_oi(), "DC": hi_dc(), "NA": hi_na(),
        },
        "entra-intune": {
            "FR": ei_fr(), "CR": ei_cr(), "OI": ei_oi(), "DC": ei_dc(), "NA": ei_na(),
        },
        "iosxr": {
            "FR": ix_fr(), "CR": ix_cr(), "OI": ix_oi(), "DC": ix_dc(), "NA": ix_na(),
        },
    }

    questions: list[TestQuestion] = []
    for source, cats in sources.items():
        for cat_name, qs in cats.items():
            medium = [q for q in qs if q.difficulty.value == "medium"]
            pick = rng.choice(medium)
            questions.append(TestQuestion(
                source=source,
                category=cat_name,
                qid=pick.id,
                question=pick.question,
                reference_answer=pick.reference_answer,
            ))
    return questions


def call_openrouter(model: str, prompt: str, api_key: str) -> tuple[str, dict]:
    """Call OpenRouter chat completions API. Returns (content, usage_dict)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/decoct-io/decoct",
        "X-Title": "decoct-agent-qa-eval",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
    }

    with httpx.Client(timeout=120.0) as client:
        resp = client.post(OPENROUTER_BASE, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return content, usage


def run_question(q: TestQuestion, api_key: str) -> TestResult:
    """Run the full Router → Answerer pipeline for one question."""
    output_dir = OUTPUT_DIRS[q.source]
    tier_a_path = output_dir / TIER_A_FILES[q.source]
    tier_a_content = tier_a_path.read_text(encoding="utf-8")

    # ── Router ──
    router_prompt = format_router_prompt(tier_a_content, q.question)
    t0 = time.monotonic()
    router_raw, router_usage = call_openrouter(ROUTER_MODEL, router_prompt, api_key)
    router_time = time.monotonic() - t0

    parsed = parse_router_response(router_raw)
    files = parsed.get("files", [])
    reasoning = parsed.get("reasoning", "")

    # Ensure files is a list of strings
    if not isinstance(files, list):
        files = []
    files = [str(f) for f in files]

    # ── Validate routed files ──
    missing_files: list[str] = []
    if files:
        files, missing_files = validate_routed_files(output_dir, files)
        if missing_files:
            print(f"        WARNING: Router hallucinated files: {missing_files}")

    # ── Load files ──
    tier_a_excerpt = _extract_tier_a_types_section(tier_a_content)
    if files:
        loaded = load_files(output_dir, files)
    else:
        # Tier A only — pass it as context
        loaded = f"--- tier_a.yaml ---\n{tier_a_content}\n"
        tier_a_excerpt = ""  # Already included in full

    # ── Answerer ──
    answerer_prompt = format_answerer_prompt(
        q.question, loaded, category=q.category, tier_a_excerpt=tier_a_excerpt,
    )
    t1 = time.monotonic()
    answer_raw, answerer_usage = call_openrouter(ANSWERER_MODEL, answerer_prompt, api_key)
    answerer_time = time.monotonic() - t1

    total_time = router_time + answerer_time

    return TestResult(
        source=q.source,
        category=q.category,
        qid=q.qid,
        question=q.question,
        reference_answer=q.reference_answer,
        router_model=ROUTER_MODEL,
        answerer_model=ANSWERER_MODEL,
        routed_files=files,
        router_reasoning=str(reasoning),
        answer=answer_raw,
        router_time_s=round(router_time, 2),
        answerer_time_s=round(answerer_time, 2),
        total_time_s=round(total_time, 2),
        router_input_tokens=router_usage.get("prompt_tokens"),
        router_output_tokens=router_usage.get("completion_tokens"),
        answerer_input_tokens=answerer_usage.get("prompt_tokens"),
        answerer_output_tokens=answerer_usage.get("completion_tokens"),
        missing_files=missing_files if missing_files else None,
    )


def main() -> None:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("ERROR: Set OPENROUTER_API_KEY environment variable")
        sys.exit(1)

    questions = select_questions()
    print(f"Running {len(questions)} questions through two-agent QA harness")
    print(f"  Router:   {ROUTER_MODEL}")
    print(f"  Answerer: {ANSWERER_MODEL}")
    print()

    results: list[TestResult] = []
    for i, q in enumerate(questions, 1):
        print(f"[{i:2d}/15] {q.source} | {q.category} | {q.qid}: {q.question[:70]}...")
        try:
            result = run_question(q, api_key)
            results.append(result)
            files_str = ", ".join(result.routed_files) if result.routed_files else "(tier_a only)"
            print(f"        Router: {files_str}")
            print(f"        Time: router={result.router_time_s}s answerer={result.answerer_time_s}s")
            tok_str = ""
            if result.router_input_tokens is not None:
                tok_str += f" router_in={result.router_input_tokens} router_out={result.router_output_tokens}"
            if result.answerer_input_tokens is not None:
                tok_str += f" ans_in={result.answerer_input_tokens} ans_out={result.answerer_output_tokens}"
            if tok_str:
                print(f"        Tokens:{tok_str}")
            print()
        except Exception as e:
            print(f"        ERROR: {e}")
            results.append(TestResult(
                source=q.source, category=q.category, qid=q.qid,
                question=q.question, reference_answer=q.reference_answer,
                router_model=ROUTER_MODEL, answerer_model=ANSWERER_MODEL,
                routed_files=[], router_reasoning="", answer="",
                router_time_s=0, answerer_time_s=0, total_time_s=0,
                error=str(e),
            ))
            print()

    # ── Summary ──
    print("=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    for r in results:
        print(f"\n{'─' * 80}")
        print(f"{r.source} | {r.category} | {r.qid}")
        print(f"Q: {r.question}")
        print(f"Reference: {r.reference_answer[:200]}")
        print(f"Files: {', '.join(r.routed_files) if r.routed_files else '(tier_a only)'}")
        if r.missing_files:
            print(f"Hallucinated files: {', '.join(r.missing_files)}")
        print(f"Router reasoning: {r.router_reasoning[:200]}")
        print(f"Answer: {r.answer[:500]}")
        if r.error:
            print(f"ERROR: {r.error}")

    # ── Timing & cost summary ──
    print(f"\n{'=' * 80}")
    total_router = sum(r.router_time_s for r in results)
    total_answerer = sum(r.answerer_time_s for r in results)
    total_router_in = sum(r.router_input_tokens or 0 for r in results)
    total_router_out = sum(r.router_output_tokens or 0 for r in results)
    total_ans_in = sum(r.answerer_input_tokens or 0 for r in results)
    total_ans_out = sum(r.answerer_output_tokens or 0 for r in results)

    # Pricing: flash-lite $0.10/$0.40 per M, flash $0.30/$2.50 per M
    router_cost = (total_router_in * 0.10 + total_router_out * 0.40) / 1_000_000
    answerer_cost = (total_ans_in * 0.30 + total_ans_out * 2.50) / 1_000_000
    total_cost = router_cost + answerer_cost

    print(f"Timing:  router={total_router:.1f}s  answerer={total_answerer:.1f}s  total={total_router + total_answerer:.1f}s")
    print(f"Tokens:  router_in={total_router_in:,}  router_out={total_router_out:,}  ans_in={total_ans_in:,}  ans_out={total_ans_out:,}")
    print(f"Cost:    router=${router_cost:.4f}  answerer=${answerer_cost:.4f}  total=${total_cost:.4f}")
    errors = sum(1 for r in results if r.error)
    hallucinations = sum(1 for r in results if r.missing_files)
    print(f"Errors:  {errors}/15")
    print(f"Hallucinated files: {hallucinations}/15 questions had invalid file paths")

    # ── Save JSON ──
    out_path = Path("internals/agent_qa_eval_results_v2.json")
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
