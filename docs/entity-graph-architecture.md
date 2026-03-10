# Entity-Graph Pipeline — Architecture and Design

This document is the authoritative reference for the entity-graph compression pipeline. It supersedes the handoff document (`docs/dev/entity-graph-handoff.md`), the data manual (`docs/entity-graph-data-manual.md`), the evaluation guide (`docs/entity-graph-evaluation.md`), and the session summary (`docs/session-summary-2026-03-10.md`).

---

## 1. Purpose

The entity-graph pipeline compresses fleets of infrastructure configurations into a three-tier YAML representation that separates shared structure from per-entity differences. The compression is lossless — every entity can be reconstructed exactly from the output. The system typically achieves 70-80% token savings on homogeneous corpora (IOS-XR) and 29-34% on heterogeneous mixed-format corpora (hybrid-infra).

The pipeline operates entirely independently of the existing pass-based pipeline. No existing code was modified to build it.

### 1.1 Origins

The entity-graph pipeline was motivated by a critical finding from the benchmark harness. Running `decoct benchmark` on a 527-file public corpus (docker/awesome-compose, kubernetes/examples, ansible/ansible-examples, etc.) revealed that the schema tier had **negative compression** for Kubernetes (-211%) and Docker Compose (-119%). The root cause: the `emit-classes` pass emitted ALL vendor schema defaults as header comments regardless of actual stripping — costing more tokens than it saved.

Rather than patching the pass-based pipeline, the user proposed an **LZ77/Huffman-style general solution**: discover compression classes from corpus data itself rather than relying on platform-specific rules. The idea was that recurring patterns in infrastructure configs (shared BGP configurations across routers, identical service definitions across environments) are analogous to repeated byte sequences that LZ77 discovers. This conceptual insight became the seed for the entity-graph pipeline — a system that automatically discovers entity types, extracts shared class structures, and compresses the remainder into per-entity deltas.

An initial prototype (`src/decoct/corpus_classes.py`, ~250 lines) tested the concept: flatten documents → discover instance levels → mine frequent (path, value) pairs → co-occurrence clustering → greedy score/select. This platform-agnostic approach proved viable and evolved into the current eight-phase pipeline.

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

The pipeline is orchestrated by `run_entity_graph_pipeline()` in `src/decoct/entity_pipeline.py` (146 lines). It chains eight phases:

```
Input files (.cfg, .yaml, .json, .ini, .conf)
  │
  ▼
[Phase 1] Canonicalise ─── adapter.parse() + adapter.extract_entities() → EntityGraph
  │
  ▼
[Phase 2+3] Bootstrap Loop ─── seed types → profile → refine → converge
  │
  ▼
[Phase 3.5] Composite Decomposition ─── shadow map + template extraction
  │
  ▼
[Phase 4] Class Extraction ─── greedy frequent-bundle clustering
  │
  ▼
[Phase 5] Delta Compression ─── subclass promotion for compression gain
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
```

### 3.1 Phase 1: Canonicalise

**Module:** Adapter-specific (`src/decoct/adapters/`)

Each adapter implements `BaseAdapter`:

```python
class BaseAdapter(ABC):
    def parse(self, source: str) -> Any: ...
    def extract_entities(self, parsed: Any, graph: EntityGraph) -> None: ...
    def source_type(self) -> str: ...
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

### 3.4 Phase 4: Class Extraction

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

### 3.5 Phase 5: Delta Compression

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

`test_entity_graph_e2e.py` — **THE gate test**. Runs `run_entity_graph_pipeline()` on all 86 IOS-XR fixture configs. Verifies:
- 0 reconstruction mismatches (implicit — pipeline raises if any)
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

  adapters/
    base.py                31 lines — BaseAdapter ABC
    iosxr.py              563 lines — IOS-XR parser + entity extraction
    hybrid_infra.py       364 lines — Multi-format adapter
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
    class_extractor.py    245 lines — Greedy frequent-bundle class extraction
    delta.py              281 lines — Delta compression + subclass promotion
    normalisation.py      144 lines — Tier C construction
    phone_book.py          23 lines — Dense phone book builder
    inversion.py           23 lines — FK detection (v1 stub)

  assembly/
    tier_builder.py       274 lines — Tier A/B/C YAML builders + ID range compression

  reconstruction/
    reconstitute.py       228 lines — Entity reconstitution from Tier B + C
    validator.py          263 lines — Structural invariants + per-entity fidelity

  entity_pipeline.py      146 lines — Top-level orchestrator
  entity_graph_stats.py   388 lines — Compression statistics

  qa/
    questions.py           — Question generation (6 categories)
    evaluate.py            — LLM evaluation harness
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
  test_class_extractor.py              — Class extraction tests
  test_delta.py                        — Delta compression tests
  test_normalisation.py                — Normalisation tests
  test_reconstruction.py               — Reconstitution tests
  test_assembly.py                     — Assembly tests
  test_entity_graph_e2e.py             — THE gate test (86 configs)
  test_entity_graph_stats.py           — Statistics tests
```

### Output (IOS-XR 86-config corpus)

```
output/entity-graph/
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

### What Works (as of 2026-03-10)

- Complete entity-graph pipeline with 8 phases
- Three adapters: IOS-XR (86 configs), Entra-Intune (88 resources), Hybrid-Infra (100 files)
- 100% reconstruction fidelity on all three corpora
- Statistics CLI with markdown/JSON output
- QA comprehension harness with 6 question categories
- Comprehensive test suite (97+ tests)

### Compression Results

| Corpus | Files | Entities | Types | Compression |
|---|---|---|---|---|
| IOS-XR | 86 | 86 | 5 | 70-80% |
| Hybrid-Infra | 100 | 100 | varies | 29-34% |
| Entra-Intune | 88 | 88 | 8 | — |

### Open Items

- **List composite decomposition**: v1 stub uses one-cluster-per-value; future: cross-value template extraction
- **Anti-unification**: v1 path-by-path comparison; future: deeper structural anti-unification
- **Token estimation**: `len(str) / 4` approximation; future: tiktoken cl100k_base
- **FK detection**: v1 returns empty dict; future: detect foreign keys from value overlap across types
- **Additional adapters**: XML/CLI normalisation planned for Phase 3 of overall decoct roadmap
