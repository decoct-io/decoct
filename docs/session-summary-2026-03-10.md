# Decoct — 26-Hour Session Summary (2026-03-09 18:00 → 2026-03-10 20:15 UTC)

This document summarises all development activity across ~20 Claude Code sessions over the past 26 hours, with particular focus on the entity-graph compression pipeline — its design, architecture, implementation, and iterative refinement.

---

## Table of Contents

1. [Chronological Session Summary](#1-chronological-session-summary)
2. [Entity-Graph System — Comprehensive Design Document](#2-entity-graph-system--comprehensive-design-document)
3. [Key Decisions and Lessons Learned](#3-key-decisions-and-lessons-learned)
4. [Current State and Open Items](#4-current-state-and-open-items)

---

## 1. Chronological Session Summary

### Phase A: Pass-Based Pipeline Polish (Mar 9, 18:00–18:15)

**Session: 33067d58** — Updated `CLAUDE.md` and `decoct-dev-plan.md` to reflect Phase 1 complete, Phase 2 mostly complete (30 bundled schemas, JSON/INI input, 10 passes). Fixed 5 doc inconsistencies across README, roadmap, steering docs. Committed and pushed.

### Phase B: Benchmark Harness (Mar 9, 18:15–18:28)

**Session: 4aa700d9** — Implemented `decoct benchmark` CLI subcommand + `src/decoct/benchmark.py` (435 lines). Three compression tiers (generic, schema, full). Auto-detects platforms, resolves bundled schemas. Reports per-file and aggregate token savings in markdown or JSON. Tests written and passing.

### Phase C: Public Corpus Benchmark (Mar 9, 18:28–19:08)

**Sessions: 961d2fbd, fc25c447** — Created `scripts/fetch_corpus.py` to fetch real-world configs from 8 curated GitHub repos (docker/awesome-compose, kubernetes/examples, ansible/ansible-examples, etc.) via sparse git checkout. Ran benchmark on 527 files across 7 platforms.

**Critical finding:** Schema tier had **negative compression** for Kubernetes (-211%) and Docker Compose (-119%). Root cause: `emit-classes` pass emitted ALL vendor schema defaults as header comments regardless of actual stripping — costing more tokens than it saved.

**User's key insight:** Requested an LZ77/Huffman-style general solution — discovering compression classes from corpus data rather than platform-specific rules. This became the conceptual seed for the entity-graph pipeline.

### Phase D: Corpus-Learned Classes — First Attempt (Mar 10, 11:40)

**Session: 4eb74683** — Implemented `src/decoct/corpus_classes.py` (~250 lines). General algorithm: flatten docs → discover instance levels → mine frequent (path, value) pairs → co-occurrence clustering → greedy score/select. Platform-agnostic — discovers `services.*` the same way LZ77 discovers repeated byte sequences.

### Phase E: IOS-XR Fixture Generator (Mar 10, 11:55–12:20)

**Session: 5f7644c6, 4cc1c8a9** — Built large-scale IOS-XR test fixtures. 86 devices: 60 Access PE, 6 P-Core, 4 RR, 8 BNG, 8 Services PE. CSV inputs + Jinja2 templates + Python generator script. Realistic BGP, ISIS, SR, BNG, EVPN, interface configs. One `.cfg` file per device in `tests/fixtures/iosxr/configs/`.

Also planned the Entra/Intune fixture generator.

### Phase F: Entity-Graph Pipeline — Core Implementation (Mar 10, 12:20–14:03)

**Sessions: df85dcb7, 0156ba43** — This was the main implementation session. The user provided a detailed specification (`docs/dev/decoct-spec-v1.3.1.md`, 1936 lines) and an implementation plan covering all 8 pipeline phases.

**Implemented (in order):**
1. `src/decoct/core/` — types.py, entity_graph.py, config.py, canonical.py, composite_value.py
2. `src/decoct/analysis/` — entropy.py, profiler.py, tier_classifier.py
3. `src/decoct/discovery/` — type_seeding.py, type_discovery.py, anti_unification.py, bootstrap.py, composite_decomp.py
4. `src/decoct/compression/` — class_extractor.py, delta.py, normalisation.py, phone_book.py, inversion.py
5. `src/decoct/assembly/` — tier_builder.py
6. `src/decoct/reconstruction/` — reconstitute.py, validator.py
7. `src/decoct/adapters/` — base.py, iosxr.py (563 lines)
8. `src/decoct/entity_pipeline.py` — top-level orchestrator (146 lines)
9. All unit + E2E tests — 97 tests passing, 0 reconstruction mismatches on 86 configs

**First successful run output:**
- 5 types discovered: iosxr-access-pe (60), iosxr-bng (8), iosxr-p-core (6), iosxr-rr (4), iosxr-services-pe (8)
- 91 base attrs for access-pe, 3 classes, 3 subclasses
- 100% reconstruction fidelity

**Also during this session:**
- Fixed `pyproject.toml` for venv installation
- Wrote handoff doc (`docs/dev/entity-graph-handoff.md`)
- Wrote data reader manual (`docs/entity-graph-data-manual.md`)
- Began planning Entra/Intune adapter

### Phase G: Entra/Intune Fixtures + Adapter (Mar 10, 13:34–15:39)

**Sessions: 1c33e76c, bbf25655, d5bcff4b** — Three-part effort:

1. **Entra/Intune Fixture Generator** — 88 JSON files (Microsoft Graph API format): 20 CA policies, 12 app registrations, 25 security groups, 10 compliance policies, 8 device configs, 4 app protection, 6 named locations, 3 cross-tenant. CSV + Jinja2 + Python script.

2. **Hybrid-Infra Fixture Generator ("Ridgeline Data")** — 100 mixed-format files (54 YAML + 15 JSON + 31 INI) across Docker Compose, Ansible, PostgreSQL, MariaDB, Traefik, cloud-init, Prometheus, sshd. Realistic messy multi-environment SaaS deployment narrative.

3. **Entra/Intune Adapter** (`src/decoct/adapters/entra_intune.py`, 343 lines) — Parses Graph API JSON, maps 13 OData types → 8 logical types, strips metadata fields, composite handling for arrays, two-pass relationship extraction (group_ref, assignment_target, tenant_ref).

### Phase H: Hybrid-Infra Adapter + Compression Fixes (Mar 10, 15:39–17:37)

**Sessions: 85ae3dc2, 95018073, e6a44f76, f5b6a9cb, 6a418b9b, d3119a8d** — Dense implementation and iteration:

1. **Entity-graph stats module** (`src/decoct/entity_graph_stats.py`, 388 lines) — `decoct entity-graph stats` CLI. Input/output directory scanning, per-tier/per-type token counts, markdown/JSON reports.

2. **QA comprehension harness** — Deterministic question generation (6 categories: SINGLE_VALUE, MULTI_ENTITY, EXISTENCE, COMPARISON, COUNT, ORDERING) + LLM-based evaluation comparing accuracy on raw vs compressed contexts.

3. **Updated data reader manual** — Added `!` section-existence marker explanation, hybrid-infra path conventions, composite value documentation.

4. **Hybrid-Infra Adapter** (`src/decoct/adapters/hybrid_infra.py`, 364 lines) — Generic multi-format adapter. Three fallback parsers (ruamel.yaml/json, tolerant INI, space-separated). Content-based type detection for 5 platforms; Jaccard fingerprint clustering for unknowns. Homogeneous map detection (Jaccard ≥ 0.5 on child key sets).

5. **Compression fix round 1** — Hybrid-infra showed -14% compression (output larger than input). Root cause: 100 entities split into 69 singleton types. Fix:
   - Replaced exact fingerprint type seeding with **Jaccard agglomerative clustering** (threshold 0.4)
   - Added **small-cluster merge guard** to prevent type shattering
   - Result: -14% → +16.7% compression

6. **Compression fix round 2** — Three further fixes:
   - **Fix A:** Stricter docker-compose detection (require `image` keys in service dicts)
   - **Fix B:** Single-child homogeneous map support (`min_children=1`)
   - **Fix C:** **Map-inner decomposition** for composite values — pools map entries across entities, extracts common base template, stores per-entity deltas. This was the major compression win.

7. **Reconstruction fidelity questions** — User asked about byte-exact reconstruction, ordering preservation (ACLs), and semantic validation. Led to ORDERING question category.

### Phase I: ORDERING Questions + Git Commits (Mar 10, 17:37–19:09)

**Session: 2c542564** — Added `ORDERING` question category to QA harness for validating list-order-sensitive semantics (ACL rules, Ansible task sequences). Parameterised question generation to work with any adapter. Committed all work as 25 logical git commits and pushed.

### Phase J: decoct.io Website + Documentation (Mar 10, 09:34–13:20)

**Sessions (decoct-io project): 39f6a633, 0a49839c, f92887d6** — Stripped decoct.io website to minimal "coming soon" landing page. Force-pushed as fresh first commit. Kept old content on local branch. Also set up clipboard image capture skill.

### Phase K: Entity-Graph Architecture Document (Mar 10, 20:00–20:12)

**Session: fac47976** — User requested a comprehensive entity-graph architecture document absorbing all existing docs (handoff, eval, data manual). This produced `docs/entity-graph-architecture.md` (767 lines), which is the authoritative reference. *This is the session that led to the current conversation.*

---

## 2. Entity-Graph System — Comprehensive Design Document

### 2.1 Purpose

The entity-graph pipeline compresses fleets of infrastructure configurations into a three-tier YAML representation that separates shared structure from per-entity differences. The compression is **lossless** — every entity can be reconstructed exactly from the output. Achieves 70-80% token savings on IOS-XR corpora; 16-30% on hybrid mixed-format corpora.

The pipeline operates entirely independently of the existing pass-based pipeline. No existing code was modified to build it.

### 2.2 Core Data Model

All types in `src/decoct/core/types.py`.

**Entity** — the atomic unit. One input file → one entity. ID comes from adapter (hostname for IOS-XR, filename stem for hybrid-infra, displayName for Entra-Intune). Has `schema_type_hint` (adapter's guess) and `discovered_type` (final assignment after bootstrap).

**Attribute** — entity property. Dot-separated key path (e.g., `router.isis.CORE.is-type`), value (scalar or CompositeValue), type string, source entity ID.

**CompositeValue** — wraps non-scalar structures (lists, dicts) that should remain atomic rather than flattened. Kind = "map" or "list". Critical for preventing type-discovery failure from path shattering. Examples: BGP neighbor blocks, Docker Compose services, Ansible task lists.

**Sentinels** — `ABSENT` (path exists in class template but removed for entity) and `MISSING` (path was never present). Distinguished from null.

**EntityGraph** (`src/decoct/core/entity_graph.py`, 76 lines) — stores entities by ID and relationships as (source, label, target) triples. Idempotent insertion, sorted accessor output for determinism.

**Canonical Functions** (`src/decoct/core/canonical.py`) — `CANONICAL_KEY()`, `CANONICAL_EQUAL()`, `VALUE_KEY()`, `ITEM_KEY()`, `IS_SCALAR_LIKE()`. Provide authoritative equality/hashing. JSON-serialised, float→int normalised, dict-key sorted.

### 2.3 Eight-Phase Pipeline

Orchestrated by `run_entity_graph_pipeline()` in `src/decoct/entity_pipeline.py` (146 lines):

```
Input files (.cfg, .yaml, .json, .ini, .conf)
  │
  ▼
[Phase 1] Canonicalise ── adapter.parse() + adapter.extract_entities() → EntityGraph
  │
  ▼
[Phase 2+3] Bootstrap Loop ── seed types → profile → refine → converge
  │
  ▼
[Phase 3.5] Composite Decomposition ── shadow map + template extraction
  │
  ▼
[Phase 4] Class Extraction ── greedy frequent-bundle clustering
  │
  ▼
[Phase 5] Delta Compression ── subclass promotion for compression gain
  │
  ▼
[Phase 6] Normalisation ── build Tier C (phone book + instance_attrs)
  │
  ▼
[Phase 7] Reconstruction Validation ── 100% fidelity gate test
  │
  ▼
[Phase 8] Assembly ── emit Tier A / B / C YAML
```

#### Phase 1: Canonicalise (Adapters)

Three adapters, all implementing `BaseAdapter`:

| Adapter | File | Lines | Input | Entity ID | Type Hinting |
|---------|------|-------|-------|-----------|--------------|
| IOS-XR | `adapters/iosxr.py` | 563 | `.cfg` (indentation-based) | hostname | Prefix patterns (P-CORE-, RR-, APE-) |
| Entra-Intune | `adapters/entra_intune.py` | 343 | `.json` (Graph API) | displayName | @odata.type → 8 logical types |
| Hybrid-Infra | `adapters/hybrid_infra.py` | 364 | YAML/JSON/INI | filename stem | Content detection for 5 platforms + Jaccard clustering |

**IOS-XR adapter specifics:**
- Custom indentation parser (1-space indent, `!` block terminators)
- Section keywords → path segments: `router isis CORE` → `router.isis.CORE`
- Composite value collection: BGP neighbors, EVPN EVIs, bridge-domains, route-policies
- Subsumed prefix filtering prevents double-counting composites vs flat paths
- Relationship extraction from interface descriptions (`TO-{hostname}` → `p2p_link`) and BGP neighbors

**Hybrid-Infra adapter specifics:**
- Three fallback parsers: standard load_input(), tolerant INI (duplicate key accumulation), space-separated (sshd-style)
- Homogeneous map detection: dict-of-dicts with structurally similar children (Jaccard ≥ 0.5) → CompositeValue(map) instead of recursive flattening
- Scalar arrays → comma-separated strings; object arrays → CompositeValue(list)

**Entra-Intune adapter specifics:**
- 13 OData types → 8 logical types via ODATA_TYPE_MAP
- Metadata stripping (@odata.type, id, timestamps) before flattening
- Two-pass relationship extraction: parse all entities → build UUID→displayName lookup → resolve references

#### Phase 2+3: Bootstrap Loop

**Type Seeding (Phase 2a)** — `src/decoct/discovery/type_seeding.py`. Hinted entities grouped by hint. Unhinted entities clustered using greedy agglomerative Jaccard clustering (threshold 0.4) on attribute key sets. Entities sorted by attribute count descending to seed clusters with most representative first.

**Attribute Profiling (Phase 2b)** — `src/decoct/analysis/profiler.py`. Per-path per-type: cardinality, Shannon entropy (normalised), coverage, value length stats. Role classification:
- **A_BASE**: coverage=1.0 AND cardinality=1 (universal constant)
- **C**: high entropy (H_norm > 0.8) or high cardinality. Below `small_group_floor` (8): stricter thresholds
- **B**: everything else (class-compressible)

Bootstrap signal classification for type refinement:
- **VALUE_SIGNAL**: A_BASE, or low-cardinality (≤3) + high-coverage (>0.95) + low-entropy (H_norm < 0.3)
- **PRESENCE_SIGNAL**: sparse attributes (coverage < 0.2)
- **NONE**: no discriminating power

**Type Refinement (Phase 3)** — `src/decoct/discovery/type_discovery.py` (211 lines). Sub-clusters within each type using bootstrap signal fingerprints. Anti-unification restricted to signal paths (prevents per-device IP differences from splitting types). Small-cluster merge guard prevents shattering:
- If ALL clusters below threshold → return original type unchanged
- Small clusters merge into closest large group (relaxed 2x threshold)
- Fallback: merge into largest group

Bootstrap loop iterates until entity→type assignments converge (max 5 iterations).

#### Phase 3.5: Composite Decomposition

`src/decoct/discovery/composite_decomp.py` (354 lines). Two strategies:

**Map-inner decomposition** (for `kind="map"`): Pools all map entries across entities → finds common keys (≥50% of entries) → picks most frequent value per key as template → stores per-entity per-entry deltas. Template IDs: `{type_id}.{path}.T{index}`.

**Trivial clustering** (for lists): One template per distinct value. v1 stub — no cross-value extraction.

Shadow map preserves original values for reconstruction validation. Re-profiling after decomposition updates entropy/cardinality/role stats.

#### Phase 4: Class Extraction

`src/decoct/compression/class_extractor.py` (245 lines). Greedy frequent-bundle selection:

1. **Base class**: A_BASE attrs + universal-value B attrs
2. **Residual B**: Build item vectors (frozenset of (path, VALUE_KEY) tuples) → enumerate bundles up to `max_class_bundle_size=3` → score: `gain = repeated_cost - templated_cost` → greedy selection of highest-gain bundle → assign covered entities → repeat
3. Unassigned entities → `_base_only` class

Class names auto-generated from distinguishing attribute paths. Output: `ClassHierarchy` (base_class, classes, subclasses).

#### Phase 5: Delta Compression

`src/decoct/compression/delta.py` (281 lines). For each primary class:
1. Build parent template (base + class own_attrs)
2. Compute restricted deltas per entity
3. Build item vectors from deltas → enumerate frequent bundles → score/select → create SubclassDefs
4. Max inheritance depth: 2 (base → class → subclass)
5. ABSENT deletions never become subclass own_attrs in v1

#### Phase 6: Normalisation

`src/decoct/compression/normalisation.py` (144 lines). Builds `TierC`:
- **Phone book** (PHONE_BOOK): scalar-like, full coverage → dense columnar table
- **Instance attrs** (INSTANCE_ATTRS): sparse, complex, composite_template_ref → per-entity key-value
- Class/subclass assignments, relationship store, overrides, composite deltas, foreign keys (v1 stub)

#### Phase 7: Reconstruction Validation

`src/decoct/reconstruction/validator.py` (263 lines). **The gate test** — pipeline raises `ReconstructionError` if any mismatch.

8 structural invariants (no multi-class, exact coverage, subclass containment, max depth 2, valid override owners, rectangular phone book, no path duplication).

Per-entity fidelity: reconstitute from Tier B + C using 7-layer precedence chain (base → class → subclass → overrides → B-template expansion → instance_attrs → phone book). Compare every attribute with `CANONICAL_EQUAL`. Compare against shadow map for decomposed composites.

#### Phase 8: Assembly

`src/decoct/assembly/tier_builder.py` (274 lines). Builds three-tier YAML:
- **Tier A** (`tier_a.yaml`): types (counts, file refs), topology (inter-type connectivity), assertions (base_only_ratio)
- **Tier B** (`{type}_classes.yaml`): meta, base_class, classes, subclasses, composite_templates
- **Tier C** (`{type}_instances.yaml`): class_assignments (with ID range compression), instance_data phone book, instance_attrs, relationship_store, overrides, b_composite_deltas

### 2.4 Configuration

`src/decoct/core/config.py` — `EntityGraphConfig` with all thresholds:

| Parameter | Default | Phase | Effect |
|-----------|---------|-------|--------|
| `composite_decompose_threshold` | 5 | 3.5 | Min cardinality to trigger decomposition |
| `min_composite_template_members` | 2 | 3.5 | Min entities a template must cover |
| `min_class_support` | 3 | 4 | Min entities for a class |
| `max_class_bundle_size` | 3 | 4, 5 | Max attrs in a bundle |
| `min_subclass_size` | 3 | 5 | Min entities for subclass promotion |
| `max_anti_unify_variables` | 3 | 3 | Max variables before types differ |
| `small_group_floor` | 8 | 2b | Stricter C-role threshold below this |
| `min_refinement_cluster_size` | 3 | 3 | Small clusters merged into larger ones |
| `unhinted_jaccard_threshold` | 0.4 | 2a | Jaccard threshold for unhinted grouping |
| `max_bootstrap_iterations` | 5 | 2+3 | Max refinement loops |

### 2.5 Three-Tier Output Format

**Tier A** — Fleet overview. Read first. Shows entity types, counts, class/subclass counts, topology (which types connect), quality assertions.

**Tier B** — Per-type class hierarchy. Base class (universal constants), primary classes (shared subgroup attrs), subclasses (further refinements), composite templates.

**Tier C** — Per-entity differences. Class assignments (with ID range compression `APE-R1-01..APE-R1-20`), phone book (dense scalar table), instance_attrs (sparse/complex), relationship_store, overrides (per-entity B-layer deltas).

**Reconstruction algorithm:**
1. Start with base_class from Tier B
2. Add primary class own_attrs
3. Add subclass own_attrs (if any)
4. Apply overrides (ABSENT = remove path)
5. Expand B-layer composite templates + deltas
6. Add instance_attrs + expand template refs
7. Add phone book values

### 2.6 Statistics and Evaluation

**Stats module** (`src/decoct/entity_graph_stats.py`, 388 lines): `decoct entity-graph stats -i <input> -o <output>`. Per-tier file/byte/token counts, compression ratios, per-type structural metrics.

**QA harness** (`src/decoct/qa/`): 6 question categories (SINGLE_VALUE, MULTI_ENTITY, EXISTENCE, COMPARISON, COUNT, ORDERING). Deterministic generation from parsed configs. LLM evaluation comparing raw vs compressed accuracy. Fuzzy answer matching.

### 2.7 Test Architecture

| Test File | Coverage | Count |
|-----------|----------|-------|
| `test_core/test_entity_graph.py` | EntityGraph CRUD, relationship dedup | 8 |
| `test_analysis.py` | Entropy, roles, Tier C storage | 11 |
| `test_discovery.py` | Type seeding, Jaccard, anti-unification, merge guard | 12 |
| `test_class_extractor.py` | Base class, universal B, greedy bundles | 7 |
| `test_reconstruction.py` | 6-layer precedence, ABSENT, template expansion | 9 |
| `test_entity_graph_e2e.py` | **THE gate test** — 86 IOS-XR configs, 0 mismatches | 10+ |
| `test_adapters/` | 7 files covering all three adapters | varies |
| `test_entity_graph_stats.py` | Stats computation, formatting, CLI | 20 |

### 2.8 File Reference

```
src/decoct/
  core/
    types.py              189 lines
    entity_graph.py        76 lines
    config.py              39 lines
    canonical.py           78 lines
    composite_value.py     48 lines
  adapters/
    base.py                31 lines
    iosxr.py              563 lines
    hybrid_infra.py       364 lines
    entra_intune.py       343 lines
  analysis/
    entropy.py             39 lines
    profiler.py           101 lines
    tier_classifier.py     75 lines
  discovery/
    type_seeding.py        79 lines
    type_discovery.py     211 lines
    anti_unification.py    70 lines
    bootstrap.py           64 lines
    composite_decomp.py   354 lines
  compression/
    class_extractor.py    245 lines
    delta.py              281 lines
    normalisation.py      144 lines
    phone_book.py          23 lines
    inversion.py           23 lines
  assembly/
    tier_builder.py       274 lines
  reconstruction/
    reconstitute.py       228 lines
    validator.py          263 lines
  entity_pipeline.py      146 lines
  entity_graph_stats.py   388 lines
  qa/
    questions.py           — 6 question categories
    evaluate.py            — LLM evaluation harness
```

---

## 3. Key Decisions and Lessons Learned

### 3.1 CompositeValue Wrapping
Without it, per-device structures (BGP neighbors, EVPN EVIs, Docker services) would appear as unique flat paths, creating N singleton types instead of 1 type with N entities. CompositeValue keeps these atomic.

### 3.2 Anti-Unification Restricted to Signal Paths
Type refinement originally compared ALL attributes. Per-device values (IPs, hostnames) caused every entity pair to exceed `max_anti_unify_variables=3`, producing 86 singleton types. Restricting to bootstrap signal paths (VALUE_SIGNAL + PRESENCE_SIGNAL) fixed this.

### 3.3 Jaccard Clustering over Exact Fingerprints
Exact attribute-fingerprint grouping over-split types when key sets had minor variations. Jaccard clustering (threshold 0.4) tolerates variations while separating structurally different entities. Combined with small-cluster merge guard.

### 3.4 Homogeneous Map Detection
Dict-of-dicts with similar child key sets (Jaccard ≥ 0.5) stored as CompositeValue(map) instead of recursively flattened. Prevents per-entry paths from polluting attribute profiles.

### 3.5 Map-Inner Decomposition
For map composites: pool all entries across entities → extract common base template (most frequent value per common key) → store per-entity per-entry deltas. Achieves compression even when entities have different map entries.

### 3.6 Hybrid-Infra Compression Journey
- Start: -14% (output larger than input) — 69 singleton types from 100 entities
- Round 1 (Jaccard clustering + merge guard): → +16.7%
- Round 2 (stricter detection + map-inner decomposition): → +29-34%
- IOS-XR remains at 70-80% compression throughout

### 3.7 Ordering Preservation Concern
User raised ACL ordering as a critical semantic concern. CompositeValue with `kind="list"` preserves ordering. `CANONICAL_EQUAL` respects list order. ORDERING question category added to QA harness to validate LLM comprehension of order-dependent semantics.

---

## 4. Current State and Open Items

### What Works (as of 2026-03-10 20:15 UTC)
- Complete entity-graph pipeline with 8 phases
- Three adapters: IOS-XR (86 configs), Entra-Intune (88 resources), Hybrid-Infra (100 files)
- 100% reconstruction fidelity on all three corpora
- Statistics CLI with markdown/JSON output
- QA comprehension harness with 6 question categories
- 25 git commits pushed to main
- Comprehensive architecture documentation (`docs/entity-graph-architecture.md`, 767 lines)

### Git Commits (25 commits, all Mar 10)
```
af73908 Add core entity-graph data types, canonical forms, and graph storage
c161394 Add entity-graph analysis: entropy, profiling, and tier classification
9bebb80 Add entity-graph discovery: type seeding, bootstrap loop, composite decomposition
7a477ab Add entity-graph compression: class extraction, delta, normalisation
082a0ae Add entity-graph assembly and reconstruction validation
ba800b9 Add platform adapters: IOS-XR, Entra/Intune, Hybrid Infrastructure
56f7d7c Add entity-graph pipeline orchestrator
0f214e9 Add test fixtures for IOS-XR, Entra/Intune, and Hybrid Infra
c36df19 Add tests for core types, entity graph, canonical forms, and adapters
d32b0ba Add entity-graph pipeline tests: analysis through end-to-end validation
8e212dd Add entity-graph output samples and pipeline runner scripts
0c3799a Add benchmark harness and corpus-learned compression classes
a3d97d0 Add entity-graph compression statistics module
dc7e57e Add QA comprehension harness for entity-graph evaluation
702e2b2 Add entity-graph CLI group with stats, generate-questions, and evaluate
40d0e03 Add developer specs and entity-graph data manual
282c97f Add entity-graph evaluation guide and CLI reference updates
ffdd24e Add ORDERING question category and adapter-parameterized generation
b1fc24b Add tests for ORDERING questions and adapter parameter
f57b033 Add homogeneous map detection and inner map composite decomposition
8f045ec Replace fingerprint type seeding with Jaccard clustering and merge guard
e7a0114 Regenerate hybrid-infra output with map decomposition and Jaccard clustering
```

### v1 Stubs (Correct but Not Optimised)
| Function | v1 Behaviour | Future |
|----------|-------------|--------|
| List composite decomposition | 1 cluster per distinct value | Cross-value template extraction |
| `anti_unify()` | Path-by-path comparison | Deeper structural anti-unification |
| `token_estimate_*()` | `len(str) / 4` approximation | tiktoken cl100k_base |
| `detect_foreign_keys()` | Returns empty dict | FK detection from value overlap |

### Other Sessions (Non-Entity-Graph)
- **decoct.io website**: Stripped to minimal landing page, force-pushed as fresh repo
- **Clipboard image skill**: Set up `clipimg` as global Claude Code skill
- **Enable-infra**: Brief session, no significant changes
