# Entity-Graph Pipeline — Implementation Handoff

## What Was Built

A complete entity-graph compression pipeline (spec v1.3.1) — the core compression system for decoct.

The pipeline parses infrastructure configs into an entity graph, discovers types via bootstrap profiling, extracts class hierarchies, compresses deltas, and emits three-tier YAML output with 100% reconstruction fidelity.

## Pipeline Phases

```
Config files
  → [1] IOS-XR Adapter (parse + entity extraction)
  → [2] Bootstrap Loop (type seeding → profiling → refinement → convergence)
  → [3] Composite Decomposition (shadow map + template refs)
  → [4] Class Extraction (greedy frequent-bundle)
  → [5] Delta Compression (subclass promotion)
  → [6] Normalisation (phone book + instance_attrs split)
  → [7] Reconstruction Validation (0 mismatches required)
  → [8] Assembly (Tier A/B/C YAML output)
```

## Results on 86 IOS-XR Fixtures

| Type | Entities | Base Attrs | Classes | Subclasses |
|---|---|---|---|---|
| iosxr-access-pe | 60 | 91 | 3 | 3 |
| iosxr-bng | 8 | 107 | 0 | 0 |
| iosxr-p-core | 6 | 151 | 0 | 0 |
| iosxr-rr | 4 | 120 | 0 | 0 |
| iosxr-services-pe | 8 | 77 | 0 | 0 |

**Gate test: 0 reconstruction mismatches across all 86 entities.**

## Codebase

### Source (3,537 lines, 41 files)

```
src/decoct/
  core/               532 lines — types, canonical, hashing, composite_value,
                                  entity_graph, config, io
  adapters/           607 lines — base adapter ABC, IOS-XR parser + extraction
  analysis/           216 lines — entropy, profiler, tier_classifier
  discovery/          535 lines — type_seeding, type_discovery, anti_unification,
                                  bootstrap, composite_decomp
  compression/        715 lines — class_extractor, delta, normalisation,
                                  phone_book, inversion
  assembly/           330 lines — tier_builder, assertions, token_estimator
  reconstruction/     456 lines — reconstitute, validator
  entity_pipeline.py  146 lines — orchestrator
```

### Tests (1,400 lines, 133 tests)

```
tests/
  test_core/                  — canonical, entity_graph, config
  test_adapters/              — iosxr parser, paths, adapter (per-role + corpus)
  test_analysis.py            — entropy, final role, bootstrap role, tier C storage
  test_discovery.py           — type seeding, anti-unification
  test_composite_decomp.py    — shadow map, template IDs, re-profiling, threshold
  test_class_extractor.py     — base class, universal B, greedy bundles, min_support
  test_delta.py               — delta computation, overrides, ABSENT handling
  test_normalisation.py       — phone book routing, instance_attrs, relationships
  test_reconstruction.py      — precedence chain, ABSENT, template expansion
  test_assembly.py            — ID range compression round-trip
  test_entity_graph_e2e.py    — THE gate test (86 configs, 5 types, 0 mismatches)
```

### Running

```bash
python3 -m venv .venv && source .venv/bin/activate
python3 -m pip install -e ".[dev]"

# All entity-graph tests
python3 -m pytest tests/ --ignore=tests/test_learn.py -v

# Just the gate test
python3 -m pytest tests/test_entity_graph_e2e.py -v

# Lint + type check
ruff check src/decoct/
mypy src/decoct/ --ignore-missing-imports

# Generate Tier A/B/C YAML output
python3 scripts/run_pipeline.py
# Output goes to output/iosxr/
```

## Key Design Decisions

### Spec-mandated UPPER_CASE function names
`CANONICAL_KEY`, `CANONICAL_EQUAL`, `VALUE_KEY`, `ITEM_KEY`, `IS_SCALAR_LIKE`, `STABLE_CONTENT_HASH` — these match the spec notation. Suppressed via `[tool.ruff.lint.per-file-ignores]` in pyproject.toml.

### CompositeValue wrapping
BGP neighbors, EVPN EVIs, bridge-domains, bridge-groups, and route-policies are wrapped in `CompositeValue` (map or list). This prevents per-device paths like `evpn.evi.10000.*` from appearing as unique flat attributes (which would break type discovery by creating 60 singleton types instead of 1 type with 60 entities).

### Anti-unification restricted to signal paths
Type refinement compares entities using only bootstrap signal paths (VALUE_SIGNAL + PRESENCE_SIGNAL), not all 170+ attributes. Without this, variable counts exceeded `max_anti_unify_variables=3` for every pair, preventing any merging.

### Subsumed prefix filtering
When a composite value covers a subtree (e.g., `evpn.evis` covers all `evpn.evi.*` paths), the flat paths under that prefix are removed from the entity's attributes. Without this, both the composite and the flat paths would exist, causing double-counting and type-discovery failures.

### v1 Stubs (correct but not optimal)
These are intentionally simple implementations that produce correct output:

| Function | v1 Behaviour | Future Improvement |
|---|---|---|
| `cluster_and_anti_unify_composites()` | One cluster per distinct value | Cross-value template extraction |
| `anti_unify(a, b)` | Path-by-path comparison | Deeper structural anti-unification |
| `token_estimate_*()` | `len(yaml_str) // 4` | tiktoken cl100k_base |
| `detect_foreign_keys_on_scalar_attrs()` | Returns empty dict | FK detection from value overlap |

## Major Bugs Fixed During Implementation

1. **Type over-splitting (60 types instead of 1)** — Three related issues:
   - Anti-unification compared all attributes instead of signal paths only
   - Composite collection didn't recurse into non-section nodes (`evpn`, `l2vpn`)
   - Flat paths weren't filtered against subsumed composite prefixes

2. **tier_builder.py AttributeError** — `ClassDef` has no `attrs` field (it's `own_attrs`). Fixed `base_only_count` calculation.

3. **profiler.py placeholder** — Bootstrap role was initialized with a non-functional placeholder. Fixed to use `BootstrapSignal.NONE` then compute after profile creation.

## What's NOT Built

Per the plan, these are explicitly out of scope:

- No other adapters (YANG, OpenAPI, JSON Schema, ADMX, Augeas)
- No CLI integration (`decoct entity-graph` command)
- No evaluation harness
- No progressive loading / runtime API
- No `decoct diff`

## File Quick Reference

| Need to... | Look at... |
|---|---|
| Understand the spec | `docs/dev/decoct-spec-v1.3.1.md` |
| Run the pipeline | `src/decoct/entity_pipeline.py` |
| Add a new adapter | Subclass `src/decoct/adapters/base.py`, see `iosxr.py` |
| Change classification thresholds | `src/decoct/core/config.py` (EntityGraphConfig) |
| Understand type discovery | `src/decoct/discovery/bootstrap.py` → `type_discovery.py` |
| Understand class extraction | `src/decoct/compression/class_extractor.py` |
| Debug reconstruction failures | `src/decoct/reconstruction/validator.py` |
| See the IOS-XR parser | `src/decoct/adapters/iosxr.py` (563 lines, the largest file) |
| See output format | `scripts/run_pipeline.py` → `output/iosxr/` |
