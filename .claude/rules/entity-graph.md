# Entity-Graph Pipeline

The entity-graph pipeline is an independent subsystem — separate from the pass-based pipeline, no shared code paths, different data model. It compresses fleets of infrastructure configs into a three-tier representation (shared classes + per-entity differences).

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
python scripts/run_pipeline.py               # IOS-XR → output/entity-graph/
python scripts/run_hybrid_infra.py           # Hybrid → output/hybrid-infra/
python scripts/run_entra_intune.py           # Entra → output/entra-intune/

# CLI
decoct entity-graph stats -i <input_dir> -o <output_dir>
decoct entity-graph generate-questions -i <input_dir> -o <output_dir>
decoct entity-graph evaluate -i <input_dir> -o <output_dir>
decoct entity-graph infer-spec -i <input_dir> [-o spec.yaml] [--model ...] [--base-url ...]
```

## Module Layout

```
src/decoct/
  core/               Entity, Attribute, CompositeValue, EntityGraph, canonical functions, config
  adapters/           BaseAdapter + IOS-XR (.cfg), Hybrid-Infra (YAML/JSON/INI), Entra-Intune (JSON)
  analysis/           Attribute profiling, Shannon entropy, tier/role classification
  discovery/          Type seeding (Jaccard), bootstrap loop, anti-unification, composite decomposition
  compression/        Class extraction (greedy bundles), delta compression, normalisation, phone book
  assembly/           Tier A/B/C YAML builders, ID range compression, assertions, token estimation
  reconstruction/     Entity reconstitution + validation (100% fidelity gate test)
  qa/                 Question generation (6 categories) + LLM evaluation harness
  entity_pipeline.py  Top-level orchestrator (chains all 8 phases)
  entity_graph_stats.py  Compression statistics + CLI formatting
  learn_ingestion.py  LLM-assisted ingestion spec inference (requires [llm])
```

## 8-Phase Pipeline

1. Canonicalise — adapter parses input → EntityGraph (one file = one entity)
2. Bootstrap Loop — seed types (Jaccard clustering) → profile → refine (anti-unification) → converge
3. Composite Decomposition — template extraction + per-entity deltas for high-cardinality composites
4. Class Extraction — greedy frequent-bundle clustering for shared attribute sets
5. Delta Compression — subclass promotion for residual B-layer differences (max depth 2)
6. Normalisation — build Tier C (phone book for dense scalars, instance_attrs for sparse)
7. Reconstruction Validation — gate test: 8 structural invariants + per-entity fidelity check
8. Assembly — emit Tier A (fleet overview), Tier B (class definitions), Tier C (per-entity differences)

## Test Fixtures and Output

- `tests/fixtures/iosxr/configs/` — 86 IOS-XR .cfg files
- `tests/fixtures/entra-intune/resources/` — 88 Entra/Intune .json files
- `tests/fixtures/hybrid-infra/` — 100 mixed-format files (YAML/JSON/INI)
- `output/entity-graph/`, `output/hybrid-infra/`, `output/entra-intune/` — sample output (checked in)

## Key Rules

- Secrets masking is implemented (R2 complete) — pre-flatten + post-flatten masking via `src/decoct/secrets/`
- Entity-graph code uses `UPPER_CASE` function names for canonical functions (CANONICAL_KEY, CANONICAL_EQUAL, etc.) — suppressed via ruff per-file overrides
- The gate test (`test_entity_graph_e2e.py`) must pass with 0 reconstruction mismatches before any PR
- CompositeValue wrapping is critical — without it, per-device structures shatter type discovery
- LLM dependencies stay in `[llm]` extra — the deterministic pipeline must work without them
