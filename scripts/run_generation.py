#!/usr/bin/env python3
"""End-to-end generation pipeline: projection inference + Tier A enhancement.

Usage:
    export OPENROUTER_API_KEY=sk-or-...
    python scripts/run_generation.py
    python scripts/run_generation.py --corpora iosxr
    python scripts/run_generation.py --model google/gemini-2.5-flash --workers 4
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO
from pathlib import Path

from dotenv import load_dotenv
from ruamel.yaml import YAML

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from decoct.assembly.tier_a_spec import dump_tier_a_spec
from decoct.assembly.tier_builder import merge_tier_a_spec
from decoct.learn_projections import infer_projection_spec
from decoct.learn_tier_a import infer_tier_a_spec
from decoct.projections.generator import generate_projection
from decoct.projections.spec_loader import dump_projection_spec

# ── Corpus config ────────────────────────────────────────────────────────────

CORPORA: dict[str, Path] = {
    "iosxr": Path("output/iosxr"),
    "hybrid-infra": Path("output/hybrid-infra"),
    "entra-intune": Path("output/entra-intune"),
}

SPEC_BASE = Path("specs")

# Pattern for numbered subtypes like ansible-playbook_1, iosxr-access-pe_2
_SUBTYPE_RE = re.compile(r"^(.+)_(\d+)$")


def discover_base_types(output_dir: Path) -> list[str]:
    """Find base entity types from *_classes.yaml files, skipping numbered subtypes."""
    types: list[str] = []
    for f in sorted(output_dir.glob("*_classes.yaml")):
        type_id = f.stem.removesuffix("_classes")
        if _SUBTYPE_RE.match(type_id):
            continue
        types.append(type_id)
    return types


def run_projection_for_type(
    corpus: str,
    output_dir: Path,
    type_id: str,
    model: str,
    base_url: str,
    api_key_env: str,
) -> str:
    """Infer projection spec + generate projections for one type. Returns status message."""
    t0 = time.monotonic()

    # Step 2a: Infer projection spec
    spec = infer_projection_spec(
        output_dir=output_dir,
        type_id=type_id,
        model=model,
        base_url=base_url,
        api_key_env=api_key_env,
    )

    # Save spec
    spec_dir = SPEC_BASE / "projections" / type_id
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_file = spec_dir / "projection_spec.yaml"
    spec_file.write_text(dump_projection_spec(spec))

    # Step 2b: Load tier B+C and generate projections
    yaml = YAML(typ="safe")
    classes_file = output_dir / f"{type_id}_classes.yaml"
    instances_file = output_dir / f"{type_id}_instances.yaml"

    tier_b = yaml.load(classes_file.read_text())
    tier_c = yaml.load(instances_file.read_text()) if instances_file.exists() else {}

    proj_dir = output_dir / "projections" / type_id
    proj_dir.mkdir(parents=True, exist_ok=True)

    rt_yaml = YAML(typ="rt")
    rt_yaml.default_flow_style = False

    for subj in spec.subjects:
        projected = generate_projection(tier_b, tier_c, subj)
        out_file = proj_dir / f"{subj.name}.yaml"
        stream = StringIO()
        rt_yaml.dump(projected, stream)
        out_file.write_text(stream.getvalue())

    elapsed = time.monotonic() - t0
    return (
        f"  {corpus}/{type_id}: {len(spec.subjects)} subjects, "
        f"spec → {spec_file}, projections → {proj_dir} ({elapsed:.1f}s)"
    )


def run_tier_a_enhancement(
    corpus: str,
    output_dir: Path,
    model: str,
    base_url: str,
    api_key_env: str,
) -> str:
    """Infer Tier A spec + merge into tier_a.yaml. Returns status message."""
    t0 = time.monotonic()

    # Step 3a: Infer Tier A spec
    spec = infer_tier_a_spec(
        output_dir=output_dir,
        model=model,
        base_url=base_url,
        api_key_env=api_key_env,
    )

    # Save spec
    spec_dir = SPEC_BASE / "tier-a" / corpus
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_file = spec_dir / "tier_a_spec.yaml"
    spec_file.write_text(dump_tier_a_spec(spec))

    # Step 3b: Load existing tier_a.yaml + merge
    tier_a_file = output_dir / "tier_a.yaml"
    yaml = YAML(typ="safe")
    tier_a = yaml.load(tier_a_file.read_text())

    merged = merge_tier_a_spec(tier_a, spec, output_dir=output_dir)

    rt_yaml = YAML(typ="rt")
    rt_yaml.default_flow_style = False
    stream = StringIO()
    rt_yaml.dump(merged, stream)
    tier_a_file.write_text(stream.getvalue())

    elapsed = time.monotonic() - t0
    return (
        f"  {corpus}: spec → {spec_file}, "
        f"enhanced tier_a.yaml ({len(spec.type_descriptions)} types, {elapsed:.1f}s)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run generation pipeline (projections + Tier A)")
    parser.add_argument(
        "--corpora", nargs="*", default=list(CORPORA.keys()),
        choices=list(CORPORA.keys()),
        help="Corpora to process (default: all)",
    )
    parser.add_argument("--model", default="google/gemini-2.5-flash", help="LLM model")
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1", help="API base URL")
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY", help="API key env var")
    parser.add_argument("--workers", type=int, default=4, help="Max parallel workers per corpus")
    args = parser.parse_args()

    api_key = os.environ.get(args.api_key_env, "")
    if not api_key:
        print(f"ERROR: Set {args.api_key_env} environment variable")
        sys.exit(1)

    total_t0 = time.monotonic()

    for corpus in args.corpora:
        output_dir = CORPORA[corpus]
        if not output_dir.exists():
            print(f"SKIP: {output_dir} does not exist")
            continue

        # ── Step 2: Projection inference + generation ──
        base_types = discover_base_types(output_dir)
        print(f"\n{'=' * 70}")
        print(f"CORPUS: {corpus} — {len(base_types)} base types")
        print(f"{'=' * 70}")
        print(f"Base types: {', '.join(base_types)}")
        print(f"\nStep 2: Projections (model={args.model}, workers={args.workers})")

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(
                    run_projection_for_type,
                    corpus, output_dir, type_id,
                    args.model, args.base_url, args.api_key_env,
                ): type_id
                for type_id in base_types
            }
            for future in as_completed(futures):
                type_id = futures[future]
                try:
                    msg = future.result()
                    print(msg)
                except Exception as e:
                    print(f"  ERROR ({corpus}/{type_id}): {e}")

        # ── Step 3: Tier A enhancement ──
        print(f"\nStep 3: Tier A enhancement (model={args.model})")
        try:
            msg = run_tier_a_enhancement(corpus, output_dir, args.model, args.base_url, args.api_key_env)
            print(msg)
        except Exception as e:
            print(f"  ERROR ({corpus} tier-a): {e}")

    elapsed = time.monotonic() - total_t0
    print(f"\n{'=' * 70}")
    print(f"Generation complete in {elapsed:.1f}s")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
