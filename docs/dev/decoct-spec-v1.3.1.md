# Decoct: Semantic Compression Pipeline — v1.3.1 Implementation Spec

**Version:** 1.3.1
**Author:** Enable Network Services / decoct project
**Status:** Implementation-ready for the v1 core

## Document Context

This spec replaces v1.3. It tightens the specification in areas identified during review: scalar-like classification of decomposed composites, the reserved-form collision boundary in `instance_attrs`, null handling in reference collections, subclass gain accounting, structural validation edge cases, naming ordinal strategy, and value-representative semantics in canonical equality.

### What changed from v1.3

| Issue | v1.3.1 fix |
|-------|------------|
| `composite_template_ref` could theoretically pass `is_scalar_like` and enter the phone book | Stated explicitly: `composite_template_ref` is **never** scalar-like, regardless of statistical profile. See §1.3 and §7.3. |
| `IS_ENCODED_C_TEMPLATE_VALUE` could collide with a literal map matching the reserved `{template, delta?}` shape | Documented as a known limitation. Literal maps matching the exact reserved shape on template-capable paths are not supported as C values. Adapters must model such data differently. See §9.1. |
| Null elements in reference-typed collections had no ruling | Null elements within reference collections are silently dropped during `NORMALIZE_REF_TARGETS()`. A field whose entire value is `null` emits no relationship. See §2.5. |
| Subclass gain calculation omitted Tier B structural overhead per subclass | Added `SUBCLASS_OVERHEAD_TOKENS` constant to `TOKEN_ESTIMATE_SUBCLASS`. See §6.3. |
| Stored values in `base_attrs` and `item_lookup` were implicitly treated as canonical despite being arbitrary representatives | Documented: stored values are representatives of their `CANONICAL_EQUAL` equivalence class, not necessarily byte-identical to every entity's value. Reconstruction uses `CANONICAL_EQUAL` for validation. See §2.4. |
| Structural validation check 7 did not catch empty schema with non-empty records | Added converse density check. See §10.2. |
| Structural validation check 9 did not verify that B composite delta entities actually hold a template-ref at the delta path | Added template-ref presence check. See §10.2. |
| `instance_attrs` lacked an explicit statement on opaque values vs the reserved encoding | `instance_attrs` values are opaque YAML; the only reserved form is `{template, delta?}` on template-capable paths. Everything else is a literal value. See §7.3. |
| Naming ordinal was always appended even when the human-readable portion was unique | Ordinal suffix is now collision-resolution only: appended only when the human-readable base would otherwise collide. See §12. |
| Tier C example did not annotate the disjoint-path case (entity in both `instance_attrs` and `overrides`) | Added annotation to §8.3. |

### Lineage

v1.3 (was labelled v1.2.2) introduced:

* Separation of final emission roles from physical encodings.
* Tier C `instance_data` / `instance_attrs` split.
* Composite template pruning by entities covered.
* Normative `CANONICAL_EQUAL`, `VALUE_KEY`, `ITEM_KEY`.
* `NORMALIZE_REF_TARGETS()` for reference-typed collections.
* Deterministic frequent-bundle subclass extraction replacing undefined clustering.
* Structural validation against serialized tier files.
* Naming as a design requirement.

v1.2.1 introduced:

* Relationship deduplication.
* Small-group floor for the final role classifier.
* Configurable anti-unification merge threshold.
* Composite template singleton pruning.
* `anti_unify_deltas` definition (superseded in v1.3 by frequent-bundle extraction).
* Structural invariant checks.
* `compress_id_ranges` format.
* `core/types.py`.
* `max_inheritance_depth` as assertion.
* `base_only_ratio` diagnostic.

## 1. Overview

Decoct transforms heterogeneous infrastructure data into a tiered semantic representation optimized for selective LLM loading and exact reconstruction.

### 1.1 v1.3.1 scope

v1.3.1 is a compiler/validator for a tiered YAML representation. It defines:

* canonicalization into an entity graph,
* type discovery,
* composite decomposition,
* class extraction,
* delta compression,
* normalization into Tier A / B / C YAML,
* exhaustive reconstruction validation.

v1.3.1 does not define the runtime tool/API by which an LLM asks for additional tiers. The emitted format is stable enough for that later contract, but the contract itself is deferred.

### 1.2 Canonical model

The canonical graph is:

* `E`: entities
* `A(e)`: non-reference attributes only
* `R`: typed relationships `(source_id, label, target_id)`

If a schema says a field is a reference, that field is normalized into `R`, not kept as an attribute.

Reference-typed collections emit one relationship per unique normalized target. In v1, direct relationship collections have **set semantics**: order and multiplicity are not preserved in `R`. If order or multiplicity is semantically important, the adapter must model that source structure as child entities with ordinal attributes rather than as direct relationships.

The entity graph deduplicates relationships: `G.add_relationship()` is idempotent on the triple `(source_id, label, target_id)`. This prevents duplicates when adapter `extract_refs()` overlaps with relationships already emitted by the typed schema walk.

Examples:

* `isis.level = 2` → attribute
* `acl.rules = [...]` → composite attribute
* `pe_primary = PE01` → relationship `(BNG001, pe_primary, PE01)`
* containment of interface by router → relationship `(BNG001, contains, BNG001-Gi0/0/0)`

### 1.3 Final emission roles, bootstrap signals, and physical encodings

Final emission roles are semantic ownership classes. They are not identical to the serialized Tier C layout.

**Final emission roles**

| Role | Meaning |
|------|---------|
| `A_BASE` | Universal constant for an entity type |
| `B` | Type-owned attribute that is compressible via base/class/subclass/override structure |
| `C` | Instance-owned non-reference attribute |
| `R` | Relationship `(source_id, label, target_id)` |

A path has exactly one final role within a discovered type.

**Physical encodings**

| Encoding | Used for | Serialized in |
|----------|----------|---------------|
| `base/class/subclass` templates | `A_BASE` and shared `B` structure | Tier B |
| `overrides` | Per-instance residual `B` differences only | Tier C |
| `instance_data` phone book | Dense scalar-like `C` paths with `coverage == 1.0` | Tier C |
| `instance_attrs` | All other `C` paths: sparse scalar, explicit-null sparse, direct composite, or template-backed composite | Tier C |
| `relationship_store` | `R` | Tier C |

`scalar-like` means JSON scalar or enum values: string, number, boolean, null, enum. **`composite_template_ref` is never scalar-like**, regardless of its statistical profile. A decomposed composite path that reclassifies to C with coverage == 1.0 is routed to `instance_attrs`, not `instance_data`, because it requires template expansion during reconstruction.

Rules:

1. `C` does **not** mean "goes in the phone book."
2. `instance_data` never represents absence. Omission is represented only by not having a path in `instance_attrs`.
3. Literal `null` is a valid scalar value. It is distinct from absence.
4. `overrides` are `B`-only.
5. `instance_attrs` are `C`-only.
6. `instance_attrs` values are **opaque YAML**. The only reserved form is the `{template, delta?}` encoding on template-capable paths (see §9.1). Every other value is treated as a literal.
7. For a given type, a path may appear in exactly one of:
   * Tier B template space,
   * Tier C `instance_data.schema`,
   * Tier C `instance_attrs`.

**Bootstrap signals**

Bootstrap signals are used only during Phase 3 type refinement.

| Signal | Meaning |
|--------|---------|
| `VALUE_SIGNAL` | Use literal value in type fingerprint |
| `PRESENCE_SIGNAL` | Use existence only in type fingerprint |
| `NONE` | Do not use in type fingerprint |

A sparse or low-entropy attribute may still be `B` or `C` for final emission while serving as a bootstrap signal during refinement.

### 1.4 Pipeline

```text
RAW DATA
   │
   ▼
PHASE 1: CANONICALISE
(entity graph G = entities + non-reference attrs + relationships)
(relationship deduplication on (source, label, target))
(null elements in reference collections silently dropped)
   │
   ▼
PHASE 2+3: BOOTSTRAP LOOP
(seed types → per-type profiling → type refinement)
(final roles + bootstrap signals separated)
   │
   ▼
PHASE 3.5: COMPOSITE DECOMPOSITION
(all composites above threshold → templates + deltas)
(template pruning uses entities covered, not distinct values)
(preserve original composite values for validation)
(re-profile decomposed attributes with fresh stats)
   │
   ▼
PHASE 4: CLASS EXTRACTION
(greedy partial frequent-template extractor on Tier B)
(base class = A_BASE + universal B)
   │
   ▼
PHASE 5: DELTA COMPRESSION
(Tier B residuals only)
(deterministic subclass promotion over concrete delta bundles)
(subclass gain includes Tier B structural overhead)
(parent membership inclusive)
(max depth = 2 enforced as assertion, not config)
   │
   ▼
PHASE 6: INVERSION & NORMALISATION
(class assignments, subclass assignments,
 Tier C phone book (dense scalar-like C only),
 Tier C instance_attrs (all other C),
 relationship store, FK detection)
   │
   ▼
PHASE 7: ASSEMBLY & ASSERTIONS
(Tier A / B / C YAML)
(structural invariant checks)
(base_only_ratio diagnostic)
   │
   ▼
VALIDATION: EXHAUSTIVE RECONSTRUCTION
(structural invariants first, then per-entity fidelity)
(non-reference attributes + relationships)
(compares against original composites shadow)
```

## 2. Phase 1 — Canonicalise

### 2.1 Purpose

Transform source data into a uniform entity graph with:

* clean entity boundaries,
* child subtree removal,
* reference normalization into relationships,
* composite value preservation,
* relationship deduplication.

### 2.2 Adapter requirements

Adapters must provide:

* `canonical_id(instance, entity_root) -> str`
* `type_hint(entity_root) -> optional[str]`
* `extract_refs(instance, schema, exclude_subtrees=...) -> [(label, target_id)]`

Rules:

* IDs must be canonical stable strings.
* `exclude_subtrees` means "do not descend into these subtrees during reference extraction." The adapter must not inspect or traverse excluded child subtrees when scanning for references. It does not filter the output by target — a reference whose target happens to be within an excluded subtree is still emitted if discovered from outside that subtree.
* If the schema directly marks a field as reference-typed, canonicalization itself emits the relationship; adapters are only for explicit or inferred references not already captured by the typed walk. Duplicates are safe because `G.add_relationship()` deduplicates on the full triple.
* The order of references returned by `extract_refs()` is not semantically relevant. The canonical graph and later assembly stages sort deterministically.

### 2.3 Entity boundary handling

Unchanged in principle from v1.1:

* list nodes with keys,
* resource boundaries,
* adapter hints,
* depth cutoff.

When a child subtree becomes its own entity, that subtree is removed from the parent's attribute space and replaced by containment relationships.

### 2.4 Canonical serialization, hashing, and equality

```python
CANONICAL_KEY(value):
  """Authoritative equality key for grouping and ordering."""
  return json.dumps(
    encode_canonical(value),   # must handle CompositeValue, tuples, enums, etc.
    sort_keys=True,
    separators=(',', ':'),
    ensure_ascii=True
  )

STABLE_CONTENT_HASH(value):
  """Deterministic hash for identifiers and ordering only."""
  return hashlib.sha256(CANONICAL_KEY(value).encode()).hexdigest()

CANONICAL_EQUAL(a, b):
  return CANONICAL_KEY(a) == CANONICAL_KEY(b)

VALUE_KEY(value):
  return CANONICAL_KEY(value)

ITEM_KEY(path, value):
  return (path, CANONICAL_KEY(value))
```

Important:

* Algorithms use `CANONICAL_KEY()` for equivalence classes.
* `STABLE_CONTENT_HASH()` is never the sole correctness key.
* Any `Counter`, `set`, `dict` key, bundle candidate, or equality test that operates on attribute values must use `VALUE_KEY`, `ITEM_KEY`, or `CANONICAL_EQUAL`.
* Raw Python object hash/equality is not authoritative.

**Value-representative semantics (v1.3.1):** When multiple values are `CANONICAL_EQUAL`, the pipeline stores a single representative via `deep_copy` of the first-seen value. This applies to `base_attrs` in Phase 4, `item_lookup` in Phases 4 and 5, and `value_lookup` in Phase 3.5. Representatives are not necessarily byte-identical to every entity's original value in the Python runtime (e.g. `1` vs `1.0` in languages that distinguish them). This is correct because reconstruction validation uses `CANONICAL_EQUAL`, not Python identity or equality. Implementations must ensure that `encode_canonical()` normalizes such distinctions so that `CANONICAL_KEY` is truly authoritative.

### 2.5 Canonicalization algorithm

```python
NORMALIZE_REF_TARGETS(value):
  """
  Accepts scalar or collection-valued reference fields and returns a
  deterministic sorted list of unique canonical target IDs.

  Null handling:
    - If value is None, returns [] (no relationship emitted).
    - Null elements within a collection are silently dropped.
      A reference collection [PE01, null, PE02] yields [PE01, PE02].
    - If all elements are null, returns [].
  """
  if value is None:
    return []

  if is_collection(value):
    targets ← sorted(unique(
      normalize_ref_target(v) for v in value
      if v is not None
    ))
    return targets

  return [normalize_ref_target(value)]
```

```python
CANONICALISE(sources):
  G ← empty entity graph
  # G.add_relationship() deduplicates on (source_id, label, target_id).
  # Calling it twice with the same triple is a no-op.

  for each (source, adapter) in sources:
    schema ← adapter.load_schema(source)
    roots ← detect_entity_boundaries(schema, source)
    raw_tree ← adapter.parse(source, schema)

    for each entity_root in roots:
      child_roots ← [r for r in roots if r.is_descendant_of(entity_root) and r != entity_root]

      for each instance in raw_tree.select(entity_root):
        e ← Entity(id=adapter.canonical_id(instance, entity_root))
        e.schema_type_hint ← adapter.type_hint(entity_root)

        attrs, containment_edges ← flatten_with_entity_removal(
          instance, entity_root, schema, child_roots
        )

        for each (path, value, type) in attrs:
          if type == reference:
            for target_id in NORMALIZE_REF_TARGETS(value):
              G.add_relationship(e.id, path, target_id)
          else:
            if type.is_collection():
              value ← make_composite_value(value, type)
            e.attributes[path] ← Attribute(path, value, type, source)

        for each (label, target_id) in containment_edges:
          G.add_relationship(e.id, label, target_id)

        # Adapter refs may overlap with typed-walk relationships.
        # Deduplication in G.add_relationship() makes this safe.
        for each (label, target_id) in adapter.extract_refs(
            instance, schema, exclude_subtrees=child_roots):
          G.add_relationship(e.id, label, target_id)

        G.add_entity(e)

  return G
```

v1 rule on reference collections: order and multiplicity are not preserved in `R`. If the source semantics require either, model the structure as entities and attributes, not as direct relationships.

## 3. Phases 2+3 — Bootstrap Loop

### 3.1 Purpose

Discover stable entity types and assign final emission roles (`A_BASE`, `B`, `C`) for non-reference attributes.

### 3.2 Phase 2a — Coarse type seeding

Unchanged in shape from v1.1:

* schema hints first,
* attribute-presence fingerprints for unhinted entities,
* merge very small groups into nearest larger group if similar enough,
* deterministic ordering only.

### 3.3 Phase 2b — Per-type profiling

Profiles are computed over non-reference attributes only.

```python
AttributeProfile:
  path
  cardinality
  entropy
  entropy_norm
  coverage
  value_length_mean
  value_length_var
  attribute_type
  final_role      # A_BASE | B | C
  bootstrap_role  # VALUE_SIGNAL | PRESENCE_SIGNAL | NONE
  entity_type
```

### 3.4 Final role classifier

```python
CLASSIFY_FINAL_ROLE(H_norm, cardinality, n_entities, coverage, len_mean, attribute_type):
  # True universal constants only
  if coverage == 1.0 and cardinality == 1:
    return (A_BASE, 1.0)

  # High-entropy or very wide attributes
  # Ratio test only applies above a floor.
  # For very small groups, absolute thresholds prevent premature C classification.
  if n_entities >= SMALL_GROUP_FLOOR:
    if cardinality > 0.5 * n_entities or H_norm > 0.8:
      return (C, min(1.0, H_norm))
  else:
    # Below the floor, only classify as C if cardinality is genuinely high
    # or entropy is unambiguously instance-level.
    if cardinality >= n_entities or H_norm > 0.9:
      return (C, min(1.0, H_norm))

  # Long low-cardinality values are still too expensive inline
  if len_mean > 200 and cardinality < sqrt(n_entities):
    return (C, 0.6)

  # Everything else is class-compressible in v1
  return (B, max(0.5, 1.0 - H_norm))
```

`SMALL_GROUP_FLOOR` defaults to `8`. Below this threshold, the ratio test `cardinality > 0.5 * n_entities` is replaced with stricter absolute checks. This prevents, for example, 3 distinct values across 4 entities from being classified as C when they would compress well as class attributes.

### 3.5 Bootstrap signal classifier

```python
CLASSIFY_BOOTSTRAP_ROLE(profile):
  # True constants can help define type
  if profile.final_role == A_BASE:
    return VALUE_SIGNAL

  # Sparse presence often discriminates type even if it is not a constant
  if profile.coverage < 0.2:
    return PRESENCE_SIGNAL

  # Low-cardinality, low-entropy attributes can discriminate by value
  if profile.cardinality <= 3 and profile.coverage > 0.95 and profile.entropy_norm < 0.3:
    return VALUE_SIGNAL

  return NONE
```

Relationship labels also participate in type refinement as `PRESENCE_SIGNAL`s.

### 3.6 Type refinement

```python
REFINE_TYPES(G, type_map, profiles, config):
  new_type_map ← {}

  for each (type_id, entities) in type_map:
    type_profiles ← profiles[type_id]

    signal_paths ← sorted([
      p for p, prof in type_profiles.items()
      if prof.bootstrap_role != NONE
    ])

    rel_labels ← sorted(unique_relationship_labels_from_entities(G, entities))

    fingerprints ← {}

    for each entity e in sorted(entities, key=lambda x: x.id):
      fp_parts ← []

      for p in signal_paths:
        prof ← type_profiles[p]
        if prof.bootstrap_role == VALUE_SIGNAL:
          if p in e.attributes:
            fp_parts.append((p, CANONICAL_KEY(e.attributes[p].value)))
        elif prof.bootstrap_role == PRESENCE_SIGNAL:
          if p in e.attributes:
            fp_parts.append((p, '__EXISTS__'))

      for label in rel_labels:
        if G.has_relationship_from(e.id, label):
          fp_parts.append((f"REL::{label}", '__EXISTS__'))

      fingerprints[e.id] ← tuple(fp_parts)

    sub_clusters ← group_by(
      sorted(entities, key=lambda e: e.id),
      key=lambda e: fingerprints[e.id]
    )

    if len(sub_clusters) == 1:
      new_type_map[type_id] ← entities
      continue

    merged ← []
    for each cluster C in sub_clusters in canonical order:
      reps ← sorted(C, key=lambda e: e.id)[:min(5, len(C))]
      placed ← False

      for each group M in merged:
        templates ← [anti_unify(r1, r2) for r1 in reps for r2 in M.representatives]
        avg_var_count ← mean(count_variables(t) for t in templates)

        if avg_var_count <= config.max_anti_unify_variables:
          M.add_all(C)
          M.representatives ← sorted(M.entities, key=lambda e: e.id)[:5]
          placed ← True
          break

      if not placed:
        merged.append(ClusterGroup(C, reps))

    if len(merged) == 1:
      new_type_map[type_id] ← entities
    else:
      for i, group in enumerate(merged):
        refined_name ← derive_type_name(group, base_name=type_id, ordinal=i)
        new_type_map[refined_name] ← sorted(group.entities, key=lambda e: e.id)

  return new_type_map, build_type_topology(G, new_type_map)
```

### 3.7 Convergence loop

Unchanged in shape:

* max 5 iterations,
* compare entity → type assignment map,
* final re-profile on converged types.

## 4. Phase 3.5 — Composite Value Decomposition

### 4.1 Purpose

Decompose all high-cardinality composite attributes before class extraction.

### 4.2 v1.3.1 rules

* Applies to all composite attributes above `composite_decompose_threshold`.
* Preserves original composite values in a shadow map for validation.
* Re-profiles decomposed attributes using fresh statistics.
* Template equality/grouping uses `CANONICAL_KEY()`.
* Template pruning threshold counts **entities covered**, not distinct composite values.
* If a retained cluster covers fewer entities than `min_composite_template_members`, those entities retain their original inline composite values and no template is emitted for that cluster.
* After decomposition, the path may still classify as either `B` or `C`. Physical encoding is decided later in Phase 6.

### 4.3 Algorithm

`cluster_and_anti_unify_composites()` must be deterministic. At minimum:

* input distinct values in deterministic order,
* each distinct value belongs to exactly one cluster,
* cluster order is deterministic,
* template ids are assigned in cluster order,
* tie-breaking is deterministic.

```python
DECOMPOSE_COMPOSITES(G, type_map, profiles, config):
  template_index ← {}             # template_id -> CompositeTemplate
  templates_by_type_path ← {}     # (type_id, path) -> [template_id, ...]
  composite_deltas ← {}           # (entity_id, path) -> delta
  original_composite_values ← {}  # (entity_id, path) -> original CompositeValue

  for each (type_id, entities) in type_map:
    type_profiles ← profiles[type_id]

    composite_paths ← [
      p for p, prof in type_profiles.items()
      if prof.attribute_type.is_collection()
      and prof.cardinality > config.composite_decompose_threshold
    ]

    for each path in sorted(composite_paths):
      # Preserve originals
      for each e in entities:
        if path in e.attributes and isinstance(e.attributes[path].value, CompositeValue):
          original_composite_values[(e.id, path)] ← deep_copy(e.attributes[path].value)

      value_support ← Counter(
        VALUE_KEY(e.attributes[path].value)
        for e in entities if path in e.attributes
      )

      value_lookup ← {}
      for v in [e.attributes[path].value for e in entities if path in e.attributes]:
        k ← VALUE_KEY(v)
        if k not in value_lookup:
          value_lookup[k] ← deep_copy(v)

      distinct_values ← [
        value_lookup[k]
        for k in sorted(value_lookup.keys())
      ]

      if len(distinct_values) <= 1:
        continue

      clusters ← cluster_and_anti_unify_composites(distinct_values)

      local_ids ← []
      covered_value_keys ← set()
      next_template_idx ← 0

      for each (template, members) in clusters:
        member_keys ← [VALUE_KEY(m) for m in members]
        covered_entity_count ← sum(value_support[k] for k in member_keys)

        # Threshold counts entities covered, not distinct values
        if covered_entity_count < config.min_composite_template_members:
          continue

        template_id ← f"{type_id}.{path}.T{next_template_idx}"
        next_template_idx += 1

        ct ← CompositeTemplate(
          id=template_id,
          content=template.common_elements,
          variable_positions=template.variable_positions
        )
        template_index[template_id] ← ct
        local_ids.append(template_id)
        covered_value_keys |= set(member_keys)

      templates_by_type_path[(type_id, path)] ← local_ids

      if not local_ids:
        continue

      for each e in entities:
        if path not in e.attributes:
          continue

        value ← e.attributes[path].value
        value_key ← VALUE_KEY(value)

        if value_key not in covered_value_keys:
          continue

        best_template, delta ← find_best_template_match(
          value,
          [template_index[tid] for tid in local_ids]
        )

        e.attributes[path] ← Attribute(
          path=path,
          value=best_template.id,
          type='composite_template_ref',
          source=e.attributes[path].source
        )

        if delta:
          composite_deltas[(e.id, path)] ← delta

      # Fresh re-profile after decomposition
      type_profiles[path] ← reprofile_decomposed_attribute(
        entities=entities,
        path=path,
        old_profile=type_profiles[path]
      )

  return G, template_index, templates_by_type_path, composite_deltas, original_composite_values, profiles
```

### 4.4 Re-profile after decomposition

```python
REPROFILE_DECOMPOSED_ATTRIBUTE(entities, path, old_profile):
  current_values ← [e.attributes[path].value for e in entities if path in e.attributes]
  freq ← Counter(VALUE_KEY(v) for v in current_values)
  cardinality ← len(freq)
  coverage ← len(current_values) / len(entities)
  entropy ← shannon(freq)
  entropy_norm ← entropy / log2(cardinality) if cardinality > 1 else 0
  len_mean ← mean(token_estimate_value(v) for v in current_values)
  len_var ← variance(token_estimate_value(v) for v in current_values)

  final_role, confidence ← CLASSIFY_FINAL_ROLE(
    entropy_norm, cardinality, len(entities), coverage, len_mean, 'composite_template_ref'
  )

  tmp_profile ← AttributeProfile(
    path=path,
    cardinality=cardinality,
    entropy=entropy,
    entropy_norm=entropy_norm,
    coverage=coverage,
    value_length_mean=len_mean,
    value_length_var=len_var,
    attribute_type='composite_template_ref',
    final_role=final_role,
    bootstrap_role=NONE,
    entity_type=old_profile.entity_type
  )

  bootstrap_role ← CLASSIFY_BOOTSTRAP_ROLE(tmp_profile)

  return AttributeProfile(
    path=path,
    cardinality=cardinality,
    entropy=entropy,
    entropy_norm=entropy_norm,
    coverage=coverage,
    value_length_mean=len_mean,
    value_length_var=len_var,
    attribute_type='composite_template_ref',
    final_role=final_role,
    bootstrap_role=bootstrap_role,
    entity_type=old_profile.entity_type
  )
```

## 5. Phase 4 — Class Extraction

### 5.1 Purpose

Extract partial Tier B templates that cover meaningful repeated structure without forcing exact vector equality.

### 5.2 Design

v1.3.1 classes are built from:

* `base_class = A_BASE + universal B`
* `class own_attrs = a frequent Tier B bundle`
* unmodeled residual Tier B differences remain for Phase 5 deltas

This replaces the v1.1 exact-vector grouping.

**Implementation note — greedy set-cover behaviour:** The greedy extractor assigns each entity to the first class whose bundle it satisfies. An entity whose residual B vector is a superset of two different candidate bundles will be assigned to whichever bundle is picked first (highest gain). This is standard greedy set-cover behaviour. The second bundle's support count drops accordingly, which may cause it to fall below `min_class_support` and be discarded. This is intentional — the algorithm favours the highest-gain bundle at each step.

**Implementation note — candidate enumeration scaling:** Candidate generation (§5.5) enumerates all combinations up to `max_class_bundle_size` across residual B items. With `max_class_bundle_size=3` and `k` distinct `(path, value)` pairs per entity across `n` entities, worst-case counter increments are `n × (C(k,1) + C(k,2) + C(k,3))`. For typical infrastructure data (1000 entities, ~50 distinct pairs), this is approximately 21M increments — acceptable for v1. If profiling reveals bottlenecks on larger datasets, an FP-growth or similar frequent-itemset algorithm can replace the brute-force enumeration in v2.

### 5.3 Candidate generation

For each type:

* build each entity's residual Tier B itemset as canonical item keys `(path, VALUE_KEY(value))` excluding `base_class`,
* enumerate frequent bundles of size `1..max_class_bundle_size`,
* support must be at least `min_class_support`,
* only keep bundles with positive local compression gain.

```python
MATERIALIZE_BUNDLE(bundle_keys, item_lookup):
  return {
    path: deep_copy(item_lookup[(path, value_key)])
    for (path, value_key) in sorted(bundle_keys)
  }

BUNDLE_GAIN(bundle_keys, support_count, item_lookup):
  attrs ← MATERIALIZE_BUNDLE(bundle_keys, item_lookup)
  repeated_cost ← support_count * token_estimate_attrs(attrs)
  templated_cost ← token_estimate_class(attrs) + support_count * TOKEN_COST_CLASS_REF
  return repeated_cost - templated_cost
```

### 5.4 Greedy extractor

```python
EXTRACT_CLASSES(type_map, G, profiles, config):
  hierarchies ← {}

  for each (type_id, entities) in type_map:
    type_profiles ← profiles[type_id]

    a_base_paths ← sorted([p for p, prof in type_profiles.items() if prof.final_role == A_BASE])
    tier_b_paths ← sorted([p for p, prof in type_profiles.items() if prof.final_role == B])

    # Base class = A_BASE + universal B
    base_attrs ← {}
    for p in a_base_paths:
      base_attrs[p] ← deep_copy(entities[0].attributes[p].value)

    for p in tier_b_paths:
      values ← [e.attributes[p].value for e in entities if p in e.attributes]
      if len(values) == len(entities) and len(set(VALUE_KEY(v) for v in values)) == 1:
        base_attrs[p] ← deep_copy(values[0])

    residual_b_paths ← [p for p in tier_b_paths if p not in base_attrs]

    item_lookup ← {}
    vectors ← {}

    for each e in sorted(entities, key=lambda x: x.id):
      items ← []
      for p in residual_b_paths:
        if p in e.attributes:
          k ← ITEM_KEY(p, e.attributes[p].value)
          if k not in item_lookup:
            item_lookup[k] ← deep_copy(e.attributes[p].value)
          items.append(k)

      vectors[e.id] ← frozenset(items)

    unassigned ← [e.id for e in sorted(entities, key=lambda x: x.id)]
    classes ← {}

    while True:
      candidates ← GENERATE_BUNDLE_CANDIDATES(
        entity_ids=unassigned,
        vectors=vectors,
        item_lookup=item_lookup,
        min_support=config.min_class_support,
        max_bundle_size=config.max_class_bundle_size
      )

      if not candidates:
        break

      candidates ← sorted(
        candidates,
        key=lambda c: (
          -c.gain,
          -len(c.bundle),
          CANONICAL_KEY(sorted(c.bundle))
        )
      )

      best ← candidates[0]
      if best.gain <= 0:
        break

      covered ← sorted(
        [eid for eid in unassigned if best.bundle.issubset(vectors[eid])]
      )

      bundle_attrs ← MATERIALIZE_BUNDLE(best.bundle, item_lookup)
      class_name ← derive_class_name(bundle_attrs, type_id)

      classes[class_name] ← ClassDef(
        name=class_name,
        inherits='base',
        own_attrs=bundle_attrs,
        entity_ids=covered,     # inclusive membership
        overrides={}
      )

      unassigned ← [eid for eid in unassigned if eid not in set(covered)]

    if unassigned:
      classes['_base_only'] ← ClassDef(
        name='_base_only',
        inherits='base',
        own_attrs={},
        entity_ids=sorted(unassigned),
        overrides={}
      )

    hierarchies[type_id] ← ClassHierarchy(
      base_class=BaseClass(attrs=base_attrs),
      classes=classes,
      subclasses={}
    )

  return hierarchies
```

### 5.5 Candidate enumeration

```python
GENERATE_BUNDLE_CANDIDATES(entity_ids, vectors, item_lookup, min_support, max_bundle_size):
  counts ← Counter()

  for eid in entity_ids:
    items ← sorted(vectors[eid], key=lambda kv: (kv[0], kv[1]))
    for size in range(1, min(max_bundle_size, len(items)) + 1):
      for subset in combinations(items, size):
        counts[frozenset(subset)] += 1

  candidates ← []
  for bundle, raw_support in counts.items():
    if raw_support < min_support:
      continue

    covered ← [eid for eid in entity_ids if bundle.issubset(vectors[eid])]
    support ← len(covered)
    gain ← BUNDLE_GAIN(bundle, support, item_lookup)

    if gain > 0:
      candidates.append(BundleCandidate(
        bundle=bundle,
        covered=sorted(covered),
        gain=gain
      ))

  return candidates
```

### 5.6 Mixins

Mixins are not supported in v1.3.1. They are deferred to v2.

## 6. Phase 5 — Delta Compression

### 6.1 Purpose

Compress residual Tier B differences within each primary class and promote positive-gain shared concrete additions into direct subclasses.

### 6.2 Rules

* Eligible paths = Tier B only.
* Parent class membership is inclusive.
* Any primary class may have multiple direct subclasses.
* Subclasses cannot have children. This is a hard architectural constraint in v1, not a configurable parameter. It is enforced as an assertion in Phase 7.
* An entity may belong to at most one subclass.
* Subclasses only promote shared **concrete** delta items `(path, value)`.
* Shared deletions (`ABSENT`) are not promoted into subclass templates in v1. They remain per-instance overrides.
* An entity may have Tier B attributes at paths that appear in neither `base_class` nor its primary class `own_attrs`; these remain legal residual B values and are represented as overrides or subclass own_attrs if promoted.

### 6.3 Algorithm

Phase 5 reuses the same frequent-bundle machinery as Phase 4, but over per-class delta itemsets.

```python
SUBCLASS_OVERHEAD_TOKENS = 12
  # Fixed per-subclass cost in the Tier B subclasses section:
  # the parent, own_attrs, and instance_count keys plus YAML structural tokens.
  # This prevents marginal-gain subclasses whose template savings are consumed
  # by the overhead of existing as a subclass entry.

TOKEN_ESTIMATE_SUBCLASS(template_attrs, covered_entity_ids):
  return (
    SUBCLASS_OVERHEAD_TOKENS +
    token_estimate_class(template_attrs) +
    token_estimate_id_set(covered_entity_ids)
  )
```

```python
DELTA_COMPRESS(hierarchies, G, profiles, config):
  for each (type_id, hierarchy) in hierarchies:
    type_profiles ← profiles[type_id]
    eligible_paths ← {
      p for p, prof in type_profiles.items()
      if prof.final_role == B
    }

    for each class_def in sorted(hierarchy.classes.values(), key=lambda c: c.name):
      parent_template ← {}
      parent_template.update(hierarchy.base_class.attrs)
      parent_template.update(class_def.own_attrs)
      parent_template ← {
        p: v for p, v in parent_template.items()
        if p in eligible_paths
      }

      raw_deltas ← {}
      vectors ← {}
      item_lookup ← {}

      for eid in sorted(class_def.entity_ids):
        e ← G.get_entity(eid)
        delta ← COMPUTE_DELTA_RESTRICTED(e, parent_template, eligible_paths)
        if not delta:
          continue

        raw_deltas[eid] ← delta

        items ← []
        for each (path, value) in sorted(delta.items()):
          if value == ABSENT:
            continue   # deletions never become subclass own_attrs in v1

          k ← ITEM_KEY(path, value)
          if k not in item_lookup:
            item_lookup[k] ← deep_copy(value)
          items.append(k)

        vectors[eid] ← frozenset(items)

      remaining ← sorted(raw_deltas.keys())
      class_def.overrides = {}

      while True:
        candidates ← GENERATE_BUNDLE_CANDIDATES(
          entity_ids=remaining,
          vectors=vectors,
          item_lookup=item_lookup,
          min_support=config.min_subclass_size,
          max_bundle_size=config.max_class_bundle_size
        )

        scored ← []

        for each c in candidates:
          covered ← sorted([
            eid for eid in remaining
            if c.bundle.issubset(vectors.get(eid, frozenset()))
          ])

          template ← MATERIALIZE_BUNDLE(c.bundle, item_lookup)

          residuals ← {}
          for eid in covered:
            residual ← {}
            for each (path, value) in sorted(raw_deltas[eid].items()):
              if path in template and CANONICAL_EQUAL(value, template[path]):
                continue
              residual[path] ← value

            if residual:
              residuals[eid] ← residual

          inline_cost ← sum(
            token_estimate_override(raw_deltas[eid]) for eid in covered
          )

          templated_cost ← (
            TOKEN_ESTIMATE_SUBCLASS(template, covered) +
            sum(token_estimate_override(d) for d in residuals.values())
          )

          gain ← inline_cost - templated_cost
          if gain > 0:
            scored.append(SubclassCandidate(
              bundle=c.bundle,
              template=template,
              covered=covered,
              residuals=residuals,
              gain=gain
            ))

        if not scored:
          break

        scored ← sorted(
          scored,
          key=lambda s: (
            -s.gain,
            -len(s.bundle),
            CANONICAL_KEY(sorted(s.bundle))
          )
        )
        best ← scored[0]

        subclass_name ← derive_subclass_name(class_def.name, best.template)

        hierarchy.subclasses[subclass_name] ← SubclassDef(
          name=subclass_name,
          parent_class=class_def.name,
          own_attrs=best.template,
          entity_ids=best.covered,
          overrides=best.residuals
        )

        covered_set ← set(best.covered)
        remaining ← [eid for eid in remaining if eid not in covered_set]

      # Parent overrides only for members not lifted into a subclass
      for eid in remaining:
        class_def.overrides[eid] ← raw_deltas[eid]
```

### 6.4 Delta computation

```python
COMPUTE_DELTA_RESTRICTED(entity, template, eligible_paths):
  delta ← {}
  for each path in sorted(eligible_paths):
    entity_attr ← entity.attributes.get(path)
    template_val ← template.get(path)

    if entity_attr is not None and template_val is not None:
      if not CANONICAL_EQUAL(entity_attr.value, template_val):
        delta[path] ← deep_copy(entity_attr.value)
    elif entity_attr is not None and template_val is None:
      delta[path] ← deep_copy(entity_attr.value)
    elif entity_attr is None and template_val is not None:
      delta[path] ← ABSENT

  return delta
```

## 7. Phase 6 — Inversion & Normalisation

### 7.1 Purpose

Build the Tier C instance layer:

* inclusive parent class assignments,
* subclass assignments,
* dense Tier C phone book,
* sparse / composite Tier C `instance_attrs`,
* relationship store,
* foreign keys for scalar Tier C attributes,
* B-layer composite deltas.

### 7.2 Relationship store

Because references were normalized into `R` in Phase 1 (with deduplication), the relationship store is simple:

```yaml
relationship_store:
  BNG001:
    - {label: pe_primary, target: PE01}
    - {label: pe_secondary, target: PE02}
    - {label: contains, target: BNG001-Gi0/0/0}
```

No special-case attribute/relationship merging is needed.

### 7.3 Build Tier C

`instance_data` is restricted to dense scalar-like `C` paths. All other `C` paths go to `instance_attrs`.

**`composite_template_ref` is never scalar-like** and therefore never enters `instance_data`, even if coverage == 1.0 and cardinality == 1. Such paths require template expansion during reconstruction and must go through `instance_attrs`.

For paths that appear in Tier B `composite_templates`, `instance_attrs` may use the reserved encoded form `{template: <template_id>, delta?: <delta>}` to represent a template-backed composite `C` value. `instance_attrs` values are otherwise **opaque YAML** — any value not matching the reserved form is treated as a literal. See §9.1 for the discriminator and its known limitations.

For raw (non-decomposed) `CompositeValue` attributes classified as C — those below `composite_decompose_threshold` or in a pruned cluster — `ENCODE_C_INSTANCE_VALUE` falls through to the literal path and the composite is serialized directly as a YAML list or map. The YAML serializer and deserializer must preserve this structure faithfully so that reconstruction can `CANONICAL_EQUAL`-compare it against the original.

```python
IS_SCALAR_LIKE(attribute_type):
  """
  Returns True for JSON scalar / enum types.
  composite_template_ref is explicitly excluded.
  """
  if attribute_type == 'composite_template_ref':
    return False

  return attribute_type in SCALAR_TYPES   # string, number, boolean, null, enum
```

```python
SELECT_TIER_C_STORAGE(profile):
  if profile.final_role != C:
    return NONE

  if IS_SCALAR_LIKE(profile.attribute_type) and profile.coverage == 1.0:
    return PHONE_BOOK

  return INSTANCE_ATTRS
```

```python
ENCODE_C_INSTANCE_VALUE(eid, path, entity, composite_deltas_for_type):
  value ← entity.attributes[path].value

  if entity.attributes[path].type == 'composite_template_ref':
    out ← {'template': value}
    if (eid, path) in composite_deltas_for_type:
      out['delta'] ← deep_copy(composite_deltas_for_type[(eid, path)])
    return out

  return deep_copy(value)
```

```python
BUILD_PHONE_BOOK_DENSE(entities, schema_paths):
  if not schema_paths:
    return PhoneBook(schema=[], records={})

  records ← {}
  for each e in sorted(entities, key=lambda x: x.id):
    records[e.id] ← [deep_copy(e.attributes[p].value) for p in schema_paths]

  return PhoneBook(schema=schema_paths, records=records)
```

```python
BUILD_TIER_C(type_id, hierarchy, G, profiles, composite_deltas_for_type):
  type_profiles ← profiles[type_id]
  entities ← sorted(
    [e for e in G.entities if e.discovered_type == type_id],
    key=lambda x: x.id
  )

  # 1. Inclusive parent class assignments
  class_assignments ← {}
  for each class_def in sorted(hierarchy.classes.values(), key=lambda c: c.name):
    class_assignments[class_def.name] ← {
      'instances': compress_id_ranges(sorted(class_def.entity_ids))
    }

  # 2. Subclass assignments
  subclass_assignments ← {}
  for each subclass_def in sorted(hierarchy.subclasses.values(), key=lambda s: s.name):
    subclass_assignments[subclass_def.name] ← {
      'parent': subclass_def.parent_class,
      'instances': compress_id_ranges(sorted(subclass_def.entity_ids))
    }

  # 3. Tier C storage split
  phone_book_paths ← sorted([
    p for p, prof in type_profiles.items()
    if SELECT_TIER_C_STORAGE(prof) == PHONE_BOOK
  ])

  instance_attr_paths ← sorted([
    p for p, prof in type_profiles.items()
    if SELECT_TIER_C_STORAGE(prof) == INSTANCE_ATTRS
  ])

  phone_book ← BUILD_PHONE_BOOK_DENSE(entities, phone_book_paths)

  instance_attrs ← {}
  for each e in entities:
    row ← {}
    for each path in instance_attr_paths:
      if path not in e.attributes:
        continue
      row[path] ← ENCODE_C_INSTANCE_VALUE(
        e.id, path, e, composite_deltas_for_type
      )
    if row:
      instance_attrs[e.id] ← row

  # 4. Relationship store
  relationship_store ← {}
  for each e in entities:
    rels ← sorted(
      [{'label': label, 'target': target_id}
       for (label, target_id) in G.relationships_from(e.id)],
      key=lambda r: (r['label'], r['target'])
    )
    if rels:
      relationship_store[e.id] ← rels

  # 5. Flatten B overrides from parents and subclasses
  overrides ← {}
  for each class_def in sorted(hierarchy.classes.values(), key=lambda c: c.name):
    for eid, delta in sorted(class_def.overrides.items()):
      overrides[eid] ← {'owner': class_def.name, 'delta': delta}

  for each subclass_def in sorted(hierarchy.subclasses.values(), key=lambda s: s.name):
    for eid, delta in sorted(subclass_def.overrides.items()):
      overrides[eid] ← {'owner': subclass_def.name, 'delta': delta}

  # 6. B-layer composite deltas only
  b_composite_deltas ← {}
  for each ((eid, path), delta) in sorted(composite_deltas_for_type.items()):
    if type_profiles[path].final_role != B:
      continue
    b_composite_deltas.setdefault(eid, {})[path] ← {'delta': deep_copy(delta)}

  # 7. FK detection only on scalar Tier C attrs
  fk_map ← detect_foreign_keys_on_scalar_attrs(G, profiles, type_id)

  return TierC(
    class_assignments=class_assignments,
    subclass_assignments=subclass_assignments,
    instance_data=phone_book,
    instance_attrs=instance_attrs,
    relationship_store=relationship_store,
    overrides=overrides,
    b_composite_deltas=b_composite_deltas,
    foreign_keys=fk_map
  )
```

### 7.4 ID range compression

`compress_id_ranges` produces a compact YAML-friendly representation of sorted entity ID lists. Where IDs share a common non-numeric prefix and a contiguous numeric suffix of the same width, consecutive runs are collapsed into range notation.

Rules:

* Input: a sorted list of canonical entity IDs.
* Numeric-suffix grouping requires:
  * identical non-numeric prefix,
  * decimal numeric suffix,
  * identical suffix width.
* Consecutive runs are collapsed into `PREFIX_START..PREFIX_END`, preserving zero-padding.
  * Example: `[BNG001, BNG002, ..., BNG400]` → `[BNG001..BNG400]`
* Non-contiguous IDs or IDs without numeric suffixes are listed individually.
* Mixed ranges and singletons may appear in the same list:
  * `[BNG001..BNG400, BNG405, BNG410..BNG500]`
* The output must be deterministic: same input always produces same output.
* `expand_id_ranges()` is the inverse operation and must round-trip exactly.

```python
COMPRESS_ID_RANGES(sorted_ids):
  if not sorted_ids:
    return []

  result ← []
  groups ← group_by_prefix_width_and_contiguous_suffix(sorted_ids)

  for (prefix, width, start_num, end_num, members) in groups:
    if prefix is None or start_num == end_num:
      result.extend(members)
    else:
      result.append(
        f"{prefix}{str(start_num).zfill(width)}..{prefix}{str(end_num).zfill(width)}"
      )

  return result
```

## 8. Phase 7 — Assembly & Assertions

### 8.1 Tier A

Tier A remains an orientation file:

* type counts,
* type-level topology,
* Tier B / Tier C file refs,
* high-level assertions.

**v1.3.1 assertions include:**

* **Structural invariants** (see §10.2 for the full check list).
* **`base_only_ratio`** per type: the fraction of entities assigned to `_base_only`. This is a diagnostic signal — a high ratio (e.g. `> 0.5`) suggests `min_class_support` or `max_class_bundle_size` may need tuning for that type.
* **Max inheritance depth = 2** enforced as an assertion, not a configurable parameter. If any subclass has a child, assembly fails.

Tier A is not the source of reconstructible per-entity data.

### 8.2 Tier B

```yaml
meta:
  entity_type: bng
  total_instances: 1000
  max_inheritance_depth: 2
  tier_c_ref: bng_instances.yaml

base_class:
  isis.level: 2
  isis.metric_style: wide
  sr.srgb: [16000, 23999]

classes:
  business:
    inherits: base
    own_attrs:
      qos.policy: business-subscriber
    instance_count_inclusive: 350

  premium:
    inherits: base
    own_attrs:
      qos.policy: premium-subscriber
      bgp.peer_template: premium-peer-v4
    instance_count_inclusive: 400

  _base_only:
    inherits: base
    own_attrs: {}
    instance_count_inclusive: 250

subclasses:
  business_jumbo:
    parent: business
    own_attrs:
      interfaces.bundle_ether.mtu: 9200
    instance_count: 10

composite_templates:
  acl.rules:
    bng.acl.rules.T0:
      elements:
        - {seq: 10, action: permit, match: "10.0.0.0/8"}
        - {seq: 20, action: deny, match: "any"}

assertions:
  base_only_ratio: 0.25
```

### 8.3 Tier C

```yaml
meta:
  entity_type: bng
  tier_b_ref: bng_classes.yaml
  total_instances: 1000

class_assignments:
  business: {instances: [BNG401..BNG750]}
  premium:  {instances: [BNG001..BNG400]}
  _base_only: {instances: [BNG751..BNG1000]}

subclass_assignments:
  business_jumbo:
    parent: business
    instances: [BNG741..BNG750]

# Dense scalar-like C paths only (coverage == 1.0, scalar types).
instance_data:
  schema: [loopback_ip, hostname]
  records:
    BNG001: [10.0.1.1, bng-lon-01]
    BNG002: [10.0.1.2, bng-lon-02]

# All other C paths: sparse scalar, explicit-null, direct composite,
# or template-backed composite.
# Values are opaque YAML except for the reserved {template, delta?} form.
instance_attrs:
  BNG042:
    acl.rules:
      template: bng.acl.rules.T0
      delta:
        position_0: {match: "10.1.0.0/16"}
  # BNG847 appears in both instance_attrs (C path: note) and overrides
  # (B path: qos.shaper). This is valid because the paths are disjoint:
  # C paths never appear in overrides and B paths never appear in instance_attrs.
  BNG847:
    note: "temporary shaping override"

relationship_store:
  BNG001:
    - {label: pe_primary, target: PE01}
    - {label: pe_secondary, target: PE02}
    - {label: contains, target: BNG001-Gi0/0/0}

# B-only per-instance deltas.
overrides:
  BNG847:
    owner: business
    delta:
      qos.shaper: 150m

# B-layer composite deltas (separate from C-layer template encoding).
b_composite_deltas:
  BNG741:
    customer_acl:
      delta:
        position_1: {action: deny, match: "192.0.2.0/24"}

foreign_keys:
  loopback_ip: null
```

## 9. Reconstitution

### 9.1 Canonical algorithm

The canonical reconstruction API takes `entity_type` explicitly.

**Reserved-form discriminator and known limitations**

`IS_ENCODED_C_TEMPLATE_VALUE` distinguishes the reserved `{template, delta?}` encoding from literal map values in `instance_attrs`. The discriminator requires: the path appears in `path_template_ids`, the `template` value is a known template ID for that path, and the key set is exactly `{template}` or `{template, delta}`.

**Known limitation:** A literal map C value that (a) sits on a template-capable path, (b) contains exactly one or two keys named `template` and optionally `delta`, and (c) whose `template` value happens to match a known template ID, would be misinterpreted as an encoded composite. This collision is astronomically unlikely in practice — it requires a literal map to accidentally mirror both the reserved key structure and a valid template ID. However, it is formally unresolvable without a type tag. Adapters encountering source data that could produce such values on template-capable paths must model the data differently (e.g. wrapping it in a container key or moving it to a child entity).

```python
IS_ENCODED_C_TEMPLATE_VALUE(path, encoded_value, path_template_ids):
  return (
    path in path_template_ids
    and is_mapping(encoded_value)
    and 'template' in encoded_value
    and set(encoded_value.keys()).issubset({'template', 'delta'})
    and encoded_value['template'] in path_template_ids[path]
  )

MATERIALIZE_C_INSTANCE_VALUE(path, encoded_value, path_template_ids, template_index):
  if IS_ENCODED_C_TEMPLATE_VALUE(path, encoded_value, path_template_ids):
    template ← template_index[encoded_value['template']]
    out ← deep_copy(template.content)

    if 'delta' in encoded_value:
      apply_composite_delta(out, encoded_value['delta'])

    return out

  return deep_copy(encoded_value)
```

```python
RECONSTITUTE_ENTITY(entity_type, entity_id, tier_b, tier_c, template_index):
  """
  Reconstruct non-reference attributes and all relationships.

  Attribute precedence:
    1. base_class
    2. primary class own_attrs
    3. subclass own_attrs (if any)
    4. per-instance B overrides
    5. B-layer composite template expansion + B-layer composite delta application
    6. C-layer instance_attrs
    7. C-layer dense phone-book attributes

  Paths are disjoint by construction:
    * B paths live in template/override space
    * phone_book paths are dense scalar-like C only
    * instance_attrs holds all other C paths

  Relationships:
    * loaded directly from Tier C relationship_store

  If a per-instance B override replaces a template-ref path with a direct value,
  no template expansion occurs for that entity/path.
  """

  attrs ← {}
  path_template_ids ← {
    path: set(template_defs.keys())
    for path, template_defs in tier_b.composite_templates.items()
  }

  # 1. Base class
  attrs.update(deep_copy(tier_b.base_class))

  # 2. Primary class
  class_name ← find_parent_class(entity_id, tier_c.class_assignments)
  class_def ← tier_b.classes[class_name]
  attrs.update(deep_copy(class_def.own_attrs))

  # 3. Subclass, if any
  subclass_name ← find_subclass(entity_id, tier_c.subclass_assignments)
  if subclass_name is not None:
    subclass_def ← tier_b.subclasses[subclass_name]
    attrs.update(deep_copy(subclass_def.own_attrs))

  # 4. Per-instance B overrides
  if entity_id in tier_c.overrides:
    for each (path, value) in sorted(tier_c.overrides[entity_id]['delta'].items()):
      if value == ABSENT:
        attrs.pop(path, None)
      else:
        attrs[path] ← deep_copy(value)

  # 5. Expand B-layer template refs only on known template-capable paths.
  #    If an override replaced a template ref with a direct value, the value
  #    will not be a string matching a template ID, so no expansion occurs.
  for each path in sorted(path_template_ids.keys()):
    if path not in attrs:
      continue

    value ← attrs[path]
    if isinstance(value, str) and value in path_template_ids[path]:
      template ← template_index[value]
      attrs[path] ← deep_copy(template.content)

      if entity_id in tier_c.b_composite_deltas and path in tier_c.b_composite_deltas[entity_id]:
        apply_composite_delta(
          attrs[path],
          tier_c.b_composite_deltas[entity_id][path]['delta']
        )

  # 6. Apply non-phone-book C values (instance_attrs).
  #    Values are opaque YAML except for the reserved {template, delta?} form.
  if entity_id in tier_c.instance_attrs:
    for each (path, encoded_value) in sorted(tier_c.instance_attrs[entity_id].items()):
      attrs[path] ← MATERIALIZE_C_INSTANCE_VALUE(
        path, encoded_value, path_template_ids, template_index
      )

  # 7. Apply dense scalar-like C values (phone book)
  if entity_id in tier_c.instance_data.records:
    record ← tier_c.instance_data.records[entity_id]
    for i, path in enumerate(tier_c.instance_data.schema):
      attrs[path] ← deep_copy(record[i])

  relationships ← []
  if entity_id in tier_c.relationship_store:
    relationships = [
      (edge['label'], edge['target'])
      for edge in tier_c.relationship_store[entity_id]
    ]

  return ReconstructedEntity(
    id=entity_id,
    entity_type=entity_type,
    attributes=attrs,
    relationships=sorted(relationships)
  )
```

### 9.2 Optional wrapper

A future wrapper may resolve `entity_type` from a manifest or lookup index, but that is outside the canonical v1.3.1 algorithm.

## 10. Validation

### 10.1 Scope

Validation is exhaustive and checks:

* structural invariants of the serialized tier format,
* every entity,
* every non-reference attribute,
* every relationship,
* original composite values via the shadow map from Phase 3.5.

### 10.2 Structural invariant checks

These checks run before per-entity reconstruction validation. They verify the consistency of the emitted Tier B/Tier C files themselves.

```python
VALIDATE_STRUCTURAL_INVARIANTS(G, tier_b_files, tier_c_files, template_index):
  errors ← []

  for each type_id in sorted(tier_b_files.keys()):
    tier_b ← tier_b_files[type_id]
    tier_c ← tier_c_files[type_id]

    expected_ids ← sorted([
      e.id for e in G.entities
      if e.discovered_type == type_id
    ])
    expected_set ← set(expected_ids)

    class_ids ← {
      name: set(expand_id_ranges(data['instances']))
      for name, data in sorted(tier_c.class_assignments.items())
    }

    subclass_ids ← {
      name: set(expand_id_ranges(data['instances']))
      for name, data in sorted(tier_c.subclass_assignments.items())
    }

    # 1. No entity appears in more than one primary class
    seen ← set()
    for class_name, ids in sorted(class_ids.items()):
      overlap ← ids & seen
      if overlap:
        errors.append(MultiClassAssignment(type_id, class_name, overlap))
      seen |= ids

    # 2. Primary class coverage is exact
    if seen != expected_set:
      errors.append(ClassCoverageError(type_id, expected_set - seen, seen - expected_set))

    # 3. Subclass parent containment
    for subclass_name, ids in sorted(subclass_ids.items()):
      parent ← tier_c.subclass_assignments[subclass_name]['parent']
      if parent not in class_ids:
        errors.append(InvalidSubclassParent(type_id, subclass_name, parent))
        continue

      orphans ← ids - class_ids[parent]
      if orphans:
        errors.append(SubclassOrphan(type_id, subclass_name, parent, orphans))

    # 4. No entity appears in more than one subclass
    seen_sub ← set()
    for subclass_name, ids in sorted(subclass_ids.items()):
      overlap ← ids & seen_sub
      if overlap:
        errors.append(MultiSubclassAssignment(type_id, subclass_name, overlap))
      seen_sub |= ids

    # 5. Max inheritance depth = 2
    subclass_names ← set(tier_b.subclasses.keys())
    for subclass_name, subclass_def in sorted(tier_b.subclasses.items()):
      if subclass_def.parent_class in subclass_names:
        errors.append(DepthViolation(type_id, subclass_name, [subclass_def.parent_class]))

    # 6. Override owners are valid and owner membership is consistent
    valid_owners ← set(tier_b.classes.keys()) | set(tier_b.subclasses.keys())
    subclass_union ← set().union(*subclass_ids.values()) if subclass_ids else set()

    for eid, override_data in sorted(tier_c.overrides.items()):
      owner ← override_data['owner']
      if owner not in valid_owners:
        errors.append(InvalidOverrideOwner(type_id, eid, owner))
        continue

      if owner in subclass_ids:
        if eid not in subclass_ids[owner]:
          errors.append(OverrideMembershipError(type_id, eid, owner))
      else:
        if eid not in class_ids[owner]:
          errors.append(OverrideMembershipError(type_id, eid, owner))
        if eid in subclass_union:
          errors.append(ParentOverrideOnSubclassMember(type_id, eid, owner))

    # 7. Phone-book schema/records are rectangular and dense
    schema ← tier_c.instance_data.schema
    records ← tier_c.instance_data.records

    for eid, row in sorted(records.items()):
      if len(row) != len(schema):
        errors.append(PhoneBookRowLengthError(type_id, eid, len(schema), len(row)))

    # v1.3.1: both directions of the density contract
    if schema and set(records.keys()) != expected_set:
      errors.append(PhoneBookCoverageError(type_id, expected_set - set(records.keys())))

    if not schema and records:
      errors.append(PhoneBookEmptySchemaWithRecords(type_id, len(records)))

    # 8. No path appears in both phone book and instance_attrs
    schema_set ← set(schema)
    path_template_ids ← {
      path: set(template_defs.keys())
      for path, template_defs in tier_b.composite_templates.items()
    }

    for eid, row in sorted(tier_c.instance_attrs.items()):
      overlap ← set(row.keys()) & schema_set
      if overlap:
        errors.append(DuplicateCPathEncoding(type_id, eid, overlap))

      for path, value in sorted(row.items()):
        if IS_ENCODED_C_TEMPLATE_VALUE(path, value, path_template_ids):
          if value['template'] not in template_index:
            errors.append(UnknownCompositeTemplate(type_id, eid, path, value['template']))
        elif is_mapping(value) and 'template' in value and path in path_template_ids:
          # Looks like a malformed encoded composite value on a template-capable path
          errors.append(MalformedEncodedCompositeValue(type_id, eid, path, value))

    # 9. B composite deltas reference known entities and template-capable paths,
    #    and the entity actually holds a template-ref at that path in the B layer.
    for eid, path_map in sorted(tier_c.b_composite_deltas.items()):
      if eid not in expected_set:
        errors.append(UnknownEntityInCompositeDelta(type_id, eid))
        continue

      for path in sorted(path_map.keys()):
        if path not in path_template_ids:
          errors.append(UnknownCompositeDeltaPath(type_id, eid, path))
          continue

        # v1.3.1: verify the entity's B-layer value at this path is actually a
        # template ref. Reconstruct the B-layer value through the precedence
        # chain (base → class → subclass → override) and check.
        b_value ← resolve_b_layer_value(
          eid, path, tier_b, tier_c
        )
        if b_value is None or not (
          isinstance(b_value, str) and b_value in path_template_ids[path]
        ):
          errors.append(CompositeDeltaOnNonTemplateRef(type_id, eid, path, b_value))

  if errors:
    raise StructuralInvariantError(f"{len(errors)} structural errors", errors)
```

Helper for check 9:

```python
RESOLVE_B_LAYER_VALUE(eid, path, tier_b, tier_c):
  """
  Walk the B-layer precedence chain for a single entity/path
  without performing template expansion. Returns the raw value
  (which should be a template ID string if a B composite delta
  is expected) or None if the path is absent.
  """
  value ← None

  # base_class
  if path in tier_b.base_class:
    value ← tier_b.base_class[path]

  # primary class
  class_name ← find_parent_class(eid, tier_c.class_assignments)
  if class_name and path in tier_b.classes[class_name].own_attrs:
    value ← tier_b.classes[class_name].own_attrs[path]

  # subclass
  subclass_name ← find_subclass(eid, tier_c.subclass_assignments)
  if subclass_name and path in tier_b.subclasses[subclass_name].own_attrs:
    value ← tier_b.subclasses[subclass_name].own_attrs[path]

  # override
  if eid in tier_c.overrides:
    delta ← tier_c.overrides[eid].get('delta', {})
    if path in delta:
      if delta[path] == ABSENT:
        value ← None
      else:
        value ← delta[path]

  return value
```

### 10.3 Per-entity reconstruction validation

Validation must distinguish **absence** from literal `null`.

```python
MISSING ← object()
```

```python
VALIDATE_RECONSTRUCTION(G, hierarchies, tier_b_files, tier_c_files,
                        template_index, original_composite_values):
  # Structural invariants first
  VALIDATE_STRUCTURAL_INVARIANTS(G, tier_b_files, tier_c_files, template_index)

  mismatches ← []

  for each entity e in sorted(G.entities, key=lambda x: x.id):
    entity_type ← e.discovered_type

    reconstructed ← RECONSTITUTE_ENTITY(
      entity_type=entity_type,
      entity_id=e.id,
      tier_b=tier_b_files[entity_type],
      tier_c=tier_c_files[entity_type],
      template_index=template_index
    )

    all_paths ← sorted(set(e.attributes.keys()) | set(reconstructed.attributes.keys()))

    for path in all_paths:
      if (e.id, path) in original_composite_values:
        original_present ← True
        original_val ← original_composite_values[(e.id, path)]
      elif path in e.attributes:
        original_present ← True
        original_val ← e.attributes[path].value
      else:
        original_present ← False
        original_val ← MISSING

      if path in reconstructed.attributes:
        recon_present ← True
        recon_val ← reconstructed.attributes[path]
      else:
        recon_present ← False
        recon_val ← MISSING

      if original_present != recon_present:
        mismatches.append(AttributeMismatch(e.id, path, original_val, recon_val))
        continue

      if original_present and not CANONICAL_EQUAL(original_val, recon_val):
        mismatches.append(AttributeMismatch(e.id, path, original_val, recon_val))

    # Compare relationships
    original_rels ← sorted(G.relationships_from(e.id))
    recon_rels ← sorted(reconstructed.relationships)

    if original_rels != recon_rels:
      mismatches.append(RelationshipMismatch(e.id, original_rels, recon_rels))

  if mismatches:
    raise ReconstructionError(
      f"{len(mismatches)} mismatches",
      mismatches
    )
```

Passing both the structural invariant checks and per-entity reconstruction gate is the correctness criterion for v1.3.1.

## 11. Implementation Roadmap

### 11.1 Module structure

```text
decoct/
├── adapters/
│   ├── base.py
│   ├── yang.py, openapi.py, json_schema.py, admx.py, augeas.py
│   └── entity_boundary.py
├── analysis/
│   ├── entropy.py
│   ├── profiler.py
│   └── tier_classifier.py
├── discovery/
│   ├── type_seeding.py
│   ├── type_discovery.py
│   ├── anti_unification.py
│   ├── bootstrap.py
│   └── composite_decomp.py
├── compression/
│   ├── class_extractor.py
│   ├── delta.py
│   ├── inversion.py
│   ├── normalisation.py
│   └── phone_book.py
├── assembly/
│   ├── tier_builder.py
│   ├── assertions.py
│   └── token_estimator.py
├── reconstruction/
│   ├── reconstitute.py
│   └── validator.py
├── core/
│   ├── types.py
│   ├── entity_graph.py
│   ├── composite_value.py
│   ├── canonical.py        # CANONICAL_KEY, CANONICAL_EQUAL, VALUE_KEY, ITEM_KEY,
│   │                       #   IS_SCALAR_LIKE, encode_canonical
│   ├── hashing.py
│   ├── config.py
│   └── io.py
└── evaluation/
    ├── harness.py
    ├── question_gen.py
    └── scorer.py
```

### 11.2 Build order

| Order | Component | Gate |
|-------|-----------|------|
| 1 | `core/` | Canonical key and stable hash deterministic across processes. Canonical equality helpers are authoritative. `IS_SCALAR_LIKE` excludes `composite_template_ref`. `entity_graph.py` deduplicates relationships. |
| 2 | `adapters/` | Canonical IDs; child subtree exclusion works; reference fields become relationships; reference collections emit deterministic unique targets; null elements in reference collections silently dropped. |
| 3 | `analysis/` | Final role vs bootstrap role classification correct. Small-group floor behaves as specified. |
| 4 | `discovery/bootstrap.py` | Types converge; sparse signals help but do not leak into base class. Anti-unification merge threshold is configurable. |
| 5 | `discovery/composite_decomp.py` | Shadow map preserved; post-decomp re-profiling uses fresh stats; pruning threshold counts entities covered. |
| 6 | `compression/class_extractor.py` | Primary classes are partial templates, not exact full vectors. `_base_only` ratio is computed. |
| 7 | `compression/delta.py` | Tier B-only deltas; deterministic subclass extraction over concrete delta items with `SUBCLASS_OVERHEAD_TOKENS`; deletions remain overrides; parent assignments remain inclusive. |
| 8 | `compression/normalisation.py` | Tier C phone book contains only dense scalar-like `C` (never `composite_template_ref`); `instance_attrs` holds all other `C`; relationship store contains all `R`; B composite deltas are separated from C composite values. |
| 9 | `reconstruction/` | 100% fidelity on attributes + relationships. Sparse `C`, composite `C`, literal-null `C`, and B-layer composite deltas all round-trip. Reserved-form discriminator handles all non-collision cases. |
| 10 | `assembly/` | Valid YAML with inclusive class assignments, explicit subclasses, structural invariants pass (including empty-schema/non-empty-records and B-delta template-ref checks), `base_only_ratio` emitted. |
| 11 | `evaluation/` | LLM task scores meet targets. |

### 11.3 Configuration

```yaml
pipeline:
  composite_decompose_threshold: 5
  min_composite_template_members: 2
  min_class_support: 3
  max_class_bundle_size: 3
  min_subclass_size: 3
  max_anti_unify_variables: 3
  small_group_floor: 8
  fk_overlap_threshold: 0.5
  fk_type_compat_threshold: 0.3
  subclass_overhead_tokens: 12

  # max_inheritance_depth is NOT configurable.
  # It is a hard architectural constraint (depth = 2) enforced as an assertion.

adapters:
  yang:
    max_entity_depth: 2
  openapi:
    max_entity_depth: 1
  json_schema:
    max_entity_depth: 2
```

## 12. Naming

`derive_type_name`, `derive_class_name`, and `derive_subclass_name` must be deterministic and human-legible:

1. Prefer sanitized schema type hints if present.
2. Otherwise use the top discriminating path names and, where stable, short sanitized value tokens from the bundle/signal set.
3. If the human-readable base name would collide with an existing name in the same scope, append a deterministic ordinal suffix to disambiguate (e.g. `bng_business`, `bng_business_1`). If the base name is already unique, no suffix is appended.
4. Opaque hashes may not be used as the visible name except as a fallback suffix after human-readable tokens, and only when no discriminating path/value information is available.

The collision-resolution approach keeps names clean in the common case (distinct bundles produce distinct base names) while guaranteeing uniqueness in all cases.

## 13. Remaining open questions (v1.3.1)

* Empirical defaults for `max_entity_depth` by adapter.
* Circular FK handling.
* Schema version drift for YANG/OpenAPI paths.
* Calibration of `SUBCLASS_OVERHEAD_TOKENS` — the default of 12 is an estimate. The actual value depends on YAML serialization style and should be measured against real output during implementation.

## 14. Known limitations (v1.3.1)

* **Reserved-form collision in `instance_attrs`:** A literal map C value on a template-capable path that exactly matches the `{template, delta?}` shape with a valid template ID will be misinterpreted as an encoded composite. See §9.1. Adapters must avoid producing such values on template-capable paths.
* **Reference collection semantics:** v1 uses set semantics for direct reference collections. Order and multiplicity are discarded. Source data requiring either must be modelled as child entities with ordinal attributes.
* **Value-representative non-identity:** Stored values in `base_attrs`, `item_lookup`, and similar structures are representatives of their `CANONICAL_EQUAL` equivalence class. They may not be byte-identical to every entity's original runtime value. Reconstruction validation uses `CANONICAL_EQUAL`, not Python identity.
* **Candidate enumeration scaling:** Phase 4 and Phase 5 use brute-force combination enumeration. This is acceptable for v1 infrastructure datasets but may require replacement with FP-growth or similar for larger datasets in v2.

## 15. Deferred to v2

* FCA-based class extraction.
* Global MDL optimization.
* Mixins.
* Scaffolding packs.
* Assertion relevance filtering.
* Output stability / structural diff.
* Fuzzy coupling.
* Schema-less / LLM-learned adapters.
* Progressive-loading runtime contract / tool API. The current Tier B/C format embeds cross-file references (`tier_c_ref`, `tier_b_ref`), which implicitly commits to file-level loading granularity. If v2 requires sub-file progressive loading, the format may need restructuring.
* `decoct diff`.
