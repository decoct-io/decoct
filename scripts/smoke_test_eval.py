#!/usr/bin/env python3
"""Smoke-test eval questions: send 5 questions per source to Claude Sonnet.

Picks 1 question per class (first of each), sends with full raw context,
prints model answer vs reference answer side-by-side.

Usage:
    python scripts/smoke_test_eval.py [--source iosxr|hybrid-infra|entra-intune]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from decoct.qa.eval_models import EvalQuestionBank, EvalQuestionClass
from decoct.qa.generate_eval import load_eval_bank
from decoct.qa.evaluate import build_raw_context
from decoct.tokens import count_tokens

ROOT = Path(__file__).resolve().parent.parent

SOURCES = {
    "iosxr": ROOT / "tests/fixtures/iosxr/configs",
    "hybrid-infra": ROOT / "tests/fixtures/hybrid-infra/configs",
    "entra-intune": ROOT / "tests/fixtures/entra-intune/resources",
}


def pick_questions(bank: EvalQuestionBank) -> list:
    """Pick first question from each of the 5 classes."""
    picked = []
    for cls in EvalQuestionClass:
        for q in bank.questions:
            if q.question_class == cls:
                picked.append(q)
                break
    return picked


def ask_sonnet(context: str, question: str) -> str:
    """Call Claude Sonnet with raw context + question."""
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system="You are answering questions about infrastructure configuration data. "
               "Provide a concise, factual answer based only on the provided context.",
        messages=[{"role": "user", "content": f"{context}\n\n---\nQuestion: {question}"}],
    )
    return resp.content[0].text


def trunc(s: str, n: int = 120) -> str:
    s = s.replace("\n", " ")
    return s[:n] + "..." if len(s) > n else s


def run_source(source: str) -> None:
    bank_path = ROOT / f"output/{source}/eval/candidates.yaml"
    config_dir = SOURCES[source]

    print(f"\n{'='*80}")
    print(f"  {source}")
    print(f"{'='*80}")

    bank = load_eval_bank(bank_path)
    context = build_raw_context(config_dir)
    tokens = count_tokens(context)
    print(f"  Raw context: {tokens:,} tokens | {len(bank.questions)} questions in bank\n")

    questions = pick_questions(bank)

    for q in questions:
        print(f"  [{q.id}] {q.question_class.value} / {q.difficulty.value}")
        print(f"  Q: {trunc(q.question, 100)}")

        answer = ask_sonnet(context, q.question)

        print(f"  Model:     {trunc(answer)}")
        print(f"  Reference: {trunc(q.reference_answer)}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test eval questions against Claude Sonnet")
    parser.add_argument("--source", choices=list(SOURCES.keys()), help="Run one source only")
    args = parser.parse_args()

    sources = [args.source] if args.source else list(SOURCES.keys())
    for src in sources:
        run_source(src)


if __name__ == "__main__":
    main()
