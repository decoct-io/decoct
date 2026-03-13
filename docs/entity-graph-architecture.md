# Entity-Graph Pipeline — Architecture and Design

This document is the authoritative reference for the entity-graph compression pipeline. It supersedes the handoff document (`docs/dev/entity-graph-handoff.md`), the data manual (`docs/entity-graph-data-manual.md`), the evaluation guide (`docs/entity-graph-evaluation.md`), and the session summary (`docs/session-summary-2026-03-10.md`).

---

## 1. Purpose

The entity-graph pipeline compresses fleets of infrastructure configurations into a three-tier YAML representation that separates shared structure from per-entity differences. The compression is lossless — every entity can be reconstructed exactly from the output. The system typically achieves 70-80% token savings on homogeneous corpora (IOS-XR) and 29-34% on heterogeneous mixed-format corpora (hybrid-infra).

### 1.1 Origins

The entity-graph pipeline was motivated by a critical insight: recurring patterns in infrastructure configs (shared BGP configurations across routers, identical service definitions across environments) are analogous to repeated byte sequences that LZ77 discovers. Rather than relying on platform-specific schema rules, the pipeline discovers compression classes from corpus data itself using an **LZ77/Huffman-style general solution**.

An initial prototype (~250 lines) tested the concept: flatten documents, discover instance levels, mine frequent (path, value) pairs, co-occurrence clustering, greedy score/select. This platform-agnostic approach proved viable and evolved into the current eight-phase pipeline.

---

## 1.2 Getting Started

```bash
# Install with dev dependencies (sufficient for all pipeline work)
pip install -e ".[dev]"

# Also install LLM deps if working on QA evaluation or LLM-assisted features
pip install -e ".[dev,llm]"

# Run all entity-graph tests
pytest -k entity -v

# Run only the gate test (86 IOS-XR configs, must produce 0 reconstruction mismatches)
pytest tests/test_entity_graph_e2e.py -v

# Regenerate output from fixtures
python scripts/run_pipeline.py           # IOS-XR → output/iosxr/
python scripts/run_hybrid_infra.py       # Hybrid → output/hybrid-infra/
python scripts/run_entra_intune.py       # Entra → output/entra-intune/

# CLI commands
decoct entity-graph stats -i tests/fixtures/iosxr/configs -o output/iosxr --format markdown
decoct entity-graph generate-questions -i tests/fixtures/iosxr/configs -o output/iosxr
decoct entity-graph evaluate -i tests/fixtures/iosxr/configs -o output/iosxr
```

### Test Fixtures and Output

| Directory | Contents | Status |
|---|---|---|
| `tests/fixtures/iosxr/configs/` | 86 IOS-XR `.cfg` files (APE-R1-01 through Services-PE-08) | Checked in, generated from `tests/fixtures/iosxr/generate/` |
| `tests/fixtures/entra-intune/resources/` | 88 Entra/Intune `.json` files (Graph API format) | Checked in |
| `tests/fixtures/hybrid-infra/` | 100 mixed files (YAML/JSON/INI) across 8+ platforms | Checked in, generated from `tests/fixtures/hybrid-infra/generate/` |
| `output/iosxr/` | Tier A/B/C YAML output from IOS-XR corpus | Checked in (sample output, regenerated via `scripts/run_pipeline.py`) |
| `output/hybrid-infra/` | Tier A/B/C output from hybrid-infra corpus | Checked in |
| `output/entra-intune/` | Tier A/B/C output from Entra corpus | Checked in |

### Related Documentation

| Document | Purpose | Relationship to this doc |
|---|---|---|
| `docs/entity-graph-data-manual.md` | **Reader manual** — how to interpret and consume the three-tier output | Complementary: this doc describes how the pipeline works; the data manual describes how to read its output |
| `docs/entity-graph-evaluation.md` | QA harness usage and evaluation methodology | Content absorbed into Section 6; retained for standalone reference |
| `docs/dev/entity-graph-handoff.md` | Development history — bug-fix journal, implementation notes | Historical context; useful for understanding why certain decisions were made |
| `docs/session-summary-2026-03-10.md` | Session-by-session development log | Historical; captured in condensed form in Section 10 |

---

## 2. Core Data Model

All types live in `src/decoct/core/types.py`.

### 2.1 Entity

```python
@dataclass
class Entity:
    id: str
    attributes: dict[str, Attribute]
    schema_type_hint: str | None = None
    discovered_type: str | None = None
```

An entity is the atomic unit of the graph. One input file produces one entity. The `id` comes from the adapter (hostname for IOS-XR, filename stem for hybrid-infra, `displayName` for Entra-Intune). `schema_type_hint` is the adapter's best guess at entity type before the bootstrap loop runs. `discovered_type` is the final type assignment after bootstrap convergence.

### 2.2 Attribute

```python
@dataclass
class Attribute:
    path: str          # dot-separated key path, e.g. "router.isis.CORE.is-type"
    value: Any         # scalar string/number/bool, or CompositeValue
    type: str          # 'string', 'number', 'boolean', 'null', 'enum', 'list', 'map', 'composite_template_ref'
    source: str = ""   # originating entity ID
```

Attributes are the properties of an entity. Paths use dot-separated notation derived from the input format. The `type` field tracks what kind of value is stored. After composite decomposition, some attributes have type `composite_template_ref` — their `value` is a template ID string pointing into the template index.

### 2.3 CompositeValue

```python
@dataclass
class CompositeValue:
    data: Any          # list or dict
    kind: str = "map"  # "map" or "list"
```

Wraps non-scalar structures that should be treated as atomic units rather than flattened into separate dotted paths. Without composite wrapping, per-device structures like `evpn.evi.10000.*` would appear as unique flat attributes, creating singleton types instead of groupable entities.

Examples: BGP neighbor blocks, EVPN EVI blocks, bridge-domain blocks, route-policy bodies (IOS-XR); Ansible task lists, Prometheus scrape configs (hybrid-infra); OAuth2 permission scopes, policy assignments (Entra-Intune).

### 2.4 Sentinels

Two singleton sentinels distinguish absence from null:

- **`ABSENT`** — a path exists in the class template but is explicitly removed for a specific entity. Used in override deltas.
- **`MISSING`** — a path was never present. Used during reconstruction validation to distinguish "not in entity" from "entity has null."

### 2.5 EntityGraph

```python
class EntityGraph:
    _entities: dict[str, Entity]
    _relationships: set[tuple[str, str, str]]  # (source_id, label, target_id)
```

`src/decoct/core/entity_graph.py` (76 lines). The in-memory graph stores entities indexed by ID and relationships as a set of (source, label, target) triples. Relationship storage is idempotent — calling `add_relationship()` with the same triple twice has no effect. All accessor methods return sorted results for deterministic output.

Key operations:
- `add_entity(entity)` / `get_entity(entity_id)` — CRUD
- `add_relationship(source_id, label, target_id)` — idempotent triple insertion
- `relationships_from(source_id)` → `list[tuple[str, str]]` — all (label, target) pairs for a source
- `entities_of_type(type_id)` — filter by discovered type
- `unique_relationship_labels_from_entities(entities)` — collect distinct edge labels

### 2.6 Canonical Functions

`src/decoct/core/canonical.py`. Five functions provide authoritative equality and hashing, referenced throughout the pipeline:

| Function | Purpose |
|---|---|
| `CANONICAL_KEY(value) → str` | JSON-serialized equality key. Normalizes floats to ints where lossless, sorts dict keys, unwraps CompositeValue. |
| `CANONICAL_EQUAL(a, b) → bool` | `CANONICAL_KEY(a) == CANONICAL_KEY(b)` |
| `VALUE_KEY(value) → str` | Alias for CANONICAL_KEY |
| `ITEM_KEY(path, value) → tuple[str, str]` | Combines path and canonical value key — used as bundle item keys in class extraction |
| `IS_SCALAR_LIKE(type) → bool` | True for string/number/boolean/null/enum. `composite_template_ref` explicitly excluded. |

These names are UPPER_CASE to match the spec notation. Suppressed via ruff per-file overrides.

---

## 3. Pipeline Architecture

The pipeline is orchestrated by `run_entity_graph_pipeline()` in `src/decoct/entity_pipeline.py`. It chains ten phases:

```
Input files (.cfg, .yaml, .json, .ini, .conf)
  │
  ▼
[Phase 0] Secrets Masking ─── pre-flatten document masking + post-flatten attribute masking
  │
  ▼
[Phase 1] Canonicalise ─── adapter.parse() + adapter.extract_entities() → EntityGraph
  │
  ▼
[Phase 1.5] Source Fidelity ─── strict bidirectional token-sequence validation
  │
  ▼
[Phase 2+3] Bootstrap Loop ─── seed types → profile → refine → converge
  │
  ▼
[Phase 3.5] Composite Decomposition ─── shadow map + template extraction
  │
  ▼
[Phase 4+5] Compression Engine ─── pluggable engine (default: greedy-bundle)
  │                               class extraction + delta compression
  │
  ▼
[Phase 6] Normalisation ─── build Tier C (phone book + instance_attrs)
  │
  ▼
[Phase 7] Reconstruction Validation ─── 100% fidelity gate test
  │
  ▼
[Phase 8] Assembly ─── emit Tier A / B / C YAML
```

Phase 0 and Phase 1 are interleaved per-file: for each source file, the pipeline masks secrets in the parsed document (Phase 0a), collects source leaves, then extracts entities (Phase 1), then runs post-flatten attribute masking on all entities and source leaves (Phase 0b/0b'). Phase 1.5 runs strict bidirectional fidelity validation on the masked source leaves vs entity attributes. See §3.0 and §3.1.5 for details.

Each phase is a separate module. The pipeline returns `EntityGraphResult`:

```python
@dataclass
class EntityGraphResult:
    graph: EntityGraph
    type_map: dict[str, list[Entity]]
    hierarchies: dict[str, ClassHierarchy]
    tier_c_files: dict[str, TierC]
    template_index: dict[str, CompositeTemplate]
    tier_a: dict[str, Any]
    tier_b_files: dict[str, dict[str, Any]]
    tier_c_yaml: dict[str, dict[str, Any]]
    original_composite_values: dict[tuple[str, str], Any]
    secrets_audit: list[AuditEntry]     # (path, detection_method) — never stores values
    source_leaves: dict[str, list[tuple[str, str]]]  # per-entity source leaves (for fidelity validation)
```

### 3.0 Phase 0: Secrets Masking

**Module:** `src/decoct/secrets/`

Phase 0 is the security boundary — it MUST complete before any data reaches downstream phases or LLM review. It runs in two sub-phases:

**Phase 0a — Pre-flatten document masking:** For adapters whose `parse()` returns a dict-like structure (hybrid-infra returns `(CommentedMap, Path)`, entra-intune returns `dict`), `mask_document()` walks the raw parsed tree and redacts secrets in-place before `extract_entities()` flattens them into attributes. IOS-XR returns `IosxrConfigTree` (not a dict) — it skips pre-flatten and relies entirely on post-flatten masking.

**Phase 0b — Post-flatten attribute masking:** After all entities are extracted, `mask_entity_attributes()` scans every entity's attributes. This catches secrets that only become apparent at the dotted-path level (e.g., `tacacs-server.key`) and secrets inside CompositeValue internals.

**Phase 0b' — Post-flatten source leaf masking:** After Phase 0b, `_mask_leaf_values()` applies the same `detect_secret()` logic to source leaf values, prefixing entity_id to paths for pattern matching consistency. This ensures source leaves and entity attributes have identical `[REDACTED]` values for strict fidelity validation (Phase 1.5).

Both sub-phases use the same detection engine with four-stage detection (first match wins):

1. **Path pattern** — dotted path matches a known secret path (e.g., `*.password`, `*.api_key`)
2. **False-positive filter** — skip infrastructure data (UUIDs, IPs, MACs, file paths, template variables, pure numerics)
3. **Regex** — value matches known secret formats (16 patterns: AWS keys, private key blocks, JWTs, Cisco type 7/8/9, etc.)
4. **Charset-aware entropy** — separate thresholds for base64 (4.5) and hex (3.0) candidates, with all-digit discount to avoid false-positives on AS numbers, VLANs, and ports

The detection logic lives in `src/decoct/secrets/` with a four-stage detection engine shared across all adapters.

#### Adapter Secret Configuration

Adapters declare their own secret patterns by overriding two `BaseAdapter` methods:

```python
def secret_paths(self) -> list[str]: ...              # extra path denylist
def secret_value_patterns(self) -> list[...] | None: ... # extra value-level regexes
```

The pipeline merges these with the global `DEFAULT_SECRET_PATHS` — no adapter type-switching in the orchestrator. Custom adapters bring their own patterns without modifying pipeline code.

| Adapter | Extra secret paths | Value patterns |
|---|---|---|
| IOS-XR | TACACS/RADIUS keys, SNMP communities, network device paths | `key 7 ...`, `secret [057] ...`, `community ... RO/RW`, `key-string ...` |
| Hybrid-Infra | Network device paths | None |
| Entra-Intune | `*.clientSecret`, `*.secretText` | None |

#### `[REDACTED]` Flow

Redacted values become regular `"[REDACTED]"` strings that flow through compression normally. If all entities share a redacted path, it appears in `base_class`. If per-entity, it appears in Tier C. Reconstruction validation sees `[REDACTED]` on both sides and passes.

#### Audit Trail

Every redaction produces an `AuditEntry(path, detection_method)`. Actual secret values are NEVER logged, printed, or stored. The audit is returned on `EntityGraphResult.secrets_audit`.

### 3.1 Phase 1: Canonicalise

**Module:** Adapter-specific (`src/decoct/adapters/`)

Each adapter implements `BaseAdapter`:

```python
class BaseAdapter(ABC):
    def parse(self, source: str) -> Any: ...
    def extract_entities(self, parsed: Any, graph: EntityGraph) -> None: ...
    def source_type(self) -> str: ...
    def secret_paths(self) -> list[str]: ...                            # default: []
    def secret_value_patterns(self) -> list[tuple[str, Pattern]] | None: ...  # default: None
```

One file → one entity. The adapter handles:
- Parsing the input format into an internal representation
- Flattening nested structures into dot-separated attribute paths
- Identifying composite values that should remain atomic
- Setting `schema_type_hint` for coarse type seeding
- Extracting inter-entity relationships

#### IOS-XR Adapter (563 lines)

`src/decoct/adapters/iosxr.py`

Parses IOS-XR `.cfg` files using a custom indentation-based parser (1-space indent per level, `!` as block terminator). Builds a `ConfigNode` tree, then flattens to dotted paths via `flatten_config_tree()`.

**Section keywords** consume arguments to form path segments. `router isis CORE` becomes `router.isis.CORE`. `address-family ipv4 unicast` becomes `address-family.ipv4-unicast`. The keyword map (`SECTION_KEYWORDS`) handles both single-word and two-word sections (`bridge group`).

**Composite value collection** (`_collect_composite_values()`) identifies: BGP neighbor blocks → `CompositeValue(map)`, EVPN EVI blocks → `CompositeValue(map)`, bridge-group/bridge-domain blocks → `CompositeValue(map)`, route-policy bodies → `CompositeValue(list)`.

**Subsumed prefix filtering** prevents double-counting. If a composite covers `evpn.evis`, all flat paths under `evpn.evi.*` are excluded from the entity's attributes.

**Type hints** from hostname prefixes: `P-CORE-` → `iosxr-p-core`, `RR-` → `iosxr-rr`, `APE-` → `iosxr-access-pe`, etc.

**Relationship extraction** from interface descriptions (`TO-{hostname}` → `p2p_link`) and BGP neighbor descriptions (hostname pattern → `bgp_peer`).

#### Hybrid-Infra Adapter (364 lines)

`src/decoct/adapters/hybrid_infra.py`

Handles YAML, JSON, and INI/conf files. Uses the existing `load_input()` + `detect_format()` from `formats.py` with three fallback parsers:
1. Standard `load_input()` (ruamel.yaml / json / configparser)
2. `_parse_ini_tolerant()` — handles duplicate keys by accumulating into comma-separated strings
3. `_parse_space_separated()` — sshd-style `Key Value` configs with no `=`

**Document flattening** (`flatten_doc()`) handles: nested dicts → dotted paths, scalar arrays → comma-separated strings, arrays of objects → `CompositeValue(list)`, root lists → unwrap single-element or composite.

**Homogeneous map detection** (`_is_homogeneous_map()`) identifies dict-of-dicts where children have structurally similar keys (Jaccard similarity >= 0.5 on key sets). These are stored as `CompositeValue(map)` instead of being recursively flattened — this prevents per-entry key paths from shattering type discovery.

**Type hints** from content detection: `docker-compose` (has `services` with nested mappings + `image` keys), `ansible-playbook` (root list with `hosts` + `tasks`/`roles`), `cloud-init`, `traefik`, `prometheus`. Undetected files get `None` hint and are grouped by Jaccard clustering.

No relationships extracted.

#### Entra-Intune Adapter (343 lines)

`src/decoct/adapters/entra_intune.py`

Parses Microsoft Graph API JSON exports. Entity ID = `displayName`. Type hints from `@odata.type` field mapped through `ODATA_TYPE_MAP` (13 OData types → 8 logical types).

Metadata fields (`@odata.type`, `id`, timestamps) stripped before flattening. Known array fields (`assignments`, `apps`, `oauth2PermissionScopes`, etc.) stored as `CompositeValue`.

**Relationship extraction** requires a two-pass approach: first parse all entities, then `extract_relationships()` builds a UUID→displayName lookup and resolves `group_ref` (CA policy group references), `assignment_target` (Intune assignment targets), and `tenant_ref` (cross-tenant access) relationships.

### 3.1.5 Phase 1.5: Strict Source Fidelity Validation

**Module:** `src/decoct/reconstruction/strict_fidelity.py`

Phase 1.5 proves that the EntityGraph captures ALL source data and ONLY source data — a bidirectional data fidelity check with no heuristics. It runs after canonicalisation (Phase 1) and secrets masking (Phase 0b/0b'), before the bootstrap loop changes anything.

#### Three-Layer Validation Chain

```
Raw Text ──L1──→ Parsed Tree ──L2 (strict)──→ EntityGraph ──L3──→ Tier B+C
           │                    │                              │
     section counts       token-sequence                 reconstruction
      must match          BIJECTION                       BIJECTION
                     (sorted tokens ≡)              (CANONICAL_EQUAL ≡)
```

- **Layer 1** (`parser_validation.py`): Raw text section counts match parsed tree node counts (IOS-XR only)
- **Layer 2** (`strict_fidelity.py`): Source leaf tokens == entity leaf tokens (bidirectional, no false positives)
- **Layer 3** (`validator.py`): Entity survives compression round-trip (the gate test, Phase 7)

By transitivity: every data point from raw source survives into compressed output AND nothing is fabricated.

#### Algorithm: Token-Sequence Normalisation

The adapter's discrimination transforms move tokens between path and value fields, but the underlying **token sequence** is preserved:

```
Source leaf:  ("ntp.server",           "10.0.0.1 prefer")
Entity attr:  ("ntp.server.10.0.0.1", "prefer")

Both normalise to: ("ntp", "server", "10", "0", "0", "1", "prefer")
```

The algorithm:

1. **Tokenise path** — replace `[]` with `.`, split on `.`, apply segment aliases (`evis`→`evi`, `neighbors`→`neighbor`, `bridge-groups`→`bridge-group`, `bridge-domains`→`bridge-domain`)
2. **Tokenise value** — strip Python list repr chars (`[]'"`), replace `.` and `,` with space, split. `[REDACTED]` is preserved as a single token. Boolean `"true"` is elided (discrimination artifact)
3. **Concatenate** — `path_tokens + value_tokens` → canonical token tuple
4. **Sort** both source and entity token lists
5. **Merge-join** — walk both sorted lists with two pointers. O(n log n) total.
   - Token in source but not entity → `missing_from_entity`
   - Token in entity but not source → `fabricated_in_entity`

**Entity leaf expansion:** Before normalisation, `expand_entity_leaves()` recursively flattens `CompositeValue` objects — list composites expand to `(base[i], item)`, map composites expand to `(base.key.attr, value)`. Internal paths (`_uuid`) are excluded.

**Masking consistency:** Source leaves are collected *after* pre-flatten `mask_document()` and *before* `extract_entities()`. Post-flatten masking (`_mask_leaf_values()`) applies the same `detect_secret()` logic to source leaf values, prefixing entity_id to paths for pattern matching consistency with `mask_entity_attributes()`. Both sides then have identical `[REDACTED]` values — strict comparison works without special cases.

#### Configuration

Controlled by `EntityGraphConfig.source_fidelity_mode`:

| Mode | Behaviour |
|------|-----------|
| `"error"` | Raises `StrictFidelityError` on any mismatch (default for production) |
| `"warn"` | Logs mismatches but continues (used for adapters with known structural issues) |
| `"skip"` | Bypasses validation entirely |

#### Adapter Fidelity Status

| Adapter | Mode | Mismatches | Status |
|---------|------|------------|--------|
| **Hybrid-Infra** (JSON/YAML/INI) | `error` | **0** | Clean bidirectional fidelity |
| **Entra-Intune** (JSON) | `warn` | ~173 | Nested `@odata.type` fields in arrays skipped by adapter but present in source leaves |
| **IOS-XR** (.cfg) | `warn` | ~1502 | Multiple structural issues (see §11 Open Items) |

The hybrid-infra adapter proves that the validation framework works correctly for structured formats. The IOS-XR and Entra-Intune mismatches are genuine adapter issues that the previous fuzzy Layer 2 check was hiding — see §11 for details.

### 3.2 Phase 2+3: Bootstrap Loop

**Modules:** `src/decoct/discovery/bootstrap.py`, `type_seeding.py`, `type_discovery.py`, `anti_unification.py`

The bootstrap loop iteratively refines type assignments until convergence (or `max_bootstrap_iterations` reached, default 5).

#### Type Seeding (Phase 2a)

`seed_types_from_hints()` in `type_seeding.py`.

Entities with `schema_type_hint` are grouped by hint. Unhinted entities are clustered using **greedy agglomerative Jaccard clustering**: entities sorted by attribute count (descending) to seed clusters with the most representative first, then each entity is added to the cluster with highest Jaccard similarity of attribute key sets (if above `unhinted_jaccard_threshold`, default 0.4), or creates a new cluster. Centroid is the union of member key sets.

This replaced an earlier exact-fingerprint approach that over-split types when key sets had minor variations.

#### Attribute Profiling (Phase 2b)

`profile_attributes()` in `src/decoct/analysis/profiler.py`.

For each attribute path across all entities of a type, computes:

| Metric | Meaning |
|---|---|
| `cardinality` | Number of distinct values (by `VALUE_KEY`) |
| `entropy` / `entropy_norm` | Shannon entropy in bits / normalized to [0,1] |
| `coverage` | Fraction of entities that have this path |
| `value_length_mean/var` | Token-estimated value length statistics |
| `final_role` | A_BASE, B, or C (where this attribute is emitted) |
| `bootstrap_role` | VALUE_SIGNAL, PRESENCE_SIGNAL, or NONE |

**Final role classification** (`classify_final_role()` in `tier_classifier.py`):
- **A_BASE**: `coverage == 1.0` and `cardinality == 1` (universal constant)
- **C**: high entropy (`H_norm > 0.8`) or cardinality > half the entities (for groups above `small_group_floor`). Below the floor, requires `H_norm > 0.9` or `cardinality >= n_entities` to prevent over-classification of small groups.
- **B**: everything else (class-compressible)

**Bootstrap signal classification** (`classify_bootstrap_role()`):
- **VALUE_SIGNAL**: A_BASE attributes, or low-cardinality (≤3), high-coverage (>0.95), low-entropy (`H_norm < 0.3`) attributes
- **PRESENCE_SIGNAL**: sparse attributes (`coverage < 0.2`)
- **NONE**: no discriminating power

#### Type Refinement (Phase 3)

`refine_types()` in `type_discovery.py`.

Sub-clusters entities within each type using **bootstrap signal fingerprints**:

1. Collect signal paths (attributes with VALUE_SIGNAL or PRESENCE_SIGNAL bootstrap roles)
2. Collect relationship labels present in the entity group
3. Build per-entity fingerprints: tuples of `(path, canonical_value)` for VALUE_SIGNAL paths, `(path, "__EXISTS__")` for PRESENCE_SIGNAL paths, `("REL::label", "__EXISTS__")` for relationship labels
4. Group entities with identical fingerprints into sub-clusters
5. Merge clusters using **anti-unification** restricted to signal paths: compare representative entities pairwise, count Variable positions, merge if average variable count ≤ `max_anti_unify_variables` (default 3)

**Anti-unification** (`anti_unify()` in `anti_unification.py`): path-by-path comparison of two entities. Matching canonical values → common, mismatches → Variable sentinel. When `restrict_paths` is provided, only those paths are compared — this prevents instance-level differences (like per-device IPs) from being counted as type-level structural variables.

**Small-cluster merge guard** (`_merge_small_clusters()`): prevents type shattering. Clusters below `min_refinement_cluster_size` (default 3) are merged into the closest large group (by relaxed anti-unification, 2x threshold). If ALL clusters are below the threshold (complete shatter), the original type is returned unchanged. Fallback: merge into the largest group.

**Type naming** (`_derive_type_name()`): uses the `schema_type_hint` from the first entity in the group if available, falling back to `{base_name}_{ordinal}`.

#### Convergence

The bootstrap loop tracks entity→type assignments. If the assignment map is unchanged between iterations, the loop terminates. Final re-profiling produces the definitive `profiles` dict used by all downstream phases.

### 3.3 Phase 3.5: Composite Decomposition

**Module:** `src/decoct/discovery/composite_decomp.py`

Replaces high-cardinality composite values with template references plus per-entity deltas.

Two strategies:

**Map-inner decomposition** (for `CompositeValue(kind="map")`): Pools all map entries across entities, finds common keys (present in ≥50% of entries), picks the most frequent value per common key as the template, computes per-entity per-entry deltas (added/changed keys and removed keys as `None`). The template is stored in the template index, entity attributes are replaced with `composite_template_ref` pointing to the template ID, and deltas are stored in `composite_deltas`.

**Trivial clustering** (v1 stub for list composites): one cluster per distinct value, each becomes a template. No cross-value template extraction. Entities with matching values get a `composite_template_ref`; entities with no matching template keep their original value.

Before decomposition, original composite values are saved in a **shadow map** (`original_composite_values`) for reconstruction validation.

After decomposition, affected attributes are **re-profiled** with fresh entropy/cardinality/role statistics computed on the template ref values.

Template IDs follow the format `{type_id}.{path}.T{index}`.

### 3.4 Phase 4+5: Compression Engine

**Modules:** `src/decoct/compression/engine.py`, `src/decoct/compression/greedy_bundle.py`

Phase 4 (class extraction) and Phase 5 (delta compression) are executed by a pluggable `CompressionEngine`. The engine is selected via `EntityGraphConfig.compression_engine` (default: `"greedy-bundle"`) or the `--compression-engine` CLI flag on the `entity-graph` command group.

```python
from decoct.compression import CompressionEngine, get_engine, registry

class CompressionEngine(ABC):
    @abstractmethod
    def compress(self, type_map, graph, profiles, config) -> dict[str, ClassHierarchy]: ...
    @abstractmethod
    def name(self) -> str: ...
```

The `_EngineRegistry` manages registration and lookup:
- `registry.register(EngineClass)` — registers an engine (usable as a decorator); raises `ValueError` on duplicate names
- `registry.get(name)` — returns a new instance; raises `KeyError` with available names on miss
- `registry.available()` — sorted list of registered engine names
- `get_engine(name)` — convenience wrapper around `registry.get()`

Custom engines subclass `CompressionEngine` and register with the global `registry`:

```python
from decoct.compression.engine import CompressionEngine, registry

@registry.register
class MyEngine(CompressionEngine):
    def compress(self, type_map, graph, profiles, config):
        ...
    def name(self):
        return "my-engine"
```

The pipeline dispatches via:

```python
engine = get_engine(config.compression_engine)
hierarchies = engine.compress(type_map, graph, profiles, config)
```

#### Default Engine: Greedy Bundle

**Module:** `src/decoct/compression/greedy_bundle.py`

`GreedyBundleEngine` wraps the existing `extract_classes()` (Phase 4) and `delta_compress()` (Phase 5) functions. It is auto-registered as `"greedy-bundle"` on import.

#### Phase 4: Class Extraction

**Module:** `src/decoct/compression/class_extractor.py` (245 lines)

Extracts a `ClassHierarchy` per type using greedy frequent-bundle selection.

#### Base Class Construction

1. **A_BASE attributes**: all attributes with `final_role == A_BASE` go into the base class with their (universal) value.
2. **Universal B promotion**: B-role attributes where all entities have the same canonical value are promoted into the base class.

#### Residual B Processing

For remaining B-role paths:

1. **Build item vectors**: each entity gets a frozenset of `(path, VALUE_KEY(value))` tuples for its residual B attributes
2. **Generate bundle candidates**: enumerate all subsets up to `max_class_bundle_size` (default 3) of each entity's items, count support (number of entities containing that subset)
3. **Score bundles**: `gain = repeated_cost - templated_cost` where `repeated_cost = support * token_estimate(attrs)` and `templated_cost = token_estimate(class_def) + support * token_cost_class_ref`
4. **Greedy selection**: pick the highest-gain candidate, assign its covered entities, remove them from the unassigned pool, repeat until no positive-gain candidates remain
5. **Catchall**: unassigned entities go to `_base_only` class

#### Class Naming

`_derive_class_name()`: auto-generated from distinguishing attribute paths and values. Takes the last segment of the first two attribute paths, appends short string values. Sanitized to alphanumeric + underscore, max 50 chars. Collision resolution with ordinal suffix.

#### Output

```python
@dataclass
class ClassHierarchy:
    base_class: BaseClass          # attrs shared by all entities of this type
    classes: dict[str, ClassDef]   # primary classes (inherits: "base")
    subclasses: dict[str, SubclassDef]  # subclasses (populated by Phase 5)
```

#### Phase 5: Delta Compression

**Module:** `src/decoct/compression/delta.py` (281 lines)

Compresses residual B-layer differences within each primary class by promoting shared concrete additions into subclasses.

For each primary class:

1. **Build parent template**: merge base_class attrs + class own_attrs, restricted to eligible (B-role) paths
2. **Compute restricted deltas**: for each entity in the class, compute the difference between entity's B-values and the parent template. Only considers eligible paths. Differences → `delta[path] = entity_value`. Template paths absent in entity → `delta[path] = ABSENT`.
3. **Build item vectors from deltas**: each entity's delta items become a frozenset (excluding ABSENT values — deletions never become subclass own_attrs in v1)
4. **Generate subclass candidates**: enumerate frequent bundles from delta items, compute gain: `inline_cost - templated_cost` where `inline_cost = sum(override_cost per entity)` and `templated_cost = subclass_def_cost + sum(residual_override_cost)`
5. **Greedy selection**: pick highest-gain candidate, create `SubclassDef` with the shared delta as `own_attrs`, per-entity residuals as `overrides`
6. **Parent overrides**: entities not lifted into any subclass retain their raw deltas as parent-level overrides

Maximum inheritance depth is fixed at 2: base → class → subclass. Subclasses of subclasses are not permitted.

### 3.6 Phase 6: Normalisation

**Module:** `src/decoct/compression/normalisation.py` (144 lines)

Builds the complete `TierC` data structure for each type.

#### Tier C Storage Split

`select_tier_c_storage()` in `tier_classifier.py` routes C-role attributes:
- **PHONE_BOOK**: scalar-like type (`IS_SCALAR_LIKE`), full coverage (`coverage == 1.0`) → dense columnar storage
- **INSTANCE_ATTRS**: everything else (sparse, complex, composite_template_ref) → per-entity key-value storage
- `composite_template_ref` attributes are always INSTANCE_ATTRS, regardless of coverage/cardinality

#### Phone Book

`build_phone_book_dense()` in `phone_book.py`: builds a rectangular table with `schema` (column headers = attribute paths) and `records` (entity_id → positional value list). Every entity must have a value for every schema path.

#### Other TierC Sections

| Section | Content |
|---|---|
| `class_assignments` | `{class_name: {instances: [entity_ids]}}` |
| `subclass_assignments` | `{subclass_name: {parent: class_name, instances: [entity_ids]}}` |
| `instance_data` | Phone book (schema + records) |
| `instance_attrs` | Per-entity sparse/complex attributes |
| `relationship_store` | Per-entity `[{label, target}]` edge lists |
| `overrides` | Per-entity B-layer deltas: `{entity_id: {owner: class_name, delta: {path: value}}}` |
| `b_composite_deltas` | Per-entity composite entry deltas for B-layer template refs |
| `foreign_keys` | FK detection results (v1 stub: empty dict) |

#### Composite Encoding

Composite template refs in instance_attrs are encoded as `{template: template_id, delta: delta_data}`. During reconstruction, the template is expanded and the delta applied.

### 3.7 Phase 7: Reconstruction Validation

**Module:** `src/decoct/reconstruction/validator.py` (263 lines)

The gate test. If this fails, the pipeline raises `ReconstructionError` and the output is not produced.

#### Structural Invariants

`validate_structural_invariants()` checks 8 invariants:

1. **No multi-class assignment**: no entity in more than one primary class
2. **Exact class coverage**: union of all class instances == all entities of that type
3. **Subclass parent containment**: every subclass entity is also in its parent class
4. **No multi-subclass assignment**: no entity in more than one subclass
5. **Max inheritance depth = 2**: no subclass has another subclass as its parent
6. **Valid override owners**: override `owner` field references an existing class or subclass
7. **Phone book rectangular**: every record has exactly `len(schema)` values
8. **No path in both phone book and instance_attrs**: prevents duplicate encoding

#### Per-Entity Fidelity

For every entity in the graph:

1. **Reconstitute** the entity from Tier B + Tier C using `reconstitute_entity()`
2. **Compare** every attribute path: original value vs reconstructed value using `CANONICAL_EQUAL`
3. For decomposed composites, compare against the **shadow map** (original pre-decomposition values)
4. **Compare relationships**: original `relationships_from()` vs reconstructed relationship list
5. Any mismatch → `AttributeMismatch` or `RelationshipMismatch` → `ReconstructionError`

#### Reconstitution Precedence Chain

`reconstitute_entity()` in `reconstitute.py` applies layers in order:

1. **base_class** attrs
2. **Primary class** own_attrs (overwrites base)
3. **Subclass** own_attrs (overwrites class, if entity has a subclass)
4. **Per-instance B overrides** (from `tier_c.overrides`). ABSENT removes the path.
5. **B-layer template expansion**: template refs in B-layer attrs are expanded. For `map_inner` templates, reconstruct from base template + per-entry deltas in `b_composite_deltas`.
6. **C-layer instance_attrs**: sparse/complex per-entity data. Template refs expanded here too.
7. **C-layer phone book**: dense per-entity scalar values. Overwrites any earlier value for the same path.

Later layers override earlier ones. The result must exactly match the original entity.

### 3.8 Phase 8: Assembly

**Module:** `src/decoct/assembly/tier_builder.py` (274 lines)

Builds the three-tier YAML output.

#### Tier A (`build_tier_a()`)

Fleet overview:
- `types`: per-type counts, class/subclass counts, file references
- `assertions`: `base_only_ratio`, `max_inheritance_depth` per type
- `topology`: inter-type connectivity (which types have entities with relationships to entities of other types)

#### Tier B (`build_tier_b()`)

Per-type class file:
- `meta`: entity_type, total_instances, max_inheritance_depth, tier_c_ref
- `base_class`: dict of shared attributes
- `classes`: dict of class definitions (inherits, own_attrs, instance_count_inclusive)
- `subclasses`: dict of subclass definitions (parent, own_attrs, instance_count)
- `composite_templates`: template definitions grouped by path (only if templates exist for this type)
- `assertions`: base_only_ratio

#### Tier C (`build_tier_c_yaml()`)

Per-type instance file. Uses **ID range compression** (`compress_id_ranges()`) to collapse contiguous sequential IDs: `[APE-R1-01, APE-R1-02, ..., APE-R1-20]` → `[APE-R1-01..APE-R1-20]`. Non-sequential IDs are listed individually. `expand_id_ranges()` provides the inverse for programmatic consumption.

---

## 4. Configuration

`src/decoct/core/config.py`. All thresholds are collected in `EntityGraphConfig`:

| Parameter | Default | Phase | Effect |
|---|---|---|---|
| `composite_decompose_threshold` | 5 | 3.5 | Min cardinality to trigger decomposition |
| `min_composite_template_members` | 2 | 3.5 | Min entities a template must cover |
| `min_class_support` | 3 | 4 | Min entities for a class to be created |
| `max_class_bundle_size` | 3 | 4, 5 | Max attributes in a class/subclass bundle |
| `min_subclass_size` | 3 | 5 | Min entities for a subclass to be promoted |
| `subclass_overhead_tokens` | 12 | 5 | Estimated token cost of subclass boilerplate |
| `max_anti_unify_variables` | 3 | 3 | Max variables before entities are considered different types |
| `small_group_floor` | 8 | 2b | Below this, stricter C-role classification threshold |
| `min_refinement_cluster_size` | 3 | 3 | Clusters below this are merged into larger ones |
| `unhinted_jaccard_threshold` | 0.4 | 2a | Jaccard similarity threshold for unhinted entity grouping |
| `fk_overlap_threshold` | 0.5 | 6 | FK detection (v1 stub, unused) |
| `fk_type_compat_threshold` | 0.3 | 6 | FK detection (v1 stub, unused) |
| `max_bootstrap_iterations` | 5 | 2+3 | Max refinement iterations before forced convergence |
| `token_cost_class_ref` | 4 | 4 | Estimated token cost of a class reference per entity |
| `compression_engine` | `"greedy-bundle"` | 4+5 | Selects the compression engine (class extraction + delta compression) |
| `secrets_entropy_threshold_b64` | 4.5 | 0 | Shannon entropy threshold for base64 secret candidates |
| `secrets_entropy_threshold_hex` | 3.0 | 0 | Shannon entropy threshold for hex secret candidates |
| `secrets_min_entropy_length` | 16 | 0 | Minimum string length for entropy-based detection |

---

## 5. Three-Tier Output Format

### 5.1 Tier A — Fleet Overview (`tier_a.yaml`)

```yaml
types:
  iosxr-access-pe:
    count: 60
    classes: 3
    subclasses: 3
    tier_b_ref: iosxr-access-pe_classes.yaml
    tier_c_ref: iosxr-access-pe_instances.yaml
assertions:
  iosxr-access-pe:
    base_only_ratio: 0.0
    max_inheritance_depth: 2
topology:
  iosxr-access-pe:
  - iosxr-p-core
```

### 5.2 Tier B — Shared Configuration (`{type}_classes.yaml`)

```yaml
meta:
  entity_type: iosxr-access-pe
  total_instances: 60
  max_inheritance_depth: 2
  tier_c_ref: iosxr-access-pe_instances.yaml
base_class:
  clock: timezone UTC 0
  interface.TenGigE0/0/0/0.mtu: '9216'
classes:
  address_family_l2vpn_evpn_maximum_paths_ibgp_1:
    inherits: base
    own_attrs:
      router.bgp.65002.address-family: l2vpn-evpn
    instance_count_inclusive: 20
subclasses:
  address_family_..._distance_bgp_20_200_200_gracef:
    parent: address_family_l2vpn_evpn_maximum_paths_ibgp_1
    own_attrs:
      router.bgp.65002.distance: bgp 20 200 200
    instance_count: 20
```

### 5.3 Tier C — Per-Entity Differences (`{type}_instances.yaml`)

```yaml
meta:
  entity_type: iosxr-rr
  tier_b_ref: iosxr-rr_classes.yaml
  total_instances: 4
class_assignments:
  _base_only:
    instances:
    - RR-01..RR-04
instance_data:
  schema:
  - hostname
  - interface.Loopback0.ipv4
  records:
    RR-01:
    - RR-01
    - address 10.0.0.11 255.255.255.255
relationship_store:
  RR-01:
  - label: p2p_link
    target: P-CORE-01
overrides:
  APE-R2-01:
    owner: some_subclass
    delta:
      router.bgp.65003.nsr: 'true'
```

### 5.4 Reconstruction Algorithm

To reconstruct any entity from the output:

1. Start with `base_class` from Tier B
2. Add the primary class `own_attrs` (look up class in Tier C `class_assignments`)
3. Add the subclass `own_attrs` if any (look up in `subclass_assignments`)
4. Apply `overrides` delta if any (ABSENT means remove the path)
5. Expand B-layer composite template refs + apply b_composite_deltas
6. Add `instance_attrs` (sparse per-entity data, expand template refs)
7. Add `instance_data` phone book values (dense per-entity scalars)

---

## 6. Statistics and Evaluation

### 6.1 Compression Statistics

`src/decoct/entity_graph_stats.py` (388 lines). Computes metrics by scanning input and output directories:

- **InputStats**: file_count, total_bytes, total_lines, total_tokens
- **TierStats**: per-tier file/byte/line/token counts
- **TypeStats**: per-type entity_count, class_count, subclass_count, base_attr_count, phone_book_width, override_count, relationship_count, tier B/C tokens
- **EntityGraphStatsReport**: aggregate with compression ratios and savings percentages

CLI: `decoct entity-graph stats -i <input_dir> -o <output_dir> [--format markdown|json]`

### 6.2 QA Comprehension Harness

`src/decoct/qa/questions.py` — deterministic question generation from parsed configs across six categories: SINGLE_VALUE, MULTI_ENTITY, EXISTENCE, COMPARISON, COUNT, ORDERING.

`src/decoct/qa/evaluate.py` — LLM-based evaluation comparing accuracy on raw vs compressed contexts. Uses fuzzy answer matching (case-insensitive, whitespace-normalised, boolean/numeric equivalence, substring containment).

CLI: `decoct entity-graph generate-questions`, `decoct entity-graph evaluate`

---

## 7. Key Design Decisions

### 7.1 CompositeValue Wrapping

Without composite wrapping, per-device structures like BGP neighbors or EVPN EVIs would appear as unique flat paths (e.g., `evpn.evi.10000.advertise-mac`), creating 60 singleton types instead of 1 type with 60 entities. CompositeValue keeps these structures atomic, enabling meaningful type discovery and class extraction.

### 7.2 Anti-Unification Restricted to Signal Paths

Type refinement compares entities using only bootstrap signal paths (VALUE_SIGNAL + PRESENCE_SIGNAL), not all 170+ attributes. Without this restriction, variable counts exceeded `max_anti_unify_variables=3` for every pair (because per-device values like IPs differ), preventing any merging and producing 86 singleton types.

### 7.3 Jaccard Clustering for Unhinted Entities

Replaced exact attribute-fingerprint grouping (commit `8f045ec`). Exact fingerprints over-split when key sets had minor variations (e.g., one entity has an extra optional field). Jaccard clustering with a 0.4 threshold tolerates these variations while still separating structurally different entities.

### 7.4 Small-Cluster Merge Guard

Added alongside Jaccard clustering (commit `8f045ec`). Prevents type refinement from shattering a coherent type into near-singletons. Three rules: (1) if ALL clusters are below threshold → return original type unchanged; (2) small clusters merge into the closest large group; (3) fallback to the largest group.

### 7.5 Homogeneous Map Detection

Added in commit `f57b033`. Dict-of-dicts where children have similar key sets (Jaccard ≥ 0.5) are stored as `CompositeValue(map)` instead of being recursively flattened. This prevents per-entry paths from polluting attribute profiles and breaking type discovery in hybrid-infra configs.

### 7.6 Map-Inner Decomposition

Added in commit `f57b033`. For map composites, pools all map entries across entities, extracts a common base template (most frequent value per common key), stores per-entity per-entry deltas. This achieves compression even when entities have different map entries (e.g., different Docker Compose services or BGP neighbors).

### 7.7 Hybrid-Infra Compression Journey

The hybrid-infra corpus (100 files: 54 YAML + 15 JSON + 31 INI across Docker Compose, Ansible, PostgreSQL, MariaDB, Traefik, cloud-init, Prometheus, sshd) was the hardest test for the pipeline. The compression journey illustrates how each fix addressed a specific failure mode:

| Stage | Compression | Root Cause / Fix |
|---|---|---|
| Initial run | **-14%** (output larger than input) | 100 entities split into 69 singleton types — type-per-entity produces no class compression |
| Round 1: Jaccard clustering + small-cluster merge guard (commit `8f045ec`) | **+16.7%** | Jaccard threshold 0.4 groups structurally similar entities; merge guard prevents shattering |
| Round 2: Stricter detection + map-inner decomposition (commit `f57b033`) | **+29-34%** | Stricter docker-compose detection (require `image` keys); single-child homogeneous map support (`min_children=1`); map-inner decomposition pools entries, extracts common template, stores deltas |

IOS-XR compression remained at 70-80% throughout all iterations — the homogeneous, hinted corpus was well-served from the first implementation.

### 7.8 Subsumed Prefix Filtering

When a composite covers a subtree (`evpn.evis` covers `evpn.evi.*`), flat paths under that prefix are excluded. Without this, both the composite and the flat paths would exist, causing double-counting and type-discovery failures.

### 7.9 Two-Pass Relationship Extraction (Entra-Intune)

Entra-Intune policies reference groups by UUID, but entity IDs are displayNames. All entities must be parsed first to build a UUID→displayName lookup, then relationships are resolved in a second pass via `extract_relationships()`.

### 7.10 Ordering Preservation

List ordering is semantically critical in infrastructure configs — ACL rules, Ansible task sequences, and route-policy entries are order-dependent. The pipeline preserves ordering through:
- `CompositeValue(kind="list")` maintains element order
- `CANONICAL_EQUAL` respects list order (JSON serialization preserves array order)
- The ORDERING question category was added to the QA harness to validate that LLM comprehension of order-dependent semantics is preserved after compression

### 7.11 v1 Stubs

Intentionally simple implementations that produce correct output but leave room for optimisation:

| Function | v1 Behaviour | Future |
|---|---|---|
| List composite decomposition | One cluster per distinct value | Cross-value template extraction |
| `anti_unify()` | Path-by-path comparison | Deeper structural anti-unification |
| `token_estimate_*()` | `len(str) / 4` approximation | tiktoken cl100k_base |
| `detect_foreign_keys_on_scalar_attrs()` | Returns empty dict | FK detection from value overlap |

### 7.12 Swappable Compression Engine

Phase 4 (class extraction) and Phase 5 (delta compression) were originally hardcoded as direct function calls in the pipeline orchestrator. To enable experimentation with alternative compression algorithms, these phases are now dispatched through a `CompressionEngine` ABC with a registry pattern (`src/decoct/compression/engine.py`). The default `GreedyBundleEngine` wraps the existing `extract_classes()` + `delta_compress()` calls unchanged. New engines can be added by subclassing `CompressionEngine`, implementing `compress()` and `name()`, and registering with `registry.register()`. The engine is selected via `EntityGraphConfig.compression_engine` or the `--compression-engine` CLI flag.

---

## 8. Test Architecture

### 8.1 Unit Tests

| File | Covers | Tests |
|---|---|---|
| `test_core/test_entity_graph.py` | EntityGraph CRUD, relationship dedup | 8 |
| `test_core/test_canonical.py` | Canonical equality, key functions | — |
| `test_core/test_config.py` | Config defaults | — |
| `test_analysis.py` | Shannon entropy, final role, bootstrap role, Tier C storage | 11 |
| `test_discovery.py` | Type seeding, Jaccard clustering, anti-unification, small-cluster merge | 12 |
| `test_composite_decomp.py` | Shadow map, template IDs, re-profiling, threshold | — |
| `test_class_extractor.py` | Base class, universal B, greedy bundles, min_support | 7 |
| `test_delta.py` | Delta computation, overrides, ABSENT handling | — |
| `test_normalisation.py` | Phone book routing, instance_attrs, relationships | — |
| `test_reconstruction.py` | Precedence chain (6 layers), ABSENT, template expansion, relationships | 9 |
| `test_assembly.py` | ID range compression round-trip | — |

### 8.2 Adapter Tests

| File | Covers |
|---|---|
| `test_adapters/test_iosxr_parser.py` | IOS-XR config tree parsing |
| `test_adapters/test_iosxr_paths.py` | Dotted-path extraction |
| `test_adapters/test_iosxr_adapter.py` | End-to-end adapter extraction |
| `test_adapters/test_hybrid_infra_adapter.py` | Multi-format parsing, homogeneous map detection, composite values |
| `test_adapters/test_hybrid_infra_corpus.py` | Corpus-level hybrid-infra pipeline |
| `test_adapters/test_entra_intune_adapter.py` | JSON parsing, relationship extraction |
| `test_adapters/test_entra_intune_corpus.py` | Corpus-level Entra pipeline |

### 8.3 End-to-End Tests

`test_entity_graph_e2e.py` — **THE gate test**. Runs `run_entity_graph_pipeline()` on all 86 IOS-XR fixture configs with `source_fidelity_mode="warn"` (IOS-XR has known adapter fidelity issues, see §11). Verifies:
- 0 reconstruction mismatches (implicit — pipeline raises if any)
- Strict source fidelity runs (warn mode) — mismatches logged but don't block
- 5 discovered types matching device roles
- Correct entity counts per type (60 access-pe, 8 bng, 6 p-core, 4 rr, 8 services-pe)
- Access PE has multiple classes
- Every type's base class has attributes
- Every entity assigned to exactly one class
- Tier A has all 5 types
- Relationships preserved
- Graph contains 86 entities

### 8.4 Statistics Tests

`test_entity_graph_stats.py` — 20 tests covering `compute_stats()`, `format_stats_markdown()`, `format_stats_json()`, and CLI integration (`decoct entity-graph stats`).

---

## 9. File Reference

### Source (entity-graph specific)

```
src/decoct/
  core/
    types.py              189 lines — Entity, Attribute, ClassHierarchy, TierC, sentinels
    entity_graph.py        76 lines — EntityGraph class
    config.py              39 lines — EntityGraphConfig
    canonical.py           78 lines — CANONICAL_KEY, CANONICAL_EQUAL, VALUE_KEY, ITEM_KEY
    composite_value.py     48 lines — CompositeValue wrapper
    hashing.py             39 lines — STABLE_CONTENT_HASH() for deterministic IDs
    io.py                         — I/O utilities for entity-graph file operations

  adapters/
    base.py                      — BaseAdapter ABC (parse, extract_entities, source_type, secret_paths, secret_value_patterns)
    entity_boundary.py     31 lines — Adapter boundary logic
    iosxr.py              563 lines — IOS-XR parser + entity extraction
    hybrid_infra.py       364 lines — Multi-format adapter (YAML/JSON/INI)
    entra_intune.py       343 lines — Entra/Intune JSON adapter

  analysis/
    entropy.py             39 lines — Shannon entropy
    profiler.py           101 lines — Attribute profiling
    tier_classifier.py     75 lines — Final role / bootstrap / Tier C storage classification

  discovery/
    type_seeding.py        79 lines — Coarse type seeding + Jaccard clustering
    type_discovery.py     211 lines — Type refinement + small-cluster merge
    anti_unification.py    70 lines — Anti-unification
    bootstrap.py           64 lines — Bootstrap loop orchestrator
    composite_decomp.py   354 lines — Composite decomposition + map-inner decomposition

  compression/
    engine.py                    — CompressionEngine ABC + _EngineRegistry + get_engine()
    greedy_bundle.py             — GreedyBundleEngine (default: wraps extract_classes + delta_compress)
    class_extractor.py    245 lines — Greedy frequent-bundle class extraction
    delta.py              281 lines — Delta compression + subclass promotion
    normalisation.py      144 lines — Tier C construction
    phone_book.py          23 lines — Dense phone book builder
    inversion.py           23 lines — FK detection (v1 stub, returns empty dict)

  assembly/
    tier_builder.py       274 lines — Tier A/B/C YAML builders + ID range compression/expansion
    assertions.py                 — Builds base_only_ratio and assertions for Tier A
    token_estimator.py            — Token estimation stubs (v1: len(str)/4 approximation)

  reconstruction/
    reconstitute.py       228 lines — Entity reconstitution from Tier B + C
    validator.py          263 lines — Structural invariants + per-entity fidelity
    strict_fidelity.py    320 lines — Strict bidirectional source fidelity (token normalisation + merge-join)
    parser_validation.py  103 lines — Layer 1: raw text section counts vs parsed tree (IOS-XR)
    source_fidelity.py    197 lines — Legacy fuzzy Layer 2 (superseded by strict_fidelity.py)

  secrets/
    detection.py                 — Core detection: entropy, regex (16 patterns), false-positive filter, path matching
    document_masker.py           — Pre-flatten tree walker for CommentedMap/dict documents
    attribute_masker.py          — Post-flatten masking for Entity.attributes + CompositeValue internals
    iosxr_patterns.py            — Adapter-specific patterns: IOS-XR, Entra-Intune, network devices
    __init__.py                  — Re-exports shared API

  projections/
    models.py                    — ProjectionSpec, SubjectSpec, RelatedPath dataclasses
    path_matcher.py              — Segment-aware glob matching (*, ** wildcards over dotted paths)
    spec_loader.py               — load_projection_spec() / dump_projection_spec()
    generator.py                 — generate_projection() + validate_projection()

  entity_pipeline.py             — Top-level orchestrator (chains Phase 0 + 8 phases)
  entity_graph_stats.py   388 lines — Compression statistics + CLI formatting
  learn_projections.py           — LLM-assisted projection spec inference (OpenRouter)

  qa/
    questions.py           — Question generation (6 categories: SINGLE_VALUE, MULTI_ENTITY,
                             EXISTENCE, COMPARISON, COUNT, ORDERING)
    evaluate.py            — LLM evaluation harness (fuzzy answer matching, raw vs compressed)

scripts/
  run_pipeline.py          — Runs IOS-XR corpus → output/iosxr/
  run_hybrid_infra.py      — Runs hybrid-infra corpus → output/hybrid-infra/
  run_entra_intune.py      — Runs Entra corpus → output/entra-intune/
  fetch_corpus.py          — Downloads public benchmark corpus
```

### Tests

```
tests/
  test_core/test_entity_graph.py       — EntityGraph unit tests
  test_core/test_canonical.py          — Canonical function tests
  test_core/test_config.py             — Config tests
  test_adapters/                       — Adapter tests (7 files)
  test_analysis.py                     — Profiling + classification tests
  test_discovery.py                    — Type seeding + refinement tests
  test_composite_decomp.py             — Composite decomposition tests
  test_compression_engine.py            — Compression engine ABC, registry, GreedyBundleEngine tests
  test_class_extractor.py              — Class extraction tests
  test_delta.py                        — Delta compression tests
  test_normalisation.py                — Normalisation tests
  test_reconstruction.py               — Reconstitution tests
  test_strict_fidelity.py              — Strict source fidelity: normalisation, expansion, E2E (34 tests)
  test_source_fidelity.py              — Legacy fuzzy source fidelity tests
  test_extraction_fidelity.py          — Extraction completeness tests
  test_assembly.py                     — Assembly tests
  test_entity_graph_e2e.py             — THE gate test (86 configs)
  test_entity_graph_stats.py           — Statistics tests
  test_projections/
    test_path_matcher.py               — 21 tests: segment matching, wildcards, collection
    test_spec_loader.py                — 10 tests: load, dump, validation, round-trip
    test_generator.py                  — 15 tests: synthetic data, filtering, validation
    test_projection_e2e.py             — 7 tests: real IOS-XR output, CLI smoke test
    test_learn_projections.py          — 11 tests: path extraction, LLM validation, mocked inference
  test_secrets/
    test_detection.py                  — Entropy, false-positive filter, detect_secret, hex discount
    test_document_masker.py            — Fixture-based, plain dict, CommentedMap, custom options
    test_attribute_masker.py           — String/composite/list attributes, extra patterns, audit paths
    test_iosxr_patterns.py             — Each regex, non-secret preservation, path patterns
    test_pipeline_integration.py       — Single-config pipeline, hybrid-infra, audit field, gate test
```

### Output (IOS-XR 86-config corpus)

```
output/iosxr/
  tier_a.yaml                — Fleet overview
  iosxr-access-pe_classes.yaml    — 60 entities, 3 classes, 3 subclasses
  iosxr-access-pe_instances.yaml
  iosxr-bng_classes.yaml          — 8 entities, 1 class
  iosxr-bng_instances.yaml
  iosxr-p-core_classes.yaml       — 6 entities, 1 class
  iosxr-p-core_instances.yaml
  iosxr-rr_classes.yaml           — 4 entities, 1 class (base_only_ratio: 1.0)
  iosxr-rr_instances.yaml
  iosxr-services-pe_classes.yaml  — 8 entities, 1 class
  iosxr-services-pe_instances.yaml
  projections/iosxr-access-pe/    — Subject projections (R3)
    bgp.yaml                      — BGP-only view (318 lines, 90% reduction)
    interfaces.yaml               — Interface-only view (1,019 lines, 67% reduction)
    evpn.yaml                     — EVPN/L2VPN-only view (619 lines, 80% reduction)

output/entra-intune/
  projections/intune-device-config/    — 7 subjects (LLM-inferred)
    app-settings.yaml, cellular-settings.yaml, device-security.yaml,
    storage-settings.yaml, browser-settings.yaml, kiosk-mode-settings.yaml,
    google-account-and-voice.yaml
  projections/entra-conditional-access/ — 3 subjects (LLM-inferred)
    general-settings.yaml, user-conditions.yaml, grant-and-session-controls.yaml
  projections/intune-compliance/       — 2 subjects (LLM-inferred)
    compliance-settings.yaml, assignments.yaml

output/hybrid-infra/
  projections/ansible-playbook/        — 6 subjects (LLM-inferred)
    playbook-basics.yaml, package-management.yaml, file-management.yaml,
    service-management.yaml, health-checks-and-waits.yaml, task-execution-details.yaml
  projections/docker-compose/          — 6 subjects (LLM-inferred)
    service-configuration.yaml, service-deployment-strategy.yaml,
    service-healthchecks.yaml, service-logging.yaml,
    network-configuration.yaml, volume-configuration.yaml
  projections/postgresql/              — 7 subjects (LLM-inferred, 137 params grouped)
    logging-configuration.yaml, autovacuum-settings.yaml,
    wal-replication-and-recovery.yaml, query-planning-and-optimization.yaml,
    connection-security-and-system.yaml, background-writer-and-checkpoints.yaml,
    vacuum-cost-management.yaml
  projections/sshd/                    — 3 subjects (LLM-inferred)
    general-settings.yaml, authentication.yaml, connection-parameters.yaml

specs/projections/iosxr-access-pe/
  projection_spec.yaml            — Hand-authored projection spec (3 subjects)
```

---

## 10. Development History

The entity-graph pipeline was built over ~26 hours across ~20 Claude Code sessions (2026-03-09 18:00 → 2026-03-10 20:15 UTC).

### 10.1 Development Phases

| Phase | Timeframe | Focus | Key Output |
|---|---|---|---|
| A | Mar 9, 18:00–18:15 | Pass-based pipeline polish | Updated docs, fixed inconsistencies |
| B | Mar 9, 18:15–18:28 | Benchmark harness | `decoct benchmark` CLI (435 lines) |
| C | Mar 9, 18:28–19:08 | Public corpus benchmark | 527 files, 7 platforms — discovered negative compression |
| D | Mar 10, 11:40 | Corpus-learned classes prototype | `corpus_classes.py` (~250 lines) |
| E | Mar 10, 11:55–12:20 | IOS-XR fixture generator | 86 devices (CSV + Jinja2 + Python) |
| F | Mar 10, 12:20–14:03 | **Core implementation** | All 8 pipeline phases, 97 tests, 0 mismatches |
| G | Mar 10, 13:34–15:39 | Entra/Intune + Hybrid-Infra fixtures and adapters | 88 JSON + 100 mixed-format files, 2 adapters |
| H | Mar 10, 15:39–17:37 | Stats module, QA harness, compression fixes | Stats CLI, 6 question categories, -14% → +29-34% |
| I | Mar 10, 17:37–19:09 | ORDERING questions + git commits | ORDERING category, 25 commits pushed |
| J | Mar 10 (parallel) | decoct.io website | Minimal landing page |
| K | Mar 10, 20:00–20:15 | Architecture documentation | This document |

### 10.2 Git Commits (25 entity-graph commits)

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

---

## 11. Current State and Open Items

### What Works (as of 2026-03-11)

- Complete entity-graph pipeline with 10 phases (Phase 0 secrets masking + Phase 1.5 source fidelity + 8 compression phases)
- Strict bidirectional source fidelity validation (Phase 1.5): token-sequence normalisation proves `source_tokens == entity_tokens` with no heuristics. 0 mismatches on hybrid-infra (JSON/YAML/INI). IOS-XR and Entra-Intune run in `warn` mode with known adapter issues documented (see Open Items)
- Secrets masking: detection engine (`src/decoct/secrets/`) with adapter-declared secret patterns via `BaseAdapter.secret_paths()` / `secret_value_patterns()`
- Three adapters: IOS-XR (86 configs), Entra-Intune (88 resources), Hybrid-Infra (100 files)
- 100% reconstruction fidelity on all three corpora (with secrets masking active)
- Statistics CLI with markdown/JSON output
- QA comprehension harness with 6 question categories
- Subject projections: deterministic generator + LLM-assisted spec inference (R3 complete), validated E2E on all three corpora — IOS-XR (hand-authored spec), Entra-Intune (3 types), Hybrid-Infra (4 types including 137-param PostgreSQL)
- Swappable compression engine: `CompressionEngine` ABC + registry pattern for Phase 4+5. Default `GreedyBundleEngine` wraps existing algorithms. Selectable via `EntityGraphConfig.compression_engine` or `--compression-engine` CLI flag
- Comprehensive test suite (716+ tests)

### Compression Results

| Corpus | Files | Entities | Types | Compression |
|---|---|---|---|---|
| IOS-XR | 86 | 86 | 5 | 70-80% |
| Hybrid-Infra | 100 | 100 | varies | 29-34% |
| Entra-Intune | 88 | 88 | 8 | — |

### Open Items

- **IOS-XR adapter source fidelity (~1502 mismatches)**: The strict bidirectional fidelity check (Phase 1.5) revealed three structural issues in the IOS-XR adapter that the previous fuzzy Layer 2 check was hiding. These are genuine adapter bugs, not validation false positives. The pipeline runs in `warn` mode for IOS-XR until these are fixed:

  1. **Bridge-group key collision**: When multiple bridge-domains exist under one bridge-group (e.g., `MGMT` and `DATA` under `BG1`), the adapter stores them in a Python dict keyed by bridge-domain name. The source leaf collector uses a flattened path prefix, but the entity's `CompositeValue` distributes bridge-domain names differently between path and value segments, producing non-matching token sequences. Some bridge-domain data may be lost via dict key overwrite.

  2. **BGP confederation peer restructuring**: Source configs express confederation peers as flat lines under `bgp confederation peers` (`65002`, `65003`). The adapter restructures these as discriminated map entries (`confederation.peers.65002`, `confederation.peers.65003`) with additional nesting depth that doesn't exist in source, producing token mismatches.

  3. **MPLS path insertion**: Source has `mpls ldp log ...` lines. The adapter sometimes normalises these into paths with an extra `ldp` segment (`mpls.ldp.log.neighbor` vs source's `mpls.log.neighbor`), creating token mismatches.

- **Entra-Intune adapter source fidelity (~173 mismatches)**: The adapter's `SKIP_FIELDS` list (which excludes `@odata.type` from flattening) only operates at the top level. Nested `@odata.type` fields inside arrays are included in source leaves but excluded from entity attributes, causing `missing_from_entity` mismatches. Fix: extend `SKIP_FIELDS` filtering to nested levels during `flatten_doc()`.

- **SNMP community string masking asymmetry (IOS-XR)**: IOS-XR discrimination puts SNMP community strings into path segments (`snmp-server.community.S3cr3tRO.RO`), but source leaves have the whole value masked (`snmp-server.[REDACTED]`). Path segments are never masked by `mask_entity_attributes()`. A path-segment masking pass or pre-flatten `ConfigNode` walker would resolve this.

- **List composite decomposition**: v1 stub uses one-cluster-per-value; future: cross-value template extraction
- **Anti-unification**: v1 path-by-path comparison; future: deeper structural anti-unification
- **Token estimation**: `len(str) / 4` approximation; future: tiktoken cl100k_base
- **FK detection**: v1 returns empty dict; future: detect foreign keys from value overlap across types
- **Additional adapters**: XML/CLI normalisation planned for Phase 3 of overall decoct roadmap
- **Secrets: entropy tuning**: current base64/hex thresholds work well on test corpora but may need per-adapter tuning for other platforms (e.g., Junos, Arista)
- **Secrets: IOS-XR pre-flatten**: `IosxrConfigTree` is not dict-walkable so IOS-XR relies entirely on post-flatten masking; a `ConfigNode` walker could catch secrets earlier in the pipeline

---

## 12. Roadmap

Six capabilities planned for the entity-graph pipeline.

### Development Philosophy: Claude Code First, API Later

R1, R3, and R4 require LLM intelligence to review data and produce artefacts (type hints, projection specs, Tier A guide text). All three now have API-based CLIs. The original approach was:

1. **Design each capability as spec-in, artefact-out.** Every LLM-dependent step produces a well-defined YAML artefact (ingestion spec, projection spec, guide section). The deterministic pipeline consumes these artefacts — it never calls an LLM directly.

2. **Use Claude Code as the initial LLM.** During development, a Claude Code session reads the pipeline output, applies domain reasoning, and writes the spec files interactively. This lets us iterate on the methodology — what questions to ask, what format the answers take, what the pipeline does with the answers — with a human in the loop.

3. **Productionise with API calls later (R6).** Once the spec formats and review prompts are proven, wrap them in API calls via the `LLMClient` abstraction. The spec files become the contract: any LLM that produces a valid spec file works.

This means **R6 is no longer a prerequisite for R1, R3, R4**. The dependency graph simplifies:

```
R2 Secrets Masking ✓ ──────────────────────────────┐
       │                                           │
       ▼                                           ▼
R1 Ingestion Review ✓ ► R3 Progressive Projections ✓ ──► R5 MCP Server
 (infer-spec CLI +        (project CLI +                   │
  spec machinery)          infer-projections CLI)           │
                                │                          │
                                ▼                          │
                          R4 Enhanced Tier A ✓ ─────────────┘
                           (review-tier-a CLI +
                            enhance-tier-a CLI)

R6 Multi-LLM Support ── later: unify R1/R3/R4 LLM wiring into LLMClient
```

### Spec File Convention

All LLM-generated artefacts follow a common pattern:

- **Location:** `specs/{capability}/{corpus}/` (e.g., `specs/ingestion/hybrid-infra/`, `specs/projections/iosxr-access-pe/`)
- **Format:** YAML, validated by dataclass schemas in `src/decoct/`
- **Versioned:** spec files are checked into git so methodology evolves with the codebase
- **Reproducible:** the deterministic pipeline + spec files = identical output without LLM re-invocation
- **Swappable:** during development Claude Code writes specs interactively; in production an API call writes the same spec format

### Model Selection

Each LLM-assisted CLI command has an independent `--model` default tuned to its task complexity. Different tasks have different requirements:

| Command | Default Model | Why |
|---|---|---|
| `infer-spec` | `google/gemini-2.5-flash-lite` | Simple classification task (identify platform from file content). Output is `platform: x` + optional `composite_paths`. Flash-lite is cost-effective and reliable for this. |
| `infer-projections` | `google/gemini-2.5-flash` | Requires precise glob syntax (`**` wildcards), logical grouping of attribute hierarchies, and domain reasoning. Flash-lite intermittently produces trailing-dot patterns (`router.bgp.`) instead of `router.bgp.**`, causing empty projections. Flash is consistently correct. Tested on all three corpora: IOS-XR (hierarchical paths), Entra-Intune (flat paths), Hybrid-Infra (mixed — flat INI keys, nested YAML structures, 137-param PostgreSQL configs). |

All commands accept `--model`, `--base-url`, and `--api-key-env` for full override. Models tested on all three corpora (IOS-XR, Entra-Intune, Hybrid-Infra):

| Model | infer-spec | infer-projections | Notes |
|---|---|---|---|
| `gemini-2.5-flash-lite` | Reliable | **Unreliable** — intermittent `**` syntax failures | Best for simple classification |
| `gemini-2.5-flash` | Reliable | Reliable (IOS-XR + Entra-Intune) | Best default for projections |
| `deepseek/deepseek-chat-v3-0324` | Not tested | Usable but over-generalises (`router.**` too broad) | Needs prompt tuning for projections |

**Cross-corpus adaptation:** `gemini-2.5-flash` correctly adapts its pattern style to the data structure without prompt changes:
- **IOS-XR** (deep hierarchical): `router.bgp.**`, `interface.**` — `**` glob patterns
- **Entra-Intune** (flat keys): `appsBlockClipboardSharing`, `webBrowserBlocked` — exact matches
- **Hybrid-Infra** (mixed): `services.**`, `networks.**` for Docker Compose; exact matches for PostgreSQL (137 flat params grouped into 7 DBA-oriented subjects), sshd (20 keys → 3 subjects), Ansible playbook (flat task params → 6 subjects)

---

### R1. LLM-Assisted Ingestion Review — COMPLETE

**Status:** Implemented 2026-03-11. Spec machinery (R1a) and automated inference CLI (R1b) both complete.

**Problem:** The hybrid-infra adapter assigns `schema_type_hint = None` for any format not matched by the 8 hard-coded patterns in `detect_platform()` (e.g., Nagios, HAProxy, Logrotate, systemd units). These "unknown" entities cluster by Jaccard similarity alone, producing types with opaque auto-generated names like `unknown-3`. The pipeline compresses them correctly, but the output lacks semantic meaning — an LLM reading the Tier A/B output has no idea what these entities represent.

**Solution:** An **ingestion spec** that the adapter loads before entity extraction. The spec provides platform identification, composite value guidance, and relationship hints for entities that the adapter can't classify on its own.

#### Ingestion Spec Format

```yaml
# specs/ingestion/hybrid-infra/ingestion_spec.yaml
version: 1
adapter: hybrid-infra
generated_by: decoct-infer    # or "claude-code" for hand-authored
entries:
- file_pattern: "pg-*"
  platform: postgresql
  description: "PostgreSQL server configuration"

- file_pattern: "package-json-*"
  platform: package-json
  description: "Node.js package manifest"
  composite_paths:
  - path: "dependencies"
    kind: map
    reason: "Package dependency map keyed by package name"
  - path: "devDependencies"
    kind: map
    reason: "Dev dependency map keyed by package name"
```

#### R1a: Spec Machinery (Manual Authoring)

**What was built:**

- **Spec model:** `src/decoct/adapters/ingestion_models.py` — dataclasses (`IngestionSpec`, `IngestionEntry`, `CompositePathSpec`, `RelationshipHintSpec`)
- **Spec loader:** `src/decoct/adapters/ingestion_spec.py` — `load_ingestion_spec()` (YAML → validated dataclass), `match_entry()` (fnmatch against file patterns)
- **Adapter integration:** `HybridInfraAdapter` accepts optional `ingestion_spec` in constructor. When present, matches each file against spec entries and applies `platform` as `schema_type_hint`, `composite_paths` as override for default composite detection, and `relationship_hints` during relationship extraction.
- **Hand-authored spec:** `specs/ingestion/hybrid-infra/ingestion_spec.yaml` — 12 entries covering all hybrid-infra fixture platforms

#### R1b: Automated Spec Inference (CLI)

**What was built:**

- **Core module:** `src/decoct/learn_ingestion.py` — runs partial pipeline (canonicalise + type seeding), identifies `unknown-N` clusters, sends representative file samples to an LLM per cluster, assembles spec YAML
- **CLI command:** `decoct entity-graph infer-spec -i <input_dir> [-o spec.yaml]`
- **LLM provider:** OpenAI SDK with configurable `--base-url` (defaults to OpenRouter) and `--api-key-env` (defaults to `OPENROUTER_API_KEY`). Works with any OpenAI-compatible endpoint.
- **Default model:** `google/gemini-2.5-flash-lite` — cost-effective ($0.10/M prompt tokens), reliable structured YAML output
- **Dependencies:** `openai>=1.0` and `python-dotenv>=1.0` added to `[llm]` extras; `.env` file auto-loaded if present

**CLI options:**

```bash
decoct entity-graph infer-spec \
  --input-dir tests/fixtures/hybrid-infra/configs/ \
  --adapter hybrid-infra \              # or entra-intune
  --model google/gemini-2.5-flash-lite \  # any OpenRouter/OpenAI-compatible model
  --base-url https://openrouter.ai/api/v1 \
  --api-key-env OPENROUTER_API_KEY \
  --output /tmp/inferred_spec.yaml
```

**Design decisions:**

- One LLM call per unknown cluster — cleaner context per platform
- Only unknown clusters get LLM calls — auto-detected types keep `detect_platform()` hints
- Graceful degradation — LLM failure for one cluster → warn + skip, partial spec still useful
- `on_progress` callback keeps the library module CLI-agnostic
- Prompt engineering required 3 iterations to eliminate false-positive composite paths (config sections with named settings vs. genuine homogeneous collections)

**Tests:** `tests/test_learn_ingestion.py` — 22 tests covering pure logic, validation, sample selection, round-trip serialization, mocked LLM integration, and CLI

---

### R2. Secrets Masking for Entity-Graph Pipeline — COMPLETE

**Status:** Implemented 2026-03-11. See §3.0 for architecture details.

**What was built:**

- **Detection engine** (`src/decoct/secrets/`):
  - 16 regex patterns (up from 6): added AWS secret keys, basic auth URLs, JWTs, GitLab PATs, Slack tokens, SendGrid, Stripe, Cisco type 7/8/9, Junos encrypted
  - Charset-aware entropy with separate base64 (4.5) and hex (3.0) thresholds
  - False-positive filter (runs before regex): UUIDs, IPs, MACs, file paths, template variables, indirect references, pure numerics
  - Extended path denylist: 19 patterns (up from 10)
  - Extended entropy-exempt paths: descriptions, comments

- **Pre-flatten document masking** (`document_masker.py`) — walks CommentedMap/dict trees, used by hybrid-infra and entra-intune adapters

- **Post-flatten attribute masking** (`attribute_masker.py`) — scans Entity.attributes including CompositeValue internals, supports adapter-specific value-level patterns

- **Adapter-declared patterns** — `BaseAdapter` provides `secret_paths()` and `secret_value_patterns()` methods; each adapter overrides to declare its own patterns. The orchestrator has no adapter type-switching.

- **111 tests** across 5 test modules.

**Security invariant:** Phase 0 MUST complete before any Claude Code review of raw configs or any API-based LLM contact. This is enforced by pipeline phase ordering and by the convention that spec files are generated from masked output, never raw input.

**Outstanding items:**
- IOS-XR pre-flatten: `IosxrConfigTree` is not dict-walkable; a `ConfigNode` tree walker would catch secrets before flattening (currently handled entirely by post-flatten)
- Entropy threshold tuning for additional platforms (Junos, Arista, Palo Alto)
- No CLI flag to disable secrets masking (always on — intentional for safety, but may want `--no-secrets-mask` for debugging)

---

### R3. Progressive Discovery — Subject Projections — COMPLETE

**Status:** Implemented 2026-03-11. Both deterministic projection generator (R3a) and automated LLM inference CLI (R3b) complete.

**Problem:** The current three-tier output assumes the consumer loads everything for a type. For a 60-entity IOS-XR access-PE fleet, an LLM investigating a BGP issue must load the full Tier B (3,077 lines across classes + instances) — most of which is irrelevant to BGP. Disk is cheap; context tokens are not.

**Solution:** Subject projections slice Tier B/C into per-subject views (e.g., BGP-only, interfaces-only), dramatically reducing context for targeted questions. Two deliverables:

1. **Deterministic projection generator** — spec-in, projected YAML out
2. **`infer-projections` CLI** — LLM reads Tier B, generates projection spec automatically

#### Projection Spec Format

```yaml
# specs/projections/iosxr-access-pe/projection_spec.yaml
version: 1
source_type: iosxr-access-pe
generated_by: claude-code    # or "decoct-infer" for LLM-generated
subjects:
- name: bgp
  description: "BGP routing configuration including AS numbers, address families, and timers"
  include_paths:
  - "router.bgp.**"
  related_paths:
  - path: hostname
    reason: "Device identity for BGP neighbor correlation"
  example_questions:
  - "What BGP AS number is used across the fleet?"
  - "Which devices have BGP graceful-restart enabled?"

- name: interfaces
  description: "Interface configuration including IP addressing, MTU, and descriptions"
  include_paths:
  - "interface.**"
  related_paths:
  - path: hostname
    reason: "Device identity"

- name: evpn
  description: "EVPN and L2VPN configuration"
  include_paths:
  - "evpn.**"
  - "l2vpn.**"
  related_paths:
  - path: hostname
    reason: "Device identity"
  - path: "interface.Bundle-Ether*"
    reason: "Bundle-Ether sub-interfaces carry L2 transport"
```

#### R3a: Deterministic Projection Generator

**What was built:**

- **Models:** `src/decoct/projections/models.py` — dataclasses (`ProjectionSpec`, `SubjectSpec`, `RelatedPath`)
- **Path matcher:** `src/decoct/projections/path_matcher.py` — segment-aware glob matching over dotted attribute paths. `*` matches one segment, `**` matches zero or more, per-segment `fnmatch` for character wildcards.
- **Spec loader:** `src/decoct/projections/spec_loader.py` — `load_projection_spec()` / `dump_projection_spec()` (YAML ↔ validated dataclass)
- **Generator:** `src/decoct/projections/generator.py` — `generate_projection()` slices Tier B/C by subject, `validate_projection()` checks subset fidelity
- **CLI command:** `decoct entity-graph project -o <output_dir> -s <spec_file> [--type TYPE] [--subjects s1,s2]`
- **Hand-authored spec:** `specs/projections/iosxr-access-pe/projection_spec.yaml` — BGP, interfaces, EVPN subjects

**Projection algorithm** (operates on assembled YAML dicts, no pipeline re-run needed):
1. Collect all attribute paths from Tier B (base_class, classes, subclasses, composite_templates) and Tier C (phone book schema, instance_attrs, overrides, b_composite_deltas)
2. Filter to matching paths via `collect_matching_paths()` (include_paths + related_paths)
3. Filter base_class — keep only matching paths
4. Filter classes/subclasses — filter `own_attrs`; classes with empty own_attrs become invisible
5. Re-derive class assignments — entities from invisible classes → `_base_only`
6. Column-slice phone book — keep only matching schema columns
7. Filter instance_attrs, overrides, b_composite_deltas — keep matching path keys per entity
8. Filter composite_templates — keep templates whose path prefix matches the subject
9. Validate — projected paths ⊂ original, values match, entity coverage preserved

**Note:** `composite_templates` elements can be either lists of dicts (Entra-Intune format: `[{"target.groupId": "..."}]`) or dicts (other formats). The path collector handles both.

**Projected output** is written to `{output_dir}/projections/{type_id}/{subject}.yaml`.

**Compression results on IOS-XR access-PE (60 devices, 3,077 lines full Tier B+C):**

| Subject | Lines | Reduction | Content |
|---|---|---|---|
| bgp | 318 | 90% | 3 AS classes, subclasses with timers/graceful-restart, per-device network statements |
| interfaces | 1,019 | 67% | Loopback0, BVI, TenGigE, MgmtEth — IPs, MTU, descriptions |
| evpn | 619 | 80% | EVPN/L2VPN flags, Bundle-Ether sub-interfaces with L2 transport |

**E2E validation on Entra-Intune** (LLM-inferred specs, `gemini-2.5-flash`):

| Type | Subjects | Notes |
|---|---|---|
| `intune-device-config` | 7 (app-settings, cellular, device-security, storage, browser, kiosk-mode, google-account-and-voice) | Flat paths — LLM correctly uses exact matches instead of `**` globs |
| `entra-conditional-access` | 3 (general-settings, user-conditions, grant-and-session-controls) | Mix of flat (`state`) and nested (`conditions.users.**`, `grantControls.**`) |
| `intune-compliance` | 2 (compliance-settings, assignments) | Small type; LLM identifies security vs assignment split |

**E2E validation on Hybrid-Infra** (LLM-inferred specs, `gemini-2.5-flash`):

| Type | Subjects | Notes |
|---|---|---|
| `ansible-playbook` (219 lines) | 6 (playbook-basics, package-management, file-management, service-management, health-checks-and-waits, task-execution-details) | Flat Ansible task params grouped by operational concern |
| `docker-compose` | 6 (service-configuration, deployment-strategy, healthchecks, logging, network-configuration, volume-configuration) | Nested paths — uses `services.**`, `networks.**`, `volumes.**` |
| `postgresql` (137 prefixes) | 7 (logging, autovacuum, wal-replication-and-recovery, query-planning, connection-security, bgwriter-and-checkpoints, vacuum-cost-management) | Largest flat key set tested; LLM grouped 137 params into DBA-oriented subjects |
| `sshd` (20 keys) | 3 (general-settings, authentication, connection-parameters) | Clean split of SSH config knobs |

#### R3b: Automated Spec Inference (CLI)

**What was built:**

- **Core module:** `src/decoct/learn_projections.py` — loads Tier B, extracts attribute path prefixes, sends to LLM, parses response into `ProjectionSpec`
- **CLI command:** `decoct entity-graph infer-projections -o <output_dir> --type <type_id> [--model ...] [--base-url ...] [--api-key-env ...] [--output spec.yaml]`
- **LLM provider:** OpenAI SDK with configurable `--base-url` (defaults to OpenRouter) and `--api-key-env` (defaults to `OPENROUTER_API_KEY`). Same pattern as R1 `infer-spec`.
- **Default model:** `google/gemini-2.5-flash` — flash-lite is unreliable with `**` glob syntax; flash is only marginally more expensive and consistently correct

**CLI options:**

```bash
decoct entity-graph infer-projections \
  --output-dir output/iosxr/ \
  --type iosxr-access-pe \
  --model google/gemini-2.5-flash \
  --base-url https://openrouter.ai/api/v1 \
  --api-key-env OPENROUTER_API_KEY \
  --output /tmp/inferred_projection_spec.yaml
```

**Design decisions:**

- One LLM call per type — Tier B is typically small enough for a single call
- System prompt instructs LLM to identify 3-8 subjects, use `**` glob patterns, include hostname as related_path
- Reuses `extract_yaml_block()` and the `_call_llm` pattern from `learn_ingestion.py`
- `on_progress` callback keeps the library module CLI-agnostic

**Tests:** 64 tests across 5 test modules:
- `test_path_matcher.py` — 21 tests (segment matching, wildcards, collection)
- `test_spec_loader.py` — 10 tests (load, dump, validation, round-trip)
- `test_generator.py` — 15 tests (synthetic Tier B/C data, filtering, validation)
- `test_projection_e2e.py` — 7 tests (real IOS-XR output, CLI smoke test)
- `test_learn_projections.py` — 11 tests (path prefix extraction, LLM validation, mocked inference)

---

### R4. Enhanced Tier A — LLM Instruction Layer ✓

**Status:** Complete. `decoct entity-graph review-tier-a` generates a Tier A spec via LLM; `decoct entity-graph enhance-tier-a` merges it into `tier_a.yaml` deterministically.

**Problem:** Current Tier A is a bare summary (type counts, class counts, topology). An LLM receiving Tier A has no guidance on what's available, how to navigate the data, or which projection to load for a given question. It's a table of contents without instructions.

**Solution:** Two-step workflow mirroring R1/R3 (LLM generates spec → deterministic merge):

1. `decoct entity-graph review-tier-a` — sends Tier A + all Tier B files to an LLM, returns a **Tier A spec** (corpus description, usage instructions, per-type summaries)
2. `decoct entity-graph enhance-tier-a` — deterministically merges the spec into `tier_a.yaml`, adding a `guide` section, per-type descriptions, and a `projections` index (scanned from R3 output)

#### Two-Step CLI Workflow

```bash
# Step 1: LLM generates the spec
decoct entity-graph review-tier-a -o output/iosxr/ --output specs/tier-a/iosxr/tier_a_spec.yaml

# Step 2: Deterministic merge into tier_a.yaml
decoct entity-graph enhance-tier-a -o output/iosxr/ -s specs/tier-a/iosxr/tier_a_spec.yaml
```

#### Tier A Spec Format

```yaml
# specs/tier-a/iosxr/tier_a_spec.yaml
version: 1
generated_by: decoct-infer
corpus_description: "86 Cisco IOS XR devices, categorized into 5 distinct types: access PEs, BNGs, P-Cores, Route Reflectors, and services PEs."
how_to_use:
- "Begin by reviewing this Tier A orientation guide for a high-level overview."
- "For detailed class definitions, consult the respective Tier B files."
- "To find specific differences for individual devices, refer to the Tier C files."
type_descriptions:
  iosxr-access-pe:
    summary: "Access PE routers at the network edge, connecting end-user networks to the core."
    key_differentiators:
    - "Only type with multiple classes and subclasses, indicating significant configuration variation."
    - "Features EVPN and L2VPN configurations for access services."
    - "BGP peering for multiple ASNs (65002, 65003, 65004)."
  iosxr-rr:
    summary: "Route Reflectors for BGP route distribution, reducing full mesh requirements."
    key_differentiators:
    - "All RRs share identical base configurations (base_only_ratio: 1.0)."
```

#### Enhanced Tier A Output

After `enhance-tier-a`, the `tier_a.yaml` gains three additions:

```yaml
# Existing types section now includes per-type descriptions inline
types:
  iosxr-access-pe:
    count: 60
    classes: 3
    subclasses: 3
    tier_b_ref: iosxr-access-pe_classes.yaml
    tier_c_ref: iosxr-access-pe_instances.yaml
    summary: "Access PE routers at the network edge..."    # ← merged from spec
    key_differentiators:                                   # ← merged from spec
    - "Only type with multiple classes and subclasses..."
# ...existing assertions and topology sections...

# New: guide section
guide:
  corpus_description: "86 Cisco IOS XR devices..."
  how_to_use:
  - "Begin by reviewing this Tier A orientation guide..."
  reconstruction: "To reconstruct any entity: start with base_class..."

# New: projection index (auto-scanned from projections/ directory)
projections:
  iosxr-access-pe:
  - bgp
  - bgp-config
  - evpn
  - interfaces
```

#### Validated Across All Three Corpora

| Corpus | Types | Enhanced tier_a | Projections indexed |
|---|---|---|---|
| IOS-XR | 5 | 142 lines | 5 subjects (1 type) |
| Entra/Intune | 24 | 463 lines | 12 subjects (3 types) |
| Hybrid-Infra | 17 | 332 lines | 24 subjects (4 types) |

#### Modules

- `src/decoct/assembly/tier_a_models.py` — `TierASpec`, `TierATypeDescription` dataclasses
- `src/decoct/assembly/tier_a_spec.py` — `load_tier_a_spec()` / `dump_tier_a_spec()`
- `src/decoct/assembly/tier_builder.py` — `merge_tier_a_spec()` + `scan_projection_index()` (existing `build_tier_a()` unchanged)
- `src/decoct/learn_tier_a.py` — LLM inference: prompt design, YAML sanitization, validation, orchestrator

**Depends on:** R3 (projection index requires projections to exist for the `projections` section; `guide` and `type_descriptions` can be built independently)

---

### R5. MCP Server — Progressive Disclosure

**Problem:** Even with projections, an LLM must know which file to load. An MCP server enables the LLM to discover and request exactly the data it needs through tool calls, without pre-loading everything.

**Solution:** An MCP server exposing the entity-graph output as tools for progressive disclosure.

#### Tools

| Tool | Parameters | Returns |
|---|---|---|
| `decoct_fleet_overview` | — | Tier A content (always small, safe to load fully) |
| `decoct_list_projections` | `type_id?` | Available projections with descriptions and example questions |
| `decoct_load_projection` | `type_id`, `subject` | Projected Tier B/C for one subject |
| `decoct_load_type_classes` | `type_id` | Full Tier B for one type |
| `decoct_load_type_instances` | `type_id` | Full Tier C for one type |
| `decoct_get_entity` | `entity_id` | Reconstituted entity (runs reconstitution on the fly) |
| `decoct_compare_entities` | `entity_ids[]` | Side-by-side diff of reconstituted entities |
| `decoct_search_attributes` | `path_pattern`, `value_pattern?` | Entities matching attribute criteria |
| `decoct_topology` | `type_id?` | Relationship graph (filtered or full) |

#### Architecture

```
src/decoct/mcp/
  server.py          — MCP server setup (FastMCP or low-level protocol)
  tools.py           — tool implementations (thin wrappers over existing modules)
  resources.py       — optional MCP resources for Tier A/B/C files
```

The server reads from a pre-computed output directory. No pipeline execution at query time — all tools operate on the assembled YAML files. `decoct_get_entity` uses `reconstitute_entity()` from the reconstruction module.

**CLI:** `decoct mcp serve --output-dir <dir> [--port 8080]`

**Depends on:** R3 (projections), R4 (enhanced Tier A for fleet_overview), R2 (secrets already masked in output)

---

### R6. Multi-LLM Support — Productionising the Spec Workflow

**Partial status:** R1, R3, and R4 are all API-based via `decoct entity-graph infer-spec`, `decoct entity-graph infer-projections`, and `decoct entity-graph review-tier-a` (all use OpenAI SDK with configurable `--base-url`, defaults to OpenRouter).

**Problem:** For production use (CI pipelines, non-interactive runs), a unified `LLMClient` abstraction would simplify provider management across all three spec-generating commands.

**Timing:** R6 unifies the LLM wiring across R1/R3/R4 into a single abstraction. All capabilities are already proven via their individual CLIs.

**Solution:** An `LLMClient` abstraction in `src/decoct/llm/`:

```python
# src/decoct/llm/client.py
class LLMClient(Protocol):
    def complete(self, system: str, messages: list[dict], max_tokens: int) -> str: ...
    def model_name(self) -> str: ...

class AnthropicClient(LLMClient): ...   # wraps anthropic.Anthropic()
class OpenAICompatClient(LLMClient): ...  # wraps openai.OpenAI(base_url=...) — covers DeepSeek, Ollama, vLLM
```

**What R6 automates:**

| Capability | Claude Code (development) | API call (production) |
|---|---|---|
| R1 Ingestion Review | ~~Claude Code reads unknown entities, writes `ingestion_spec.yaml`~~ | **Done:** `decoct entity-graph infer-spec` sends samples to LLM, writes spec |
| R3 Projection Specs | ~~Claude Code reads Tier B, writes `projection_spec.yaml`~~ | **Done:** `decoct entity-graph infer-projections` sends Tier B to LLM, writes spec |
| R4 Tier A Guide | ~~Claude Code reads Tier A/B, writes `tier_a_spec.yaml`~~ | **Done:** `decoct entity-graph review-tier-a` sends Tier A/B to LLM, writes spec |

The spec files are the contract. The deterministic pipeline doesn't care who wrote them.

**DeepSeek specifics:**
- Base URL: `https://api.deepseek.com` (OpenAI-compatible)
- Model: `deepseek-chat` (DeepSeek-V3) or `deepseek-reasoner` (DeepSeek-R1)
- API key via `DEEPSEEK_API_KEY` env var
- Supports system messages, structured output via JSON mode

**Dependency management:**
- `pip install decoct[llm]` — Anthropic SDK + OpenAI SDK + python-dotenv (existing; OpenAI SDK added for R1 infer-spec)
- Future: may add provider-specific extras if needed, but OpenAI-compatible SDK covers most providers via `--base-url`

**Configuration:**
- `--llm-provider anthropic|deepseek|openai-compat` CLI flag
- `--llm-model <model-id>` override
- `--llm-base-url <url>` for custom endpoints (Ollama, vLLM)
- Environment: `DECOCT_LLM_PROVIDER`, `DECOCT_LLM_MODEL`

**Migration:** Refactor LLM modules to accept `LLMClient` instead of creating their own client instances.

**Module:** `src/decoct/llm/` — `client.py` (protocol + implementations), `__init__.py` (factory), `review.py` (prompt templates for R1/R3/R4 review commands)

---

### Implementation Priority

Recommended build order. R1–R4 complete; R6 unifies LLM wiring.

| Priority | Item | Rationale |
|---|---|---|
| **P0** | R2 Secrets Masking ✓ | Security boundary — must exist before Claude Code reviews any raw configs |
| **P1** | R1 Ingestion Review ✓ | Spec machinery + `infer-spec` CLI with OpenRouter/OpenAI-compatible LLM |
| **P1** | R3 Progressive Projections ✓ | Deterministic generator + `infer-projections` CLI with OpenRouter/OpenAI-compatible LLM |
| **P2** | R4 Enhanced Tier A ✓ | `review-tier-a` CLI + `enhance-tier-a` deterministic merge |
| **P2** | R5 MCP Server | Consumer of R3+R4, high user-facing value |
| **P3** | R6 Multi-LLM Support | Unify R1/R3/R4 LLM wiring into single `LLMClient` abstraction |
