#!/usr/bin/env python3
"""Run answerer-only comparison across models on the 60-question sample.

Each question gets its own isolated API call — no context carryover.
Uses the same routed files and prompts prepared in internals/opus_test/.

Usage:
    export OPENROUTER_API_KEY=sk-or-...
    python scripts/run_model_comparison.py --model anthropic/claude-sonnet-4.6
    python scripts/run_model_comparison.py --model anthropic/claude-opus-4.6
    python scripts/run_model_comparison.py --model google/gemini-2.5-flash
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()


@dataclass
class AnswerResult:
    idx: int
    qid: str
    source: str
    category: str
    question: str
    reference_answer: str
    gemini_grade: str
    gemini_cause: str
    model: str
    answer: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    time_s: float = 0.0
    error: str | None = None


def call_openrouter(
    model: str,
    prompt: str,
    api_key: str,
    base_url: str,
) -> tuple[str, dict]:
    """Single answerer API call. Returns (content, usage_dict)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/decoct-io/decoct",
        "X-Title": "decoct-model-comparison",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
    }

    with httpx.Client(timeout=300.0) as client:
        resp = client.post(base_url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return content, usage


def run_one(
    item: dict,
    model: str,
    api_key: str,
    base_url: str,
) -> AnswerResult:
    """Run one question through the answerer model."""
    prompt_file = Path(item["prompt_file"])
    prompt = prompt_file.read_text(encoding="utf-8")

    t0 = time.monotonic()
    try:
        answer, usage = call_openrouter(model, prompt, api_key, base_url)
        elapsed = time.monotonic() - t0

        details = usage.get("prompt_tokens_details") or {}
        return AnswerResult(
            idx=item["idx"],
            qid=item["qid"],
            source=item["source"],
            category=item["category"],
            question=item["question"],
            reference_answer=item["reference_answer"],
            gemini_grade=item["gemini_grade"],
            gemini_cause=item.get("gemini_cause", ""),
            model=model,
            answer=answer,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            cached_tokens=details.get("cached_tokens"),
            time_s=round(elapsed, 2),
        )
    except Exception as e:
        elapsed = time.monotonic() - t0
        return AnswerResult(
            idx=item["idx"],
            qid=item["qid"],
            source=item["source"],
            category=item["category"],
            question=item["question"],
            reference_answer=item["reference_answer"],
            gemini_grade=item["gemini_grade"],
            gemini_cause=item.get("gemini_cause", ""),
            model=model,
            answer="",
            time_s=round(elapsed, 2),
            error=str(e),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run answerer model comparison")
    parser.add_argument("--model", required=True, help="Model ID (e.g., anthropic/claude-sonnet-4.6)")
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1/chat/completions")
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers")
    parser.add_argument("--manifest", default="internals/opus_test/manifest.json")
    args = parser.parse_args()

    api_key = os.environ.get(args.api_key_env, "")
    if not api_key:
        print(f"ERROR: Set {args.api_key_env}")
        sys.exit(1)

    with open(args.manifest) as f:
        manifest = json.load(f)

    model_short = args.model.split("/")[-1]
    print(f"Running {len(manifest)} questions through {args.model}")
    print(f"  Workers: {args.workers}")
    print()

    results: list[AnswerResult] = []
    t_total = time.monotonic()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(run_one, item, args.model, api_key, args.base_url): item
            for item in manifest
        }
        for future in as_completed(futures):
            item = futures[future]
            result = future.result()
            results.append(result)
            status = "ERR" if result.error else "OK"
            tok = f" in={result.input_tokens} out={result.output_tokens}" if result.input_tokens else ""
            print(f"[{len(results):3d}/{len(manifest)}] {status} {result.source}|{result.category}|{result.qid} t={result.time_s}s{tok}")

    # Sort by idx
    results.sort(key=lambda r: r.idx)

    elapsed = time.monotonic() - t_total
    total_in = sum(r.input_tokens or 0 for r in results)
    total_out = sum(r.output_tokens or 0 for r in results)
    total_cached = sum(r.cached_tokens or 0 for r in results)
    errors = sum(1 for r in results if r.error)

    print(f"\n{'='*60}")
    print(f"Model:    {args.model}")
    print(f"Questions: {len(results)}")
    print(f"Wall time: {elapsed:.1f}s")
    print(f"Tokens:   in={total_in:,} (cached={total_cached:,}) out={total_out:,}")
    print(f"Errors:   {errors}/{len(results)}")

    # Save
    out_path = Path(f"internals/comparison_{model_short}.json")
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
