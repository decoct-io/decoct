#!/usr/bin/env python3
"""End-to-end evaluation pipeline: router + answerer across all corpora.

Usage:
    export OPENROUTER_API_KEY=sk-or-...
    python scripts/run_evaluation.py --per-category 40 --workers 6

Each question gets its own router call (file selection) and answerer call
(answer generation). Router sees Tier A + all Tier B + projection file listing
per corpus, with cache_control breakpoints for Gemini implicit caching.

Only 3 distinct router contexts (one per corpus), so after the first call per
corpus all subsequent router calls hit the cache (0.25x input cost).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from decoct.agent_qa.bridge import (
    _extract_tier_a_types_section,
    format_answerer_prompt,
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

# ── Config ───────────────────────────────────────────────────────────────────

OUTPUT_DIRS: dict[str, Path] = {
    "hybrid-infra": Path("output/hybrid-infra"),
    "entra-intune": Path("output/entra-intune"),
    "iosxr": Path("output/iosxr"),
}

ROUTER_SYSTEM_PROMPT = """\
You are a routing agent for decoct compressed infrastructure output.

## Data Model

decoct compresses fleets of infrastructure configs into three tiers:
- **Tier A** (`tier_a.yaml`): Fleet overview — lists every entity type with counts, \
class/subclass counts, summaries, key differentiators, and file references.
- **Tier B** (`*_classes.yaml`): Class definitions — shared attribute sets, \
composite templates, subclass own_attrs. You can see ALL Tier B content below.
- **Tier C** (`*_instances.yaml`): Per-entity differences — class/subclass assignments, \
overrides, instance_attrs, instance_data (phone book).
- **Projections** (`projections/<type_id>/<subject>.yaml`): Subject-specific slices of \
Tier B+C focused on a single topic (e.g. authentication, networking).

## CRITICAL: The Answerer does NOT have Tier B

You have Tier B to help you make routing decisions. But the Answerer agent only \
receives the files you select (plus the matching Tier B is auto-included when you \
select a Tier C file). This means:

- If you return an EMPTY file list, the Answerer only sees the Tier A summary — \
it CANNOT see any config values, class definitions, or per-entity data.
- Return empty ONLY for pure fleet-level counting questions ("how many types?", \
"what types exist?").
- For ALL other questions — including operational reasoning, compliance checks, \
cross-references, and factual lookups — you MUST select files.
- If the question asks about specific settings or their impact, select at minimum \
the relevant type's Tier C file (the matching Tier B will be auto-included).

## File selection strategy

- **Factual retrieval / entity-specific** → select the relevant type's Tier C \
(`{type}_instances.yaml`). Tier B is auto-paired.
- **Subject-specific** (e.g. "authentication settings", "BGP neighbors") → prefer \
a matching projection if one exists. Fall back to Tier C.
- **Cross-entity comparison** → select Tier C for relevant types, or projections.
- **Operational / compliance / design questions** → these ALWAYS need config data. \
Select the Tier C file for the relevant type, or a projection covering the topic. \
Never return empty for these.

## Numbered subtypes — IMPORTANT

Files like `{type}_N_instances.yaml` (e.g. `entra-conditional-access_3_instances.yaml`) \
are subtype shards containing a SMALL SUBSET of entities. The MAIN file \
`{type}_instances.yaml` (referenced by `tier_c_ref` in Tier A) contains all entities \
for that type's primary class hierarchy.

**Rule: ALWAYS prefer the main `{type}_instances.yaml` file.** Only add a numbered \
subtype file if the question specifically asks about entities you know are in that \
subtype. When in doubt, use the main file — it has the majority of entities.

## Projection validation

ONLY select projections from the EXACT file listing below. Do NOT invent filenames.

## Rules
- Return at most 10 files. Only request Tier C files or projections (not Tier B).
- Use exact relative paths from the listing below.
- When in doubt, INCLUDE files — it is much better to send too much than too little.

## Response Format

Return ONLY a JSON object (no markdown fences, no extra text):
{{"files": ["path/to/file1.yaml", ...], "reasoning": "Brief explanation of selection"}}
"""


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
    router_cached_tokens: int | None = None
    error: str | None = None


@dataclass
class CorpusContext:
    """Pre-loaded corpus data for router context (cacheable)."""
    tier_a_content: str
    tier_a_excerpt: str
    tier_b_sections: str
    projection_listing: str
    output_dir: Path


def build_corpus_context(corpus: str) -> CorpusContext:
    """Load Tier A + all Tier B + projection listing for a corpus."""
    output_dir = OUTPUT_DIRS[corpus]

    # Tier A
    tier_a_content = (output_dir / "tier_a.yaml").read_text(encoding="utf-8")
    tier_a_excerpt = _extract_tier_a_types_section(tier_a_content)

    # All Tier B files
    tier_b_parts: list[str] = []
    for f in sorted(output_dir.glob("*_classes.yaml")):
        content = f.read_text(encoding="utf-8")
        tier_b_parts.append(f"### {f.name}\n```yaml\n{content}\n```")
    tier_b_sections = "\n\n".join(tier_b_parts)

    # Projection file listing
    proj_dir = output_dir / "projections"
    proj_files: list[str] = []
    if proj_dir.exists():
        for f in sorted(proj_dir.rglob("*.yaml")):
            rel = f.relative_to(output_dir)
            proj_files.append(str(rel))
    projection_listing = "\n".join(f"- {p}" for p in proj_files) if proj_files else "(none)"

    # Also list Tier C files
    tier_c_files = sorted(output_dir.glob("*_instances.yaml"))
    tier_c_listing = "\n".join(f"- {f.name}" for f in tier_c_files)

    full_listing = f"**Tier C files:**\n{tier_c_listing}\n\n**Projection files:**\n{projection_listing}"

    return CorpusContext(
        tier_a_content=tier_a_content,
        tier_a_excerpt=tier_a_excerpt,
        tier_b_sections=tier_b_sections,
        projection_listing=full_listing,
        output_dir=output_dir,
    )


def select_questions(per_category: int = 1, seed: int = 42) -> list[TestQuestion]:
    """Pick questions per category per source.

    When per_category=1, picks 1 medium question (backward compat).
    When per_category>1, samples across all difficulties.
    """
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
            if per_category == 1:
                pool = [q for q in qs if q.difficulty.value == "medium"]
                picks = [rng.choice(pool)]
            else:
                pool = list(qs)
                rng.shuffle(pool)
                picks = pool[:per_category]
            for pick in picks:
                questions.append(TestQuestion(
                    source=source,
                    category=cat_name,
                    qid=pick.id,
                    question=pick.question,
                    reference_answer=pick.reference_answer,
                ))
    return questions


def call_openrouter(
    model: str,
    messages: list[dict],
    api_key: str,
    base_url: str = "https://openrouter.ai/api/v1/chat/completions",
) -> tuple[str, dict]:
    """Call OpenRouter chat completions API. Returns (content, usage_dict)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/decoct-io/decoct",
        "X-Title": "decoct-eval",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.0,
    }

    with httpx.Client(timeout=180.0) as client:
        resp = client.post(base_url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return content, usage


def build_router_messages(ctx: CorpusContext, question: str) -> list[dict]:
    """Build router messages with cache_control breakpoint on corpus context.

    Structure:
    - system: routing instructions (small, static)
    - user part 1: Tier A + Tier B + file listing (large, cached per corpus)
    - user part 2: the question (small, varies)
    """
    corpus_context = (
        f"## Tier A Content\n\n```yaml\n{ctx.tier_a_content}\n```\n\n"
        f"## Tier B — Class Definitions (all types)\n\n{ctx.tier_b_sections}\n\n"
        f"## Available Files\n\n{ctx.projection_listing}"
    )

    return [
        {
            "role": "system",
            "content": ROUTER_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": corpus_context,
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": f"## User Question\n\n{question}",
                },
            ],
        },
    ]


def run_question(
    q: TestQuestion,
    api_key: str,
    model: str,
    base_url: str,
    ctx: CorpusContext,
) -> TestResult:
    """Run the full Router -> Answerer pipeline for one question."""
    chat_url = base_url.rstrip("/") + "/chat/completions"

    # ── Router (with caching) ──
    router_messages = build_router_messages(ctx, q.question)
    t0 = time.monotonic()
    router_raw, router_usage = call_openrouter(model, router_messages, api_key, chat_url)
    router_time = time.monotonic() - t0

    parsed = parse_router_response(router_raw)
    files = parsed.get("files", [])
    reasoning = parsed.get("reasoning", "")

    if not isinstance(files, list):
        files = []
    files = [str(f) for f in files]

    # ── Validate routed files ──
    missing_files: list[str] = []
    if files:
        files, missing_files = validate_routed_files(ctx.output_dir, files)

    # ── Auto-pair Tier B with Tier C ──
    # Router only selects Tier C / projections (it already has Tier B).
    # The answerer needs Tier B to interpret Tier C, so auto-include it.
    answerer_files = list(files)
    for f in files:
        if f.endswith("_instances.yaml"):
            tier_b_name = f.replace("_instances.yaml", "_classes.yaml")
            if tier_b_name not in answerer_files and (ctx.output_dir / tier_b_name).is_file():
                answerer_files.insert(0, tier_b_name)

    # ── Load files ──
    if answerer_files:
        loaded = load_files(ctx.output_dir, answerer_files)
    else:
        loaded = f"--- tier_a.yaml ---\n{ctx.tier_a_content}\n"

    # ── Answerer ──
    tier_a_excerpt = ctx.tier_a_excerpt if files else ""
    answerer_prompt = format_answerer_prompt(
        q.question, loaded, category=q.category, tier_a_excerpt=tier_a_excerpt,
    )
    answerer_messages = [{"role": "user", "content": answerer_prompt}]
    t1 = time.monotonic()
    answer_raw, answerer_usage = call_openrouter(model, answerer_messages, api_key, chat_url)
    answerer_time = time.monotonic() - t1

    total_time = router_time + answerer_time

    return TestResult(
        source=q.source,
        category=q.category,
        qid=q.qid,
        question=q.question,
        reference_answer=q.reference_answer,
        router_model=model,
        answerer_model=model,
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
        router_cached_tokens=(router_usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run evaluation pipeline (router + answerer)")
    parser.add_argument("--model", default="google/gemini-2.5-flash", help="LLM model")
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1", help="API base URL")
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY", help="API key env var")
    parser.add_argument("--per-category", type=int, default=1, help="Questions per (category, source) pair")
    parser.add_argument("--workers", type=int, default=1, help="Parallel workers")
    args = parser.parse_args()

    api_key = os.environ.get(args.api_key_env, "")
    if not api_key:
        print(f"ERROR: Set {args.api_key_env} environment variable")
        sys.exit(1)

    # Pre-load corpus contexts (3 calls, cached for all questions)
    print("Loading corpus contexts...")
    corpus_contexts: dict[str, CorpusContext] = {}
    for corpus in OUTPUT_DIRS:
        ctx = build_corpus_context(corpus)
        corpus_contexts[corpus] = ctx
        tier_b_size = len(ctx.tier_b_sections)
        proj_count = ctx.projection_listing.count("\n")
        print(f"  {corpus}: tier_a={len(ctx.tier_a_content)}B tier_b={tier_b_size}B projections={proj_count}")
    print()

    questions = select_questions(per_category=args.per_category)
    n = len(questions)
    print(f"Running {n} questions ({n} router calls + {n} answerer calls = {n * 2} API calls)")
    print(f"  Model: {args.model} (router + answerer)")
    print(f"  Workers: {args.workers}")
    print(f"  Router context: Tier A + Tier B + projection listing (cached per corpus)")
    print()

    results: list[TestResult] = [None] * n  # type: ignore[list-item]
    counter = {"done": 0}
    lock = threading.Lock()
    total_t0 = time.monotonic()

    def _run_one(idx: int, q: TestQuestion) -> None:
        ctx = corpus_contexts[q.source]
        try:
            result = run_question(q, api_key, args.model, args.base_url, ctx)
        except Exception as e:
            result = TestResult(
                source=q.source, category=q.category, qid=q.qid,
                question=q.question, reference_answer=q.reference_answer,
                router_model=args.model, answerer_model=args.model,
                routed_files=[], router_reasoning="", answer="",
                router_time_s=0, answerer_time_s=0, total_time_s=0,
                error=str(e),
            )
        results[idx] = result
        with lock:
            counter["done"] += 1
            done = counter["done"]
        status = "ERR" if result.error else "OK"
        files_str = ", ".join(result.routed_files[:3]) if result.routed_files else "(tier_a)"
        if len(result.routed_files) > 3:
            files_str += f" +{len(result.routed_files) - 3}"
        cached = f" cached={result.router_cached_tokens}" if result.router_cached_tokens else ""
        halluc = f" HALLUC={len(result.missing_files)}" if result.missing_files else ""
        print(
            f"[{done:3d}/{n}] {status} {q.source}|{q.category}|{q.qid} "
            f"r={result.router_time_s}s a={result.answerer_time_s}s "
            f"files=[{files_str}]{cached}{halluc}"
        )

    if args.workers > 1:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(_run_one, i, q): i for i, q in enumerate(questions)}
            for f in as_completed(futures):
                f.result()
    else:
        for i, q in enumerate(questions):
            _run_one(i, q)

    # ── Summary ──
    total_elapsed = time.monotonic() - total_t0
    print(f"\n{'=' * 80}")
    print("RESULTS SUMMARY")
    print(f"{'=' * 80}")

    # Per-question details (truncated for large runs)
    if n <= 30:
        for r in results:
            print(f"\n{'─' * 80}")
            print(f"{r.source} | {r.category} | {r.qid}")
            print(f"Q: {r.question}")
            print(f"Reference: {r.reference_answer[:200]}")
            print(f"Files: {', '.join(r.routed_files) if r.routed_files else '(tier_a only)'}")
            if r.missing_files:
                print(f"Hallucinated: {', '.join(r.missing_files)}")
            print(f"Answer: {r.answer[:300]}")
            if r.error:
                print(f"ERROR: {r.error}")

    # ── Aggregate stats ──
    print(f"\n{'=' * 80}")
    total_router = sum(r.router_time_s for r in results)
    total_answerer = sum(r.answerer_time_s for r in results)
    total_router_in = sum(r.router_input_tokens or 0 for r in results)
    total_router_out = sum(r.router_output_tokens or 0 for r in results)
    total_ans_in = sum(r.answerer_input_tokens or 0 for r in results)
    total_ans_out = sum(r.answerer_output_tokens or 0 for r in results)
    total_cached = sum(r.router_cached_tokens or 0 for r in results)

    # Pricing: flash $0.30/$2.50 per M tokens, cached at 0.25x input
    uncached_router_in = total_router_in - total_cached
    router_cost = (uncached_router_in * 0.30 + total_cached * 0.075 + total_router_out * 2.50) / 1_000_000
    answerer_cost = (total_ans_in * 0.30 + total_ans_out * 2.50) / 1_000_000
    total_cost = router_cost + answerer_cost

    errors = sum(1 for r in results if r.error)
    hallucinations = sum(1 for r in results if r.missing_files)
    tier_a_only = sum(1 for r in results if not r.routed_files and not r.error)

    print(f"Questions:       {n}")
    print(f"API calls:       {n * 2} (600 router + 600 answerer)")
    print(f"Wall time:       {total_elapsed:.1f}s")
    print(f"Router time:     {total_router:.1f}s")
    print(f"Answerer time:   {total_answerer:.1f}s")
    print(f"Router tokens:   in={total_router_in:,} (cached={total_cached:,}) out={total_router_out:,}")
    print(f"Answerer tokens: in={total_ans_in:,} out={total_ans_out:,}")
    print(f"Cost:            router=${router_cost:.4f} answerer=${answerer_cost:.4f} total=${total_cost:.4f}")
    print(f"Errors:          {errors}/{n}")
    print(f"Hallucinated:    {hallucinations}/{n} questions had invalid file paths")
    print(f"Tier-A only:     {tier_a_only}/{n} questions answered from Tier A alone")

    # ── Save JSON ──
    out_path = Path("internals/evaluation_results.json")
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
