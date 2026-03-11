#!/usr/bin/env python3
"""Generate hand-authored evaluation question banks for all 3 sources.

Constructs EvalQuestion objects directly and saves via save_eval_bank().
Re-runnable — overwrites existing candidates.yaml files.

Usage:
    python scripts/generate_eval_questions.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is importable when running as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from decoct.qa.eval_models import EvalQuestionBank
from decoct.qa.generate_eval import save_eval_bank

from eval_questions.iosxr import (
    factual_retrieval as iosxr_fr,
    cross_reference as iosxr_cr,
    operational_inference as iosxr_oi,
    design_compliance as iosxr_dc,
    negative_absence as iosxr_na,
)
from eval_questions.hybrid_infra import (
    factual_retrieval as hybrid_fr,
    cross_reference as hybrid_cr,
    operational_inference as hybrid_oi,
    design_compliance as hybrid_dc,
    negative_absence as hybrid_na,
)
from eval_questions.entra_intune import (
    factual_retrieval as entra_fr,
    cross_reference as entra_cr,
    operational_inference as entra_oi,
    design_compliance as entra_dc,
    negative_absence as entra_na,
)


SOURCES = {
    "iosxr": {
        "output": "output/iosxr/eval/candidates.yaml",
        "generators": [iosxr_fr, iosxr_cr, iosxr_oi, iosxr_dc, iosxr_na],
    },
    "hybrid-infra": {
        "output": "output/hybrid-infra/eval/candidates.yaml",
        "generators": [hybrid_fr, hybrid_cr, hybrid_oi, hybrid_dc, hybrid_na],
    },
    "entra-intune": {
        "output": "output/entra-intune/eval/candidates.yaml",
        "generators": [entra_fr, entra_cr, entra_oi, entra_dc, entra_na],
    },
}


def main() -> None:
    root = Path(__file__).resolve().parent.parent

    for source, cfg in SOURCES.items():
        print(f"\n{'='*60}")
        print(f"Generating {source} eval questions...")
        print(f"{'='*60}")

        all_questions = []
        for gen_fn in cfg["generators"]:
            qs = gen_fn()
            print(f"  {qs[0].question_class.value}: {len(qs)} questions")
            all_questions.extend(qs)

        bank = EvalQuestionBank(
            questions=all_questions,
            source=source,
            generated_by="claude-code-manual",
            model_generate="claude-opus-4",
            model_validate="",
        )

        out_path = root / cfg["output"]
        save_eval_bank(bank, out_path)
        print(f"  Saved {len(all_questions)} questions → {out_path}")
        print(f"  Class counts: {bank.class_counts}")


if __name__ == "__main__":
    main()
