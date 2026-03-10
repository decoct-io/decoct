# Entity-Graph Compressed Data — Reader Manual

This document explains how to read and use the three-tier YAML output produced by the decoct entity-graph pipeline. It is written for an LLM or human analyst receiving this data as context.

## What You Are Looking At

You have been given a compressed representation of a fleet of infrastructure configurations. Instead of receiving every configuration file individually — which would be highly repetitive — the data has been compressed into three tiers that separate what is shared from what is unique.

**The compression is lossless.** Every entity can be fully reconstructed from the data provided. Nothing has been discarded — only deduplicated and organised.

### Supported Data Sources

The pipeline supports three adapter types, each handling a different domain:

| Adapter | Input Format | Domain | Entity ID | Type Hinting |
|---|---|---|---|---|
| **IOS-XR** | `.cfg` text files | Network device configurations (Cisco IOS-XR routers) | Hostname from config header | Hostname prefix patterns (P-CORE-, RR-, APE-, etc.) |
| **Entra-Intune** | `.json` files | Microsoft Entra ID / Intune policies (Graph API exports) | `displayName` field | `@odata.type` field (13 known types) |
| **Hybrid Infrastructure** | `.yaml`, `.json`, `.ini`/`.conf`/`.cnf` | Mixed infrastructure configs (Docker Compose, Ansible, Terraform, PostgreSQL, systemd, sshd, Prometheus, cloud-init, Traefik, sysctl, app configs, etc.) | Filename stem | Content-based detection for 5 platforms; fingerprint grouping for the rest |

Each adapter maps **one file to one entity**. All three produce the same three-tier output format described below.

## The Three Tiers

The output consists of three tiers of YAML files:

| Tier | File | Purpose | Read This When... |
|---|---|---|---|
| **A** | `tier_a.yaml` | Fleet overview: what types exist, how many, how they connect | You need orientation — "what am I looking at?" |
| **B** | `{type}_classes.yaml` | Shared configuration: base class + class hierarchy per type | You need to understand what is common across entities |
| **C** | `{type}_instances.yaml` | Per-entity differences: unique values, overrides, relationships | You need specifics about an individual entity |

**Read Tier A first. Then Tier B for the type you care about. Then Tier C only for the specific entities you need.**

---

## Tier A — Fleet Overview

`tier_a.yaml` is the entry point. It tells you:

### `types`
Every discovered entity type, with counts and file references.

**IOS-XR example** (network devices):
```yaml
types:
  iosxr-access-pe:
    count: 60
    classes: 3
    tier_b_ref: iosxr-access-pe_classes.yaml
    tier_c_ref: iosxr-access-pe_instances.yaml
  iosxr-rr:
    count: 4
    classes: 1
    tier_b_ref: iosxr-rr_classes.yaml
    tier_c_ref: iosxr-rr_instances.yaml
```

**Entra-Intune example** (identity/policy):
```yaml
types:
  entra-conditional-access:
    count: 15
    classes: 2
    tier_b_ref: entra-conditional-access_classes.yaml
    tier_c_ref: entra-conditional-access_instances.yaml
  intune-compliance:
    count: 12
    classes: 1
    tier_b_ref: intune-compliance_classes.yaml
    tier_c_ref: intune-compliance_instances.yaml
```

**Hybrid infrastructure example** (mixed-format configs):
```yaml
types:
  docker-compose:
    count: 16
    classes: 2
    tier_b_ref: docker-compose_classes.yaml
    tier_c_ref: docker-compose_instances.yaml
  ansible-playbook:
    count: 15
    classes: 3
    tier_b_ref: ansible-playbook_classes.yaml
    tier_c_ref: ansible-playbook_instances.yaml
  unknown-0:
    count: 6
    classes: 1
    tier_b_ref: unknown-0_classes.yaml
    tier_c_ref: unknown-0_instances.yaml
```

**How to read:** Each type groups entities with structurally similar configurations. Type names come from platform detection (e.g., `docker-compose`, `ansible-playbook`, `entra-conditional-access`) or from fingerprint-based grouping (`unknown-N`) when the platform is not auto-detected (e.g., PostgreSQL `.conf` files, sysctl configs, app config JSON).

### `topology`
How types connect to each other. Only present when the adapter extracts inter-entity relationships.

```yaml
topology:
  iosxr-access-pe:
  - iosxr-p-core
  iosxr-p-core:
  - iosxr-rr
```

**How to read:** Access PEs connect to P-Core routers. P-Cores connect to route reflectors. This is the network's logical topology at the type level.

**Note:** IOS-XR extracts relationships from interface descriptions and BGP configs. Entra-Intune extracts group references, policy assignments, and cross-tenant links. The hybrid-infra adapter does not extract relationships (topology will be empty), since mixed-format configs rarely have standardised cross-references.

### `assertions`
Structural quality indicators.

```yaml
assertions:
  iosxr-rr:
    base_only_ratio: 1.0
```

**How to read:** `base_only_ratio: 1.0` means all route reflectors share the exact same configuration structure — there are no subgroups. A lower ratio means the type has meaningful internal variation that has been captured in classes.

---

## Tier B — Shared Configuration (Classes)

Each `{type}_classes.yaml` file contains the configuration template for one entity type. This is where most of the information lives.

### `base_class`
Attributes shared by **every** entity of this type, with identical values.

**IOS-XR example:**
```yaml
base_class:
  clock: timezone UTC 0
  domain: lookup disable
  interface.TenGigE0/0/0/0.mtu: '9216'
  router.isis.CORE.is-type: level-2-only
  ssh: timeout 30
```

**Docker Compose example:**
```yaml
base_class:
  services.web-app.logging.driver: json-file
  services.web-app.deploy.update_config.order: stop-first
  services.web-app.healthcheck.interval: 30s
  services.web-app.healthcheck.retries: '3'
```

**Entra-Intune example:**
```yaml
base_class:
  state: enabled
  grantControls.operator: OR
  sessionControls.signInFrequency.isEnabled: 'false'
```

**How to read:** Every entity of this type shares these exact values. These are design constants — they never vary.

**Attribute paths** use dot-separated notation. The path format depends on the data source:
- **IOS-XR:** `router.isis.CORE.is-type` — IOS-XR config hierarchy
- **YAML/JSON:** `services.web-app.deploy.replicas` — nested key hierarchy
- **Sectioned INI:** `mysqld.max_connections` — `[section].key` from INI sections (keys are lowercased)
- **Flat INI/conf:** `max_connections` — flat key directly from `key = value` files
- **Space-separated:** `PermitRootLogin` — key from `Key Value` configs (e.g., sshd_config)

### `classes`
Subgroups within the type. Each class adds its own attributes on top of the base class.

**IOS-XR example:**
```yaml
classes:
  address_family_l2vpn_evpn_maximum_paths_ibgp_1:
    inherits: base
    own_attrs:
      router.bgp.65002.address-family: l2vpn-evpn
      router.bgp.65002.address-family.ipv4-unicast.maximum-paths: ibgp 1
    instance_count_inclusive: 20
```

**Hybrid infrastructure example** (PostgreSQL configs grouped by fingerprint):
```yaml
classes:
  shared_buffers_256m_innodb_buffer_pool_size_256m:
    inherits: base
    own_attrs:
      shared_buffers: 256MB
      work_mem: 4MB
      effective_cache_size: 1GB
    instance_count_inclusive: 3
```

**How to read:** Entities sharing the same class have identical values for these attributes on top of the base class. Class names are auto-generated from the distinguishing attributes. For hybrid-infra types discovered by fingerprint (e.g., `unknown-0` for PostgreSQL configs), classes capture groups like "dev settings" vs "production-tuned settings."

### `subclasses`
Further refinements within a class. A subclass inherits from its parent class.

```yaml
subclasses:
  address_family_..._distance_bgp_20_200_200_gracef:
    parent: address_family_l2vpn_evpn_maximum_paths_ibgp_1
    own_attrs:
      router.bgp.65002.distance: bgp 20 200 200
      router.bgp.65002.graceful-restart: 'true'
      router.bgp.65002.timers: bgp 60 180
    instance_count: 20
```

**How to read:** This subclass adds BGP distance, graceful-restart, and timers to the parent class. The inheritance chain is: base → class → subclass (max depth 2).

### `composite_templates` (if present)
Templates for complex repeated sub-structures (e.g., BGP neighbor blocks, EVPN configurations). When present, Tier C instance values reference these templates by ID.

---

## Tier C — Per-Entity Differences

Each `{type}_instances.yaml` file contains everything that is unique to individual entities.

### `class_assignments`
Which entities belong to which class. ID ranges use `..` notation where possible; individual IDs are listed otherwise.

**IOS-XR example** (sequential IDs compress well):
```yaml
class_assignments:
  address_family_l2vpn_evpn_maximum_paths_ibgp_1:
    instances:
    - APE-R1-01..APE-R1-20
```

**Hybrid infrastructure example** (descriptive filenames listed individually):
```yaml
class_assignments:
  shared_buffers_256m_work_mem_4mb:
    instances:
    - pg-dev
    - pg-migration
    - pg-staging
```

**Entra-Intune example:**
```yaml
class_assignments:
  state_enabled_grantcontrols_operator_or:
    instances:
    - CA-Block-Legacy-Auth
    - CA-Compliant-Device-Internal
    - CA-MFA-Global-Admins
```

**How to read:** `APE-R1-01..APE-R1-20` is range notation for APE-R1-01 through APE-R1-20 (20 entities). When entity IDs are not sequential, they are listed individually.

### `subclass_assignments` (if present)
Same format, mapping entities to subclasses.

### `instance_data` (Phone Book)
A dense table of per-entity values for attributes that every entity has but with unique values (e.g., hostnames, IP addresses, environment names, service ports).

**IOS-XR example:**
```yaml
instance_data:
  schema:
  - hostname
  - interface.Loopback0.ipv4
  - interface.TenGigE0/0/0/0.description
  records:
    RR-01:
    - RR-01
    - address 10.0.0.11 255.255.255.255
    - TO-P-CORE-01
    RR-02:
    - RR-02
    - address 10.0.0.12 255.255.255.255
    - TO-P-CORE-01
```

**Hybrid infrastructure example** (Docker Compose):
```yaml
instance_data:
  schema:
  - services.core-api.image
  - services.core-api.environment.DATABASE_URL
  - services.web-app.environment.NODE_ENV
  records:
    compose-dev:
    - ridgeline/core-api:dev
    - postgresql://core:devpassword@postgres:5432/core_dev
    - development
    compose-staging:
    - ridgeline/core-api:staging
    - postgresql://core:stagingpw@postgres:5432/core_staging
    - staging
```

**How to read:** The `schema` is the column header. Each record is a positional list matching the schema order. So for compose-dev: `services.core-api.image` = "ridgeline/core-api:dev", etc.

This is the most space-efficient section — it stores what would otherwise be a separate file per entity in a compact tabular format.

### `instance_attrs` (if present)
Per-entity attributes that are sparse (not every entity has them) or structurally complex.

```yaml
instance_attrs:
  APE-R1-01:
    l2vpn.bridge-groups:
      BG-APE-R1-01:
        bridge-domain.BD-APE-R1-01-VOICE.evi: '10002'
        bridge-domain.BD-APE-R1-01-VOICE.routed: interface BVI300
    router.bgp.65002.address-family.ipv4-unicast.network: 10.0.1.1/32
```

**How to read:** APE-R1-01 has a bridge group called BG-APE-R1-01 with specific EVPN EVI configuration. Not every entity has the same bridge group structure, so these can't go in the phone book.

### `relationship_store` (if present)
Relationships between entities. The relationship labels are adapter-specific:

| Adapter | Relationship labels | Meaning |
|---|---|---|
| **IOS-XR** | `p2p_link`, `bgp_peer` | Physical links (from interface descriptions), BGP peerings |
| **Entra-Intune** | `group_ref`, `assignment_target`, `tenant_ref` | Group memberships, policy assignments, cross-tenant links |
| **Hybrid Infra** | *(none)* | No relationships extracted |

**IOS-XR example:**
```yaml
relationship_store:
  RR-01:
  - label: p2p_link
    target: P-CORE-01
  - label: bgp_peer
    target: RR-02
```

**Entra-Intune example:**
```yaml
relationship_store:
  CA-Compliant-Device-Internal:
  - label: group_ref
    target: SG-Engineering
  - label: group_ref
    target: SG-Finance-Users
  CP-Win-Basic-Security:
  - label: assignment_target
    target: DG-All-Corp-Windows
```

**How to read:** RR-01 has a point-to-point link to P-CORE-01. CA-Compliant-Device-Internal references two Entra groups. Relationships are directional.

### `overrides` (if present)
Per-entity deviations from their class template. These are entities that *almost* match their class but have a few differences.

```yaml
overrides:
  APE-R2-01:
    owner: address_family_..._distance_bgp_20_200_200_gracef
    delta:
      router.bgp.65003.nsr: 'true'
      router.bgp.65003.bgp.65001: 'true'
```

**How to read:** APE-R2-01 belongs to the named subclass but additionally has NSR enabled and confederation peer 65001. These are individual deviations from the class template.

---

## How to Reconstruct a Specific Entity

To mentally (or programmatically) reconstruct any entity, apply layers in order:

1. **Start with `base_class`** from Tier B — these are the entity's foundation
2. **Add the class `own_attrs`** — look up which class the entity belongs to in Tier C `class_assignments`, then get the class definition from Tier B
3. **Add the subclass `own_attrs`** (if any) — same lookup via `subclass_assignments`
4. **Apply `overrides`** (if any) — these patch specific attributes. `__ABSENT__` means the attribute is deleted
5. **Add `instance_attrs`** (if any) — sparse per-entity complex data
6. **Add `instance_data`** (phone book) — dense per-entity scalar values

Later layers override earlier ones. The result is the complete configuration of that entity.

### Example: Reconstruct RR-01 (IOS-XR)

```
Start:  base_class (120 attributes — clock, ISIS, MPLS, interfaces, etc.)
Class:  _base_only (no additional attributes — all RRs are identical structurally)
Phone:  hostname=RR-01, Loopback0.ipv4=10.0.0.11, TenGigE descriptions/IPs, etc.
Rels:   p2p_link→P-CORE-01, p2p_link→P-CORE-03, bgp_peer→RR-02, ...
```

### Example: Reconstruct compose-dev (Hybrid Infrastructure)

```
Start:  base_class (shared Docker Compose defaults — logging driver, healthcheck
        intervals, deploy restart policy, etc.)
Class:  services_core_api_restart_unless_stopped (adds restart policy, privileged=false, etc.)
Phone:  services.core-api.image=ridgeline/core-api:dev,
        services.core-api.environment.DATABASE_URL=postgresql://...,
        services.web-app.environment.NODE_ENV=development
Inst:   services.core-api.ports=8000:8000, networks.dev-network.driver=bridge
Rels:   (none — hybrid-infra does not extract relationships)
```

### Example: Reconstruct CA-MFA-Global-Admins (Entra-Intune)

```
Start:  base_class (state=enabled, grantControls.operator=OR, etc.)
Class:  grantcontrols_builtincontrols_mfa (adds MFA grant control)
Phone:  displayName=CA-MFA-Global-Admins,
        conditions.users.includeGroups=SG-Global-Admins
Rels:   group_ref→SG-Global-Admins
```

---

## Common Questions

### "What configuration do all entities of type X share?"
Read `base_class` in the Tier B file for type X. That's the complete shared configuration.

### "How does entity Y differ from the standard?"
1. Find Y's class in Tier C `class_assignments`
2. Find Y's subclass in `subclass_assignments` (if any)
3. Check `overrides` for Y (if any)
4. Read Y's row in `instance_data` and `instance_attrs`
Everything not listed in steps 2-4 is identical to the class/base template.

### "What IP address does entity Y have on interface Z?"
Look in Tier C `instance_data`. Find the schema position for `interface.Z.ipv4`, then read that position in Y's record.

### "Which entities connect to entity Y?"
Search `relationship_store` across all Tier C files. Relationships are directional — check both Y's entry and other entities that list Y as a target. Note: hybrid-infra entities have no relationships.

### "What is the range notation APE-R1-01..APE-R1-20?"
It means APE-R1-01, APE-R1-02, APE-R1-03, ..., APE-R1-20. The numeric suffix increments by 1. This is purely a space-saving notation for contiguous IDs. When entity IDs are non-sequential (common in hybrid-infra and Entra-Intune), they are listed individually.

### "What does `section.!: 'true'` mean (e.g., `control-plane.!: 'true'`)?"
This is an **IOS-XR section-existence marker**. In IOS-XR configurations, `!` characters at each indentation level terminate configuration blocks. The parser treats these indented `!` terminators as leaf nodes, producing paths like `control-plane.!`, `control-plane.management-plane.!`, `evpn.!`, `mpls.!`, `l2vpn.!`, `router.isis.CORE.!`, etc.

A value of `'true'` means that the named configuration section was explicitly present in the original device config, even if it contains no direct leaf values — only sub-sections or sub-commands. For example, `control-plane.!: 'true'` means the `control-plane` stanza existed; `control-plane.management-plane.inband.!: 'true'` means the `inband` sub-section existed under `management-plane` under `control-plane`.

These markers are safe to ignore when reading the data for operational content — they carry structural rather than operational meaning. However, they are included in class hierarchies because they are consistent across entities of the same type, and they are needed for lossless reconstruction.

### "What does `__ABSENT__` mean in an override?"
It means this attribute is explicitly removed for this entity. The class template has it, but this specific entity does not.

### "Why are some attributes in `instance_data` and others in `instance_attrs`?"
`instance_data` (phone book) is for attributes where every entity has a value and the value is a simple scalar (string, number). It's stored as a dense table for compactness.

`instance_attrs` is for everything else: sparse attributes (not every entity has them), complex structures (nested maps/lists), or composite template references.

### "What does `base_only_ratio: 1.0` mean?"
It means 100% of entities in this type fall into the `_base_only` class — there are no meaningful subgroups. The entire type is homogeneous except for per-entity values in Tier C. A ratio of 0.0 means every entity was assigned to a real class (good internal structure was found).

---

## Format-Specific Notes

### Hybrid Infrastructure — Attribute Path Conventions

The hybrid-infra adapter handles multiple input formats. The attribute path format in the output depends on the original file format:

| Input format | Path convention | Example path | Original source |
|---|---|---|---|
| YAML (nested) | Dot-separated key hierarchy | `services.core-api.image` | `services: core-api: image:` in Docker Compose |
| JSON (nested) | Dot-separated key hierarchy | `compute.app_instance_type` | `{"compute": {"app_instance_type": ...}}` in tfvars |
| Sectioned INI | `section.key` | `mysqld.max_connections` | `[mysqld] max_connections = 200` |
| Flat key=value | Key as-is | `max_connections` | `max_connections = 200` in postgresql.conf |
| Space-separated | Key as-is (case-preserved) | `PermitRootLogin` | `PermitRootLogin no` in sshd_config |

### Hybrid Infrastructure — Type Discovery

The hybrid-infra adapter auto-detects 5 platform types from file content:

| Detected type | Detection rule |
|---|---|
| `docker-compose` | Has `services` key with nested mappings |
| `ansible-playbook` | Root list with `hosts` + `tasks`/`roles` |
| `cloud-init` | 2+ cloud-init keys (`packages`, `runcmd`, `users`, etc.) |
| `traefik` | Has `entryPoints` or `providers` + `api` |
| `prometheus` | Has `scrape_configs` key |

Files not matching any rule (JSON app configs, PostgreSQL, MariaDB, systemd, sshd, sysctl, Ansible inventories/vars, Terraform tfvars, package.json, etc.) get `unknown-N` type names assigned by fingerprint-based grouping. The pipeline clusters these by structural similarity — for example, all PostgreSQL configs will typically end up in the same `unknown-N` type because they share the same attribute paths.

### Hybrid Infrastructure — Composite Values

Arrays of objects in YAML/JSON files are stored as **composite values** rather than flattened into dotted paths. These appear in Tier B/C as structured data:

| Source structure | Composite treatment |
|---|---|
| Ansible `tasks:` list | CompositeValue(kind="list") — each task is one item |
| Prometheus `scrape_configs:` | CompositeValue(kind="list") — each scrape job is one item |
| Docker Compose `depends_on:` (object form) | Flattened as dotted paths (nested dict, not array) |
| Cloud-init `users:` list | CompositeValue(kind="list") where items are objects |
| Scalar arrays (`["a", "b"]`) | Comma-separated string: `"a,b"` |

### Hybrid Infrastructure — INI Parsing Fallbacks

Some INI-style configs require special handling:

- **Duplicate keys** (e.g., systemd `Environment=` repeated): accumulated into comma-separated values rather than overwriting
- **Space-separated configs** (e.g., sshd `Key Value` with no `=`): fallback parser splits on first whitespace
- **Dotted keys in flat files** (e.g., sysctl `net.ipv4.tcp_syncookies = 1`): stored as-is — the dots are part of the key name, not path separators

### Entra-Intune — Type Discovery

Entra-Intune entities are typed by the `@odata.type` field from Microsoft Graph API exports. 13 OData types map to 8 logical types:

| Logical type | Entity examples |
|---|---|
| `entra-conditional-access` | CA policies (MFA, device compliance, location-based) |
| `entra-group` | Security groups, distribution groups |
| `entra-application` | App registrations with OAuth2 scopes |
| `intune-compliance` | Windows/iOS/Android compliance policies |
| `intune-device-config` | Device configuration profiles |
| `intune-app-protection` | Android/iOS app protection policies |
| `entra-named-location` | IP-based and country-based named locations |
| `entra-cross-tenant` | Cross-tenant access policy partners |

### Entra-Intune — Filtered Fields

Metadata fields are stripped before compression: `@odata.type`, `id`, `createdDateTime`, `modifiedDateTime`, `deletedDateTime`, `renewedDateTime`. These carry no configuration value and would reduce compression ratio.
