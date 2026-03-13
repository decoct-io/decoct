# Decoct Archetypal Test Fixture Specification

## Document Purpose

This specification defines the complete testing infrastructure for decoct's compression pipeline. It is intended as a handover document for Claude Code to understand, maintain, extend, and eventually wire up to the decoct pipeline when it ships.

The specification covers: the compressed output format decoct must produce, nine test sets that exercise every format primitive, five negative tests (traps) that verify decoct does not over-compress, the testing infrastructure (pytest, helpers, golden references), and the three-level testing plan.

## 1. Context

### 1.1 What decoct does

Decoct is an LLM-powered infrastructure context compression system. It takes raw YAML configuration data from multiple hosts (routers, switches, servers) and produces a compressed representation in two tiers:

- **Tier B** — extracted class templates (shared structure factored out across hosts)
- **Tier C** — per-host instance files (only what differs from the class)

The compressed output must be **readable by an LLM without reconstruction**. An LLM should be able to answer questions about any host's configuration by reading the Tier B + C representation directly, as accurately as if it had the raw data.

### 1.2 What these tests validate

The archetypal test fixtures are synthetic, hand-crafted datasets designed to test every aspect of decoct's compression. They are "archetypal" in the sense that each test set is a stylised, idealised representation of a specific compression challenge — not real-world data, but every corner case explored.

### 1.3 Repository location

```
tests/fixtures/archetypal/
├── generate_all.py
├── helpers.py
├── conftest.py
├── test_golden_integrity.py
├── test_decoct_output.py
├── set_a/ ... set_n/
└── decoct_archetypal_format_spec.md
```

## 2. Compressed Output Format

### 2.1 Convention: Class + Per-Host Overrides

```yaml
# Tier B: Class definition (shared structure)
ClassName:
  field_1: value
  field_2: value

# Tier C: Per-host (only what differs)
hostname:
  _class: ClassName
  field_that_differs: host-specific-value
```

### 2.2 Format Primitives

There are exactly six format primitives. No others should be invented.

| Primitive | Syntax | Meaning |
|-----------|--------|---------|
| `_class` | `_class: ClassName` | This host/instance inherits all fields from ClassName |
| `_remove` | `_remove: [field, ...]` | These fields from the class do not exist for this host |
| `_identity` | `_identity: [field, ...]` | These fields are unique per host/instance (declared in Tier B only) |
| `instances` | `instances: [...]` | List of entity instances for repeating types (e.g. interfaces) |
| Dot notation | `parent.child.field: value` | Override a specific nested field without ambiguity |
| No `_class` | (key absent) | Raw data — no class applies, read as-is |

### 2.3 Absence Semantics

- **Field absent from Tier C** → inherited from class (value exists, comes from Tier B)
- **`null` in Tier C** → explicitly null (field exists, value is nothing)
- **`_remove: [field]`** → field does not exist for this host (structurally absent)
- **No `_class` key** → uncompressed data, read as-is
- **No host entry for a section** → host matches class exactly, zero overrides

### 2.4 Dot Notation Rules

Dot notation provides unambiguous path-qualified overrides for nested structures. This avoids the ambiguity of whether a nested YAML key means "override just this field" or "replace the entire subtree."

| Operation | Syntax | Example |
|-----------|--------|---------|
| Override scalar at depth | `parent.child.field: new_value` | `telemetry.protocol: netconf` |
| Add new field at depth | `parent.child.new_field: value` | `telemetry.tls.min_version: "1.3"` |
| Add new subtree | One dot-notation key per leaf | `telemetry.auth.method: certificate` |
| Remove field at depth | `_remove: [parent.child.field]` | `_remove: [telemetry.tls.cipher]` |
| Remove entire subtree | `_remove: [parent.child]` | `_remove: [telemetry.tls]` |
| Replace list at depth | `parent.child.list: [new, items]` | `telemetry.collectors: [10.0.0.3]` |
| Partial list modification | **Not supported** | Replace whole list instead |

### 2.5 Anti-patterns

The following should NEVER appear in decoct output:

```yaml
# WRONG — ambiguous whether telemetry subtree is preserved or dropped
rtr-01:
  _class: ServiceConfig
  service_policy:
    interval: 60
```

The correct form is:

```yaml
rtr-01:
  _class: ServiceConfig
  service_policy.interval: 60
```

## 3. Test Sets (Positive Tests)

Each test set has its own directory under `tests/fixtures/archetypal/`. Each directory contains:

```
set_X/
├── input/rtr-{00..04}.yaml     # Tier A raw data (what decoct receives)
├── golden/
│   ├── tier_b.yaml             # Expected class extraction
│   └── tier_c/rtr-{00..04}.yaml  # Expected per-host output
└── expected.yaml               # Test metadata and scoring criteria
```

All test sets use 5 hosts (rtr-00 through rtr-04).

### 3.1 Set A — Overlap

**Directory:** `set_a/`

**Purpose:** Greedy class extraction. Tests whether decoct can discover that multiple hosts share a large identical structure with minimal variation.

**Pipeline phase tested:** Class extraction.

**Input structure:** Each host has a `base_infra` section with 22 fields. 21 fields are byte-identical across all 5 hosts. Only `snmp_location` differs per host (site-A through site-E). Adjacent `snmp_security` section is Trap 1 (see Section 4.1).

**Expected Tier B output:**

One class `BaseInfra` with 21 static fields. `snmp_location` is NOT in the class.

**Expected Tier C output per host:**

```yaml
base_infra:
  _class: BaseInfra
  snmp_location: site-A   # only varying field
```

**Scoring criteria:**

1. Exactly 1 class created for `base_infra`
2. Static field count = 21
3. Only `snmp_location` appears in Tier C per host
4. Tier B + Tier C reconstructs Tier A exactly

**What failure looks like:**

- 0 classes: decoct failed to recognise the overlap
- 2+ classes: decoct is splitting unnecessarily (e.g. per-site classes)
- `snmp_location` in the class with one host's value: data loss for other hosts
- Other fields leaking into Tier C: unnecessary data in per-host files

### 3.2 Set B — Subtraction

**Directory:** `set_b/`

**Purpose:** Delta compression via key removal. Tests the `_remove` primitive.

**Pipeline phase tested:** Delta compression (deletions).

**Input structure:** Each host has a `qos_policy` section. All values are identical across hosts. The only difference is which keys are present — files progressively drop keys:

- rtr-00: all 11 fields (full policy)
- rtr-01: 10 fields (no `burst`)
- rtr-02: 8 fields (no `burst`, `wred_min`, `wred_max`)
- rtr-03: 7 fields (also no `ecn`)
- rtr-04: 5 fields (also no `shaping_rate`, `queue_limit`)

**Expected Tier B output:**

One class `QosPolicy` with all 11 fields (the superset).

**Expected Tier C output:**

```yaml
# rtr-00 — matches class exactly
qos_policy:
  _class: QosPolicy

# rtr-01 — one field removed
qos_policy:
  _class: QosPolicy
  _remove: [burst]

# rtr-04 — six fields removed
qos_policy:
  _class: QosPolicy
  _remove: [burst, wred_min, wred_max, ecn, shaping_rate, queue_limit]
```

**Scoring criteria:**

1. Exactly 1 class (no inheritance chain — flat `_remove` per host)
2. `_remove` lists are correct and complete per host
3. rtr-00 has no `_remove` (exact class match)
4. Each host's `_remove` is a superset of the previous host's (progressive)
5. Reconstruction is lossless

**Critical design decision:** Decoct should NOT create an inheritance chain (e.g. QosPolicy → QosPolicy_NoBurst → QosPolicy_NoWred). Inheritance chains require multi-hop reasoning by the LLM. Flat `_remove` per host is one-hop: read class, mentally subtract the listed fields.

### 3.3 Set C — Addition

**Directory:** `set_c/`

**Purpose:** Delta compression via key addition. Tests extra fields in Tier C.

**Pipeline phase tested:** Delta compression (additions).

**Input structure:** Each host has a `monitor_target` section. 5 base fields are identical. Files progressively add extra fields:

- rtr-00: 5 base fields only
- rtr-01: base + `threshold_info`
- rtr-02: base + `threshold_info`, `escalation_group`
- rtr-03: base + 3 extras
- rtr-04: base + 5 extras (`threshold_info`, `escalation_group`, `suppress_flap`, `correlation_id`, `dependency_check`)

Adjacent `service_policy` section is Trap 2 (see Section 4.2).

**Expected Tier B output:**

One class `MonitorTarget` with the 5 base fields only.

**Expected Tier C output:**

Extra fields appear directly in Tier C as additional key-value pairs. No special marker needed — if it's in Tier C but not in the class, it's an addition.

```yaml
rtr-02:
  _class: MonitorTarget
  threshold_info: 50
  escalation_group: tier2
```

**Scoring criteria:**

1. Exactly 1 class (no subclasses for additions)
2. Extra fields appear inline in Tier C
3. Each host's extras are a superset of the previous (progressive)
4. Reconstruction is lossless

### 3.4 Set D — Identity

**Directory:** `set_d/`

**Purpose:** Unique-per-host values. Tests the `_identity` primitive.

**Pipeline phase tested:** Instance data classification.

**Input structure:** Each host has a `loopback_interface` section. 9 fields are identical. `ipv4_address` is unique per host (10.0.0.0 through 10.0.0.4). Adjacent `dns_resolution` section is Trap 3 (see Section 4.3).

**Expected Tier B output:**

One class `LoopbackInterface` with 9 static fields plus `_identity: [ipv4_address]`.

**Expected Tier C output:**

```yaml
rtr-00:
  _class: LoopbackInterface
  ipv4_address: 10.0.0.0
```

**What `_identity` means vs a regular override:**

An override (`snmp_location` in Set A) is a field that happens to differ. Two hosts could share the same value. An identity field (`ipv4_address` in Set D) MUST be unique — if two hosts had the same value, that's an error.

**Scoring criteria:**

1. `ipv4_address` identified as `_identity`, not just an override
2. `_identity` declaration present in Tier B class
3. No redundant `node_id` stored (hostname is already the Tier C key)
4. All `ipv4_address` values are unique across hosts
5. Reconstruction is lossless

### 3.5 Set E — Heterogeneous

**Directory:** `set_e/`

**Purpose:** Classification boundary. Standalone negative test (no trap — the entire set IS the negative test).

**Pipeline phase tested:** Class discovery threshold (Jaccard similarity).

**Input structure:** Each host has a `config_block` section with a completely different schema:

- rtr-00: BGP config (6 fields including `protocol: bgp`, `timeout: 30`)
- rtr-01: Static route (5 fields)
- rtr-02: ACL entry (6 fields including `protocol: tcp`)
- rtr-03: TE tunnel (5 fields including `timeout: 30`)
- rtr-04: TACACS server (4 fields including `timeout: 10`)

Incidental field name overlap: `timeout` appears on rtr-00, rtr-03, rtr-04. `protocol` appears on rtr-00, rtr-02. This is coincidental — the schemas are fundamentally different.

**Expected Tier B output:** Empty (no classes).

**Expected Tier C output:** Raw passthrough — each host's Tier C is identical to its Tier A.

**Scoring criteria:**

1. Zero classes created
2. All fields preserved verbatim
3. Incidental field name overlap did NOT trigger false class extraction

**Why this matters:** Decoct must have a Jaccard similarity threshold below which it does not extract classes. Set E validates that threshold works. The Jaccard similarity between any two hosts here is approximately 0.1 — far below any reasonable extraction threshold.

### 3.6 Set G — Ordered List

**Directory:** `set_g/`

**Purpose:** List ordering semantics. Tests that decoct treats list order as significant.

**Pipeline phase tested:** Canonicalisation (list ordering).

**Input structure:** Each host has a `maintenance_schedule` section containing an ordered list of 10 maintenance steps. 4 hosts have identical step order. rtr-03 has steps 4 and 5 swapped (`restart_services` before `apply_patches` instead of after).

**Expected Tier B output:**

One class `MaintenanceSchedule` with the canonical step order (matching rtr-00/01/02/04).

**Expected Tier C output:**

- rtr-00, rtr-01, rtr-02, rtr-04: `_class: MaintenanceSchedule` (exact match)
- rtr-03: Full raw data inline (no `_class`) — the entire schedule is reproduced because the list order differs

```yaml
# rtr-03 — raw, no class reference
maintenance_schedule:
  approval_required: true
  steps:
    - drain_traffic
    - snapshot_config
    - backup_database
    - restart_services    # swapped
    - apply_patches       # swapped
    - validate_health
    - run_smoke_tests
    - restore_traffic
    - notify_stakeholders
    - close_ticket
```

**Critical design decision:** Decoct should NOT attempt to express partial list reordering (e.g. "same as class but swap indices 3 and 4"). That requires the LLM to mentally apply index operations. If a list differs, carry the full list as raw data.

**Scoring criteria:**

1. Class extracted from the 4 matching hosts
2. rtr-03 carried as raw — no `_class`, full data inline
3. Reordered list NOT treated as matching the class
4. Exactly 1 deviant host out of 5
5. Reconstruction is lossless

### 3.7 Set L — Repeating Entities (Interfaces)

**Directory:** `set_l/`

**Purpose:** Multiple instances of the same entity type per host. Tests the `instances` primitive.

**Pipeline phase tested:** Instance extraction with per-instance overrides.

**Input structure:** Each host has an `interfaces` section containing a list of 8 interfaces. Each interface has 8 fields. 6 fields (`mtu`, `speed`, `duplex`, `admin_state`, `isis_metric`, `mpls_ldp`) are identical across all interfaces on all hosts. 2 fields (`name`, `ipv4_address`) are unique per interface. Two exceptions:

- rtr-02, GigE0/0/0/6: `speed: 1g` instead of `10g` (per-instance override)
- rtr-03, GigE0/0/0/7: `mpls_ldp` field is absent entirely (per-instance removal)

**Expected Tier B output:**

One class `InterfaceConfig` with 6 static fields + `_identity: [name, ipv4_address]`.

**Expected Tier C output:**

```yaml
rtr-02:
  _class: InterfaceConfig
  instances:
    - {name: GigE0/0/0/0, ipv4_address: 10.0.2.1}
    - {name: GigE0/0/0/1, ipv4_address: 10.0.2.2}
    # ... 
    - {name: GigE0/0/0/6, ipv4_address: 10.0.2.7, speed: 1g}  # override
    - {name: GigE0/0/0/7, ipv4_address: 10.0.2.8}

rtr-03:
  _class: InterfaceConfig
  instances:
    # ...
    - {name: GigE0/0/0/7, ipv4_address: 10.0.3.8, _remove: [mpls_ldp]}  # removal
```

**Instance-level mechanics mirror host-level:**

| Condition | Representation |
|-----------|---------------|
| Field inherited from class | Absent from instance |
| Field overridden | Present with new value |
| Field removed | `_remove: [field_name]` |

**Scoring criteria:**

1. One class with 6 static fields
2. `_identity: [name, ipv4_address]` declared
3. Instances carry only identity + overrides/removals
4. Exactly 1 per-instance override across all 40 instances (rtr-02, instance 6, `speed: 1g`)
5. Exactly 1 per-instance removal across all 40 instances (rtr-03, instance 7, `_remove: [mpls_ldp]`)
6. All other instances are identity-only
7. Reconstruction is lossless

### 3.8 Set M — Nested Overrides

**Directory:** `set_m/`

**Purpose:** Path-qualified overrides at depth using dot notation. Tests all dot notation operations.

**Pipeline phase tested:** Nested structure compression.

**Input structure:** Each host has a `service_config` section containing a nested `service_policy` structure with sub-sections `telemetry` (including a `collectors` list) and `logging`. The same field name `interval` appears at three different paths:

- `service_policy.interval` (depth 1)
- `service_policy.telemetry.interval` (depth 2)
- `service_policy.logging.interval` (depth 2)

Each host exercises different dot notation operations:

| Host | Operations | What it tests |
|------|-----------|---------------|
| rtr-00 | None — matches class exactly | Baseline |
| rtr-01 | `service_policy.interval: 60` + `service_policy.telemetry.collectors: [new list]` | Scalar override + list replacement |
| rtr-02 | Multi-depth overrides + `service_policy.telemetry.auth.*` (3 new fields) | Override at multiple depths + subtree addition |
| rtr-03 | `_remove: [service_policy.logging]` | Entire subtree removal |
| rtr-04 | Override + list replace + field remove all combined | All operations together |

Adjacent `export_policy` section is Trap 4 (see Section 4.4).

**Expected Tier B output:**

One class `ServiceConfig` with the full nested structure (matching rtr-00).

**Expected Tier C output (rtr-04 as the most complex example):**

```yaml
service_config:
  _class: ServiceConfig
  'service_policy.interval': 60
  'service_policy.logging.interval': 120
  'service_policy.telemetry.collectors': ["10.0.0.9"]
  _remove: [service_policy.telemetry.encoding]
```

**Scoring criteria:**

1. Dot-notation overrides target the correct depth
2. Same-named fields at different paths (`interval`) handled independently
3. Subtree addition works (rtr-02 adds `auth` subtree via per-leaf dot keys)
4. Subtree removal works (rtr-03 removes entire `logging`)
5. List replacement is wholesale (no partial list patching)
6. rtr-04 combines all operations in one host entry
7. Reconstruction is lossless

### 3.9 Set N — Partial Classification

**Directory:** `set_n/`

**Purpose:** Sub-fleet class discovery. Tests decoct's ability to find multiple classes within the same section, and to leave outliers as raw data.

**Pipeline phase tested:** Multi-class extraction.

**Input structure:** Each host has a `bgp_policy` section. Three structural groups:

- **Group 1 (rtr-00, rtr-01):** Identical — 8 fields including `address_family: ipv4-unicast`, `graceful_restart: true`, `max_paths_ibgp: 8`
- **Group 2 (rtr-02, rtr-03):** Identical — 8 fields including `address_family: vpnv4-unicast`, `graceful_restart: false`, `confederation_id: 100`
- **Outlier (rtr-04):** Unique — 9 fields including `address_family: ipv6-unicast`, `bfd_enabled: true`

Groups 1 and 2 share `asn: 65000` and `router_id_source: loopback0` — decoct must NOT merge them into one class because of these shared fields. The overall structure and most values differ.

**Expected Tier B output:**

Two classes: `BgpPolicyCore` (group 1) and `BgpPolicyVpn` (group 2).

**Expected Tier C output:**

```yaml
rtr-00:
  bgp_policy:
    _class: BgpPolicyCore

rtr-04:
  bgp_policy:       # raw — no class
    asn: 65100
    router_id_source: loopback1
    # ... all fields inline
```

**Scoring criteria:**

1. Exactly 2 classes created (not 1, not 3)
2. rtr-00 and rtr-01 assigned to the same class
3. rtr-02 and rtr-03 assigned to the same class (different from group 1)
4. rtr-04 is raw (no `_class`)
5. Shared fields (`asn`, `router_id_source`) did NOT cause false merger
6. Reconstruction is lossless

## 4. Traps (Negative Tests)

Traps are negative test cases embedded adjacent to positive test sets. They look compressible but should NOT be compressed. Each trap tests a specific failure mode.

### 4.1 Trap 1 — Type Coercion (in `set_a/`)

**Section name in input:** `snmp_security`

**Adjacent to:** Set A (overlap)

**What it tests:** Decoct must NOT normalise textually different values, even when they are logically equivalent.

**Input per host:**

| Host | `snmp_auth_enabled` | `snmp_encrypt` | `snmp_version` |
|------|-------------------|----------------|----------------|
| rtr-00 | `true` (bool) | `true` (bool) | `3` (int) |
| rtr-01 | `"true"` (string) | `true` (bool) | `3` (int) |
| rtr-02 | `true` (bool) | `"yes"` (string) | `"3"` (string) |
| rtr-03 | `1` (int) | `true` (bool) | `3` (int) |
| rtr-04 | `"on"` (string) | `"true"` (string) | `3` (int) |

**Expected output:** No class. Raw passthrough per host.

**Why it matters:** A naive implementation might canonicalise `"true"` → `true` and merge all hosts. This would lose type information that may be significant (e.g. a system that treats string `"true"` differently from boolean `true`).

### 4.2 Trap 2 — Low Jaccard Disguised (in `set_c/`)

**Section name in input:** `service_policy`

**Adjacent to:** Set C (addition)

**What it tests:** Decoct must NOT extract a class from blocks that look structurally similar but share no actual fields.

**Input:** All 5 hosts have a `service_policy` parent key, each with a different child key containing 3 fields:

- rtr-00: `service_policy.telemetry: {interval, protocol, encoding}`
- rtr-01: `service_policy.sflow: {sample_rate, collector, port}`
- rtr-02: `service_policy.netflow: {version, exporter, template_timeout}`
- rtr-03: `service_policy.streaming: {sensor_group, destination, cadence}`
- rtr-04: `service_policy.snmp_polling: {community, interval, target}`

Same parent key, same nesting depth, same field count — looks compressible at a glance. But the child keys and field names are completely different. Jaccard ≈ 0.

**Expected output:** No class. Raw passthrough.

### 4.3 Trap 3 — Structural Nesting (in `set_d/`)

**Section name in input:** `dns_resolution`

**Adjacent to:** Set D (identity)

**What it tests:** Decoct must NOT conflate logically equivalent data that differs structurally.

**Input:** Same logical data (DNS server and search domain), three different YAML structures:

- rtr-00, rtr-02: flat — `dns_server: 10.100.1.1`, `dns_search: archetypal.lab`
- rtr-01, rtr-03: nested — `dns.server: 10.100.1.1`, `dns.search: archetypal.lab`
- rtr-04: different keys — `dns_config.primary_server: 10.100.1.1`, `dns_config.search_domain: archetypal.lab`

**Expected output:** No class across all 5 (raw passthrough). Decoct MAY optionally create up to 2 classes (flat pair and nested pair), but must NEVER merge all 5 into one class.

### 4.4 Trap 4 — Same Children, Different Parents (in `set_m/`)

**Section name in input:** `export_policy`

**Adjacent to:** Set M (nested overrides)

**What it tests:** Decoct must compare full paths, not just leaf field names, when assessing similarity.

**Input:** All 5 hosts have identical leaf values (`interval: 30`, `protocol: grpc`, `encoding: gpb`) but under different parent keys:

- rtr-00: `service_policy.telemetry.*`
- rtr-01: `service_policy.sflow.*`
- rtr-02: `service_policy.netflow.*`
- rtr-03: `service_policy.streaming.*`
- rtr-04: `service_policy.diagnostics.*`

Leaf-level Jaccard = 1.0 (identical). Full-path Jaccard = 0.0 (completely different paths).

**Expected output:** No class. Raw passthrough.

## 5. Testing Infrastructure

### 5.1 File: `helpers.py`

Shared reconstruction and loading logic. Key functions:

- `deep_set(dict, dotpath, value)` — set a nested value using dot notation
- `deep_delete(dict, dotpath)` — delete a nested key using dot notation
- `normalize(obj)` — recursively sort dict keys for comparison (lists are NOT sorted — order matters)
- `reconstruct_section(tier_b, tier_c_section)` — rebuild original data from class + overrides
- `reconstruct_instances(tier_b, tier_c_section)` — rebuild instance list from class + per-instance overrides
- `TestCase` class — loads all files for one set (inputs, tier_b, tier_c, expected metadata)
- `load_case(set_dir)` — factory for TestCase

### 5.2 File: `conftest.py`

pytest configuration. Discovers all `set_*` directories and provides a parametrised `case` fixture. Every test function that takes `case` as a parameter runs once per set.

### 5.3 File: `expected.yaml` (per set)

Machine-readable scoring criteria for each set. Structure:

```yaml
positive_sections: [section_name, ...]    # sections that should be compressed
negative_sections: [section_name, ...]    # sections that should NOT be compressed (traps)
classes:
  section_name:
    class_name: ClassName
    class_count: 1
    static_field_count: 21
    identity_fields: [field, ...]         # optional
    override_fields: [field, ...]         # optional
    removal_progression: [0, 1, 3, 4, 6] # optional (per-host removal counts)
    addition_progression: [0, 1, 2, 3, 5] # optional
    hosts_matching: [rtr-00, ...]         # optional (Set G)
    hosts_raw: [rtr-03]                   # optional (Set G)
traps:
  section_name:
    expected_classes: 0
    reason: type_coercion | low_jaccard_disguised | structural_nesting | same_children_different_parents
```

### 5.4 File: `generate_all.py`

Regenerates all fixture data from code. Run after any changes to the test design:

```bash
cd tests/fixtures/archetypal
python generate_all.py
```

Produces `input/`, `golden/`, and `expected.yaml` for all 9 sets.

## 6. Test Modules

### 6.1 `test_golden_integrity.py` — Level 1a: Fixture Validation

**Purpose:** Proves the test data itself is internally consistent. These tests validate that Tier B + C can reconstruct Tier A for every set. They do NOT test decoct — they test the golden references.

**Run:** `python -m pytest test_golden_integrity.py -v`

**Current status:** 99 passed, 72 skipped, 0 failed.

**Test classes:**

- `TestReconstruction` — B + C == A for every host, every section
  - `test_all_hosts_present` — every input host has a golden tier_c file
  - `test_all_sections_present` — every section exists in both input and tier_c
  - `test_positive_section_reconstruction` — class-based reconstruction matches raw
  - `test_negative_section_passthrough` — trap sections match raw exactly

- `TestStructure` — golden refs match expected.yaml criteria
  - `test_class_count` — correct number of classes in tier_b
  - `test_class_names` — expected class names present
  - `test_negative_sections_no_class` — traps have no `_class`
  - `test_identity_fields_declared` — `_identity` in tier_b where expected
  - `test_identity_fields_unique` — identity values are unique
  - `test_static_field_count` — classes have correct field count

- `TestSetSpecific` — per-set invariants
  - `test_set_b_progressive_removal` — each host's `_remove` is superset of previous
  - `test_set_c_progressive_addition` — each host adds cumulatively
  - `test_set_g_one_deviant` — exactly rtr-03 is raw
  - `test_set_l_one_override_one_removal` — exactly 1 override + 1 removal across 40 instances
  - `test_set_n_two_groups_one_outlier` — 2 classes, 2 hosts each, 1 raw
  - `test_set_m_dot_notation_present` — hosts with overrides use dot notation
  - `test_trap1_type_diversity` — at least 4 distinct type signatures across hosts
  - `test_trap2_all_different_parents` — 5 distinct child keys
  - `test_trap4_identical_leaves` — all leaves identical despite different parents

### 6.2 `test_decoct_output.py` — Level 1b: Pipeline Scoring (STUB)

**Purpose:** Scores decoct's actual output against golden references. Currently a stub that skips all tests with "decoct pipeline not yet implemented."

**To activate:** Replace the `run_decoct()` function with an actual call to the decoct pipeline. The function should accept a dict of `{hostname: yaml_data}` and return `(tier_b_dict, tier_c_dict)`.

**Test classes:**

- `TestDecoctClassDiscovery` — correct classes extracted
- `TestDecoctReconstruction` — lossless round-trip
- `TestDecoctCompression` — positive sections use classes

## 7. Comparison Semantics

### 7.1 How comparison works

All comparisons use `yaml.safe_load` → `normalize()` → Python `==`.

| Property | Checked? | How |
|----------|----------|-----|
| All keys present | Yes | Union of both key sets, both directions |
| No extra keys | Yes | Flagged as error |
| Values (type-sensitive) | Yes | Python `==` after `safe_load` |
| List ordering | Yes | Positional comparison |
| Nesting depth | Yes | Implicit via parsed structure |
| Dict key ordering | No | YAML mappings are unordered per spec |
| Indentation | Yes | Implicit — indentation IS nesting in YAML |

### 7.2 Type preservation

`yaml.safe_load` preserves type distinctions that matter:

- `true` (bool) ≠ `"true"` (str) ≠ `1` (int)
- `3` (int) ≠ `"3"` (str) ≠ `3.0` (float)
- `null` (NoneType) ≠ `""` (str) ≠ `"null"` (str)

This is critical for Trap 1.

## 8. Three-Level Testing Plan

### Level 1: Unit Tests (CURRENT — implemented)

- Per-set, 5 routers
- Exact golden match, binary pass/fail
- Tests each format primitive in isolation
- `test_golden_integrity.py` validates test data
- `test_decoct_output.py` scores decoct output (stub)

### Level 2: Integration Tests (FUTURE)

- All sets combined in one file per router
- Decoct processes mixed compressible + non-compressible sections
- Tests that decoct handles section boundaries correctly
- Tests that class discovery doesn't leak across sections
- Scored against combined golden reference

### Level 3: Scale + Compression Ratio (FUTURE)

- Parametrically generated: 50-100 routers
- `generate_all.py` extended with `--routers N` parameter
- Tier B is constant (same classes regardless of fleet size)
- Tier C grows linearly but only carries overrides/identity
- Compression target calculated from golden reference patterns:

```python
expected_ratio = tier_a_bytes / (tier_b_bytes + tier_c_bytes)
assert actual_ratio >= expected_ratio * 0.95  # 5% tolerance
```

- Compression scales with fleet size:

| Routers | Set A ratio | Set L ratio | Overall |
|---------|-------------|-------------|---------|
| 5 | ~4× | ~2.4× | ~1.8× |
| 50 | ~15× | ~8× | TBD |
| 100 | ~17× | ~10× | TBD |

Negative tests (Set E, traps) are 1:1 at any scale — they anchor the compression floor.

## 9. Adding New Test Sets

To add a new test set:

1. Define the set in `generate_all.py`:
   - Input generator function (produces Tier A per host)
   - Golden Tier B (expected class extraction)
   - Golden Tier C (expected per-host output)
   - `expected.yaml` metadata

2. Add set-specific tests to `test_golden_integrity.py` in `TestSetSpecific` class

3. Run `python generate_all.py` to create the directory structure

4. Run `python -m pytest test_golden_integrity.py -v` to validate

5. The `conftest.py` auto-discovers `set_*` directories — no registration needed

## 10. Summary

### Positive Tests

| Set | Directory | Tests | Classes | Key mechanic |
|-----|-----------|-------|---------|--------------|
| A | `set_a/` | Overlap | 1 | Override |
| B | `set_b/` | Subtraction | 1 | `_remove` |
| C | `set_c/` | Addition | 1 | Extra fields in Tier C |
| D | `set_d/` | Identity | 1 | `_identity` |
| G | `set_g/` | Ordered list | 1 | Non-matching host = raw |
| L | `set_l/` | Repeating entities | 1 | `instances` + per-instance ops |
| M | `set_m/` | Nested overrides | 1 | Dot notation |
| N | `set_n/` | Partial classification | 2 | Multi-class + raw outlier |

### Negative Tests (Traps)

| Trap | In set | Tests | Expected classes |
|------|--------|-------|-----------------|
| 1 | `set_a/` | Type coercion | 0 |
| 2 | `set_c/` | Low Jaccard disguised | 0 |
| 3 | `set_d/` | Structural nesting | 0 (max 2) |
| 4 | `set_m/` | Same children, different parents | 0 |
| E | `set_e/` | Heterogeneous | 0 |

### Format Primitives

| Primitive | Purpose | Tested by |
|-----------|---------|-----------|
| `_class` | Inheritance | All positive sets |
| `_remove` | Field deletion | Set B, Set L (instance-level) |
| `_identity` | Unique fields | Set D, Set L |
| `instances` | Repeating entities | Set L |
| Dot notation | Nested overrides | Set M |
| No `_class` (raw) | No compression | Set E, Set G (rtr-03), Set N (rtr-04), all traps |
