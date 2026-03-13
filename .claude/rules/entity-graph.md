# Entity-Graph Pipeline

The entity-graph pipeline compresses fleets of infrastructure configs into a three-tier representation (shared classes + per-entity differences).

**Authoritative design reference:** `docs/entity-graph-architecture.md` — all architecture, interfaces, design decisions, and roadmap (Sections 1-12).

**Data manual (how to read output):** `docs/entity-graph-data-manual.md`

## Quick Reference

```bash
# Install
pip install -e ".[dev]"          # Pipeline + tests
pip install -e ".[dev,llm]"      # Also enables QA evaluation

# Tests
pytest -k entity -v                          # All entity-graph tests
pytest tests/test_entity_graph_e2e.py -v     # Gate test (86 IOS-XR configs, 0 mismatches)

# Regenerate output samples
python scripts/run_pipeline.py               # IOS-XR → output/iosxr/
python scripts/run_hybrid_infra.py           # Hybrid → output/hybrid-infra/
python scripts/run_entra_intune.py           # Entra → output/entra-intune/

# CLI
decoct entity-graph stats -i <input_dir> -o <output_dir>
decoct entity-graph generate-questions -i <input_dir> -o <output_dir>
decoct entity-graph evaluate -i <input_dir> -o <output_dir>
decoct entity-graph infer-spec -i <input_dir> [-o spec.yaml] [--model ...] [--base-url ...]

# Subject projections (R3)
decoct entity-graph project -o <output_dir> -s <spec_file> [--type TYPE] [--subjects s1,s2]
decoct entity-graph infer-projections -o <output_dir> --type <type_id> [--model ...] [--base-url ...]

# Enhanced Tier A (R4)
decoct entity-graph review-tier-a -o <output_dir> [--model ...] [--base-url ...] [--output spec.yaml]
decoct entity-graph enhance-tier-a -o <output_dir> -s <tier_a_spec.yaml>
```

## Module Layout

```
src/decoct/
  core/               Entity, Attribute, CompositeValue, EntityGraph, canonical functions, config
  adapters/           BaseAdapter + IOS-XR (.cfg), Hybrid-Infra (YAML/JSON/INI), Entra-Intune (JSON)
  analysis/           Attribute profiling, Shannon entropy, tier/role classification
  discovery/          Type seeding (Jaccard), bootstrap loop, anti-unification, composite decomposition
  compression/        CompressionEngine ABC + registry, greedy-bundle engine, class extraction, delta compression, normalisation, phone book
  assembly/           Tier A/B/C YAML builders, ID range compression, assertions, token estimation
  reconstruction/     Entity reconstitution + validation (100% fidelity gate test) + strict source fidelity
  qa/                 Question generation (6 categories) + LLM evaluation harness
  entity_pipeline.py  Top-level orchestrator (chains all 8 phases)
  entity_graph_stats.py  Compression statistics + CLI formatting
  learn_ingestion.py  LLM-assisted ingestion spec inference (requires [llm])
  projections/        Subject projections: models, path matcher, spec loader, generator
  learn_projections.py  LLM-assisted projection spec inference (requires [llm])
  learn_tier_a.py     LLM-assisted Tier A spec inference (requires [llm])
  secrets/            Secret masking (pre-flatten + post-flatten)
  tokens.py           Tiktoken wrapper (shared utility)
  formats.py          Input format detection + conversion (shared utility)
```

## Pipeline Phases

0. Secrets Masking — pre-flatten document masking + post-flatten attribute/leaf masking
1. Canonicalise — adapter parses input → EntityGraph (one file = one entity)
1.5. Source Fidelity — strict bidirectional token-sequence validation (0 mismatches for JSON/YAML/INI; warn mode for IOS-XR)
2. Bootstrap Loop — seed types (Jaccard clustering) → profile → refine (anti-unification) → converge
3. Composite Decomposition — template extraction + per-entity deltas for high-cardinality composites
4+5. Compression Engine — pluggable engine (default: greedy-bundle) runs class extraction + delta compression
6. Normalisation — build Tier C (phone book for dense scalars, instance_attrs for sparse)
7. Reconstruction Validation — gate test: 8 structural invariants + per-entity fidelity check
8. Assembly — emit Tier A (fleet overview), Tier B (class definitions), Tier C (per-entity differences)

## Test Fixtures and Output

- `tests/fixtures/iosxr/configs/` — 86 IOS-XR .cfg files
- `tests/fixtures/entra-intune/resources/` — 88 Entra/Intune .json files
- `tests/fixtures/hybrid-infra/` — 100 mixed-format files (YAML/JSON/INI)
- `output/iosxr/`, `output/hybrid-infra/`, `output/entra-intune/` — sample output (checked in)
- `specs/projections/iosxr-access-pe/` — hand-authored projection spec
- `specs/tier-a/iosxr/`, `specs/tier-a/entra-intune/`, `specs/tier-a/hybrid-infra/` — LLM-generated Tier A specs (R4)
- `output/iosxr/projections/` — IOS-XR projection output (hand-authored spec)
- `output/entra-intune/projections/` — Entra-Intune projection output (LLM-inferred specs)
- `output/hybrid-infra/projections/` — Hybrid-Infra projection output (LLM-inferred specs)

## Key Rules

- Secrets masking is implemented (R2 complete) — pre-flatten + post-flatten masking via `src/decoct/secrets/`
- Strict source fidelity validation runs on every pipeline invocation — `strict_fidelity.py` replaces the old fuzzy `source_fidelity.py`
- IOS-XR adapter has known source fidelity issues (~1502 mismatches) — use `source_fidelity_mode="warn"` in tests. See architecture doc §11 for details
- Entity-graph code uses `UPPER_CASE` function names for canonical functions (CANONICAL_KEY, CANONICAL_EQUAL, etc.) — suppressed via ruff per-file overrides
- The gate test (`test_entity_graph_e2e.py`) must pass with 0 reconstruction mismatches before any PR
- CompositeValue wrapping is critical — without it, per-device structures shatter type discovery
- LLM dependencies stay in `[llm]` extra — the deterministic pipeline must work without them
