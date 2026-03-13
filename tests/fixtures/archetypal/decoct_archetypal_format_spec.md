# Decoct Archetypal Fixture Format Specification

## Overview

This document defines the compressed output format for decoct's archetypal test
fixtures. The format must be **readable by an LLM without reconstruction** — the
model should be able to answer questions about any host's configuration by
reading the compressed representation directly.

## Format Convention — Class + Per-Host Overrides

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

### Rules

| Condition | Representation |
|-----------|---------------|
| Field inherited from class | Absent from Tier C |
| Field overridden for this host | Present in Tier C with new value |
| Field added for this host | Present in Tier C (not in class) |
| Field removed for this host | `_remove: [field_name]` |
| Field unique per host (identity) | Declared as `_identity` in Tier B |
| No class extracted | No `_class` key — data is raw/inline |
| Nested field override | Dot notation: `parent.child.field: value` |
| Nested field removal | Dot notation: `_remove: [parent.child.field]` |

### Absence Semantics

- No `_class` key on a host block → uncompressed data, read as-is
- No host entry for a set → host matches class exactly, zero overrides

### Dot Notation

For nested structures, dot notation provides unambiguous path-qualified
overrides. This avoids the ambiguity of whether a nested YAML key means
"override just this field" or "replace the entire subtree."

#### Operations

| Operation | Syntax | Example |
|-----------|--------|---------|
| Override scalar at depth | `parent.child.field: new_value` | `telemetry.protocol: netconf` |
| Add new field at depth | `parent.child.new_field: value` | `telemetry.tls.min_version: "1.3"` |
| Add new subtree | One key per leaf field | `telemetry.auth.method: certificate` |
| Remove field at depth | `_remove: [parent.child.field]` | `_remove: [telemetry.tls.cipher]` |
| Remove entire subtree | `_remove: [parent.child]` | `_remove: [telemetry.tls]` |
| Replace list at depth | `parent.child.list: [new, items]` | `telemetry.collectors: [10.0.0.3]` |
| Partial list modification | **Not supported** | Replace whole list instead |

#### Examples

**Override at depth 2:**

```yaml
rtr-01:
  _class: ServiceConfig
  telemetry.protocol: netconf
```

**Override at depth 3:**

```yaml
rtr-01:
  _class: ServiceConfig
  telemetry.tls.cipher: aes-128-gcm
```

**Add a new nested field not in the class:**

```yaml
rtr-02:
  _class: ServiceConfig
  telemetry.tls.min_version: "1.3"
```

**Add an entire new subtree (one key per leaf):**

```yaml
rtr-01:
  _class: ServiceConfig
  telemetry.auth.method: certificate
  telemetry.auth.ca: /etc/pki/ca.pem
  telemetry.auth.verify: true
```

**Remove a nested field:**

```yaml
rtr-03:
  _class: ServiceConfig
  _remove: [telemetry.tls.cipher]
```

**Remove an entire subtree and everything under it:**

```yaml
rtr-02:
  _class: ServiceConfig
  _remove: [telemetry.tls]
```

**Replace a list at depth (whole list, no partial patching):**

```yaml
rtr-01:
  _class: ServiceConfig
  telemetry.collectors: [10.0.0.3, 10.0.0.4]
```

**Multiple operations at different depths in one host:**

```yaml
rtr-04:
  _class: ServiceConfig
  telemetry.protocol: netconf
  telemetry.tls.cipher: aes-128-gcm
  _remove: [telemetry.tls.min_version]
```

#### Anti-pattern

```yaml
# NOT this — ambiguous whether telemetry subtree is preserved or dropped
rtr-01:
  _class: ServiceConfig
  service_policy:
    interval: 60
```

---

## Set A — Overlap

**Purpose:** Greedy class extraction.

**What it tests:** Can decoct discover that 5 hosts share 20 identical fields
and only `snmp_location` varies?

**Input (Tier A):** One block per host, 21 fields. 20 identical across all 5
hosts. `snmp_location` differs per host.

**Ideal Tier B:**

```yaml
BaseInfra:
  ntp_primary: "10.100.1.1"
  ntp_secondary: "10.100.1.2"
  ntp_source: Loopback0
  ntp_auth_enabled: true
  ntp_auth_key_id: 42
  ntp_auth_algo: md5
  log_host: "10.100.2.1"
  log_protocol: tcp
  log_port: 514
  log_facility: local6
  log_severity: informational
  log_buffer: 1048576
  aaa_login: RADIUS_AUTH
  aaa_enable: LOCAL
  aaa_authz: RADIUS_AUTH
  aaa_acct: RADIUS_ACCT
  radius_host_1: "10.100.3.1"
  radius_host_2: "10.100.3.2"
  radius_timeout: 5
  snmp_community: ARCHETYPAL_RO
  snmp_contact: noc@archetypal.lab
```

**Ideal Tier C (per host):**

```yaml
rtr-00:
  _class: BaseInfra
  snmp_location: site-A

rtr-01:
  _class: BaseInfra
  snmp_location: site-B
```

**Scoring:**

1. Class count — exactly 1
2. Static field count — exactly 20
3. Only `snmp_location` appears in Tier C per host
4. B + C reconstructs original exactly

---

## Trap 1 — Type Coercion (adjacent to Set A)

**Purpose:** Negative test. Verify decoct does NOT merge textually different
values, even when they are logically equivalent.

**Placement:** Adjacent to Set A in each file. Same depth, similar field names,
looks compressible at a glance.

**Input (Tier A):**

```yaml
# rtr-00
snmp_auth_enabled: true
snmp_encrypt: true
snmp_version: 3

# rtr-01
snmp_auth_enabled: "true"
snmp_encrypt: true
snmp_version: 3

# rtr-02
snmp_auth_enabled: true
snmp_encrypt: "yes"
snmp_version: "3"
```

`snmp_encrypt` has `true` on rtr-00 and `"yes"` on rtr-02. `snmp_version` has
`3` (int) on rtr-00 and `"3"` (string) on rtr-02. These are textually different.

**Ideal output:** No class extracted. Each host carries raw data. Decoct must
not normalise `"true"` → `true` or `"3"` → `3`.

**Scoring:**

1. Zero classes created for this block
2. All values preserved exactly as-is (type and value)
3. Textual type differences were NOT silently normalised

---

## Set B — Subtraction

**Purpose:** Delta compression (key removal).

**What it tests:** Can decoct extract a shared class and correctly express that
some hosts are missing fields from the base?

**Input (Tier A):** QoS policy block per host, all values identical. Files
progressively drop keys from the full set.

- rtr-00: all 11 fields
- rtr-01: no `burst`
- rtr-02: no `burst`, `wred_min`, `wred_max`
- rtr-03: no `burst`, `wred_min`, `wred_max`, `ecn`
- rtr-04: no `burst`, `wred_min`, `wred_max`, `ecn`, `shaping_rate`, `queue_limit`

**Ideal Tier B:**

```yaml
QosPolicy:
  policy_name: CORE-QOS
  bandwidth_pct: 20
  priority: true
  dscp: ef
  police_rate: 100mbps
  burst: 50ms
  queue_limit: 512
  wred_min: 64
  wred_max: 256
  ecn: true
  shaping_rate: 1gbps
```

**Ideal Tier C:**

```yaml
rtr-00:
  _class: QosPolicy

rtr-01:
  _class: QosPolicy
  _remove: [burst]

rtr-02:
  _class: QosPolicy
  _remove: [burst, wred_min, wred_max]

rtr-03:
  _class: QosPolicy
  _remove: [burst, wred_min, wred_max, ecn]

rtr-04:
  _class: QosPolicy
  _remove: [burst, wred_min, wred_max, ecn, shaping_rate, queue_limit]
```

**Scoring:**

1. Exactly 1 class (no inheritance chain — flat removal)
2. `_remove` lists are correct per host
3. rtr-00 has no overrides or removals
4. B + C reconstructs original exactly

---

## Set C — Addition

**Purpose:** Delta compression (key addition).

**What it tests:** Can decoct extract a shared base and correctly represent that
some hosts have extra fields?

**Input (Tier A):** Monitoring target block per host, base values identical.
Files progressively add extra keys.

- rtr-00: 5 base fields only
- rtr-01: base + `threshold_info`
- rtr-02: base + `threshold_info`, `escalation_group`
- rtr-03: base + `threshold_info`, `escalation_group`, `suppress_flap`
- rtr-04: base + `threshold_info`, `escalation_group`, `suppress_flap`,
  `correlation_id`, `dependency_check`

**Ideal Tier B:**

```yaml
MonitorTarget:
  polling_interval: 300
  timeout: 10
  retries: 3
  threshold_warn: 75
  threshold_crit: 95
```

**Ideal Tier C:**

```yaml
rtr-00:
  _class: MonitorTarget

rtr-01:
  _class: MonitorTarget
  threshold_info: 50

rtr-02:
  _class: MonitorTarget
  threshold_info: 50
  escalation_group: tier2

rtr-03:
  _class: MonitorTarget
  threshold_info: 50
  escalation_group: tier2
  suppress_flap: true

rtr-04:
  _class: MonitorTarget
  threshold_info: 50
  escalation_group: tier2
  suppress_flap: true
  correlation_id: auto
  dependency_check: true
```

**Scoring:**

1. Exactly 1 class (no subclasses for additions)
2. Extra fields appear directly in Tier C as overrides
3. rtr-00 has no overrides
4. B + C reconstructs original exactly

---

## Trap 2 — Low Jaccard Disguised (adjacent to Set C)

**Purpose:** Negative test. Verify decoct does NOT extract a class from blocks
that look structurally similar but share no actual fields.

**Placement:** Adjacent to Set C. Same parent key, same nesting depth, similar
field count per host. Looks compressible.

**Input (Tier A):**

```yaml
# rtr-00
service_policy:
  telemetry:
    interval: 30
    protocol: grpc
    encoding: gpb

# rtr-01
service_policy:
  sflow:
    sample_rate: 1024
    collector: "10.0.1.1"
    port: 6343

# rtr-02
service_policy:
  netflow:
    version: 9
    exporter: "10.0.2.1"
    template_timeout: 600

# rtr-03
service_policy:
  streaming:
    sensor_group: ENVMON
    destination: "10.0.3.1"
    cadence: 10000

# rtr-04
service_policy:
  snmp_polling:
    community: MONITOR_RO
    interval: 300
    target: "10.0.4.1"
```

All under `service_policy`, all 3 child fields, all at the same depth. But the
child key and field names are completely different per host. Jaccard ≈ 0.

**Ideal output:** No class extracted. Each host carries raw data.

**Scoring:**

1. Zero classes created for this block
2. All data preserved as-is per host
3. Shared parent key (`service_policy`) did NOT cause false class extraction
4. Similar field count and depth did NOT cause false class extraction

---

## Set D — Identity

**Purpose:** Unique-per-host values (identity fields).

**What it tests:** Can decoct distinguish between fields that are overrides
(could share a value) and fields that must be unique per host?

**Input (Tier A):** Loopback interface block per host. 9 fields identical,
`ipv4_address` unique per host.

**Ideal Tier B:**

```yaml
LoopbackInterface:
  interface_type: Loopback
  description: Router-ID
  mtu: 1500
  admin_state: up
  vrf: default
  isis_passive: true
  isis_metric: 10
  mpls_ldp: true
  mpls_te: false
  _identity:
    - ipv4_address
```

**Ideal Tier C:**

```yaml
rtr-00:
  _class: LoopbackInterface
  ipv4_address: 10.0.0.0

rtr-01:
  _class: LoopbackInterface
  ipv4_address: 10.0.0.1

rtr-02:
  _class: LoopbackInterface
  ipv4_address: 10.0.0.2

rtr-03:
  _class: LoopbackInterface
  ipv4_address: 10.0.0.3

rtr-04:
  _class: LoopbackInterface
  ipv4_address: 10.0.0.4
```

**Scoring:**

1. `ipv4_address` identified as `_identity` (not just an override)
2. 9 static fields correctly in class
3. No redundant `node_id` stored (hostname is already the Tier C key)
4. B + C reconstructs original exactly

---

## Trap 3 — Structural Nesting (adjacent to Set D)

**Purpose:** Negative test. Verify decoct does NOT conflate logically equivalent
data that differs structurally.

**Placement:** Adjacent to Set D. Same logical value, different YAML structure.

**Input (Tier A):**

```yaml
# rtr-00
dns_server: "10.100.1.1"
dns_search: archetypal.lab

# rtr-01
dns:
  server: "10.100.1.1"
  search: archetypal.lab

# rtr-02
dns_server: "10.100.1.1"
dns_search: archetypal.lab

# rtr-03
dns:
  server: "10.100.1.1"
  search: archetypal.lab

# rtr-04
dns_config:
  primary_server: "10.100.1.1"
  search_domain: archetypal.lab
```

Same logical data (DNS server and search domain), three different structures.
rtr-00/02 are flat. rtr-01/03 are nested under `dns`. rtr-04 uses different key
names under `dns_config`.

**Ideal output:** Decoct may extract a class for the flat pair (rtr-00, rtr-02)
and a class for the nested pair (rtr-01, rtr-03). rtr-04 is raw (unique
structure). It must NOT merge all five into one class.

**Scoring:**

1. At most 2 classes (flat pair and nested pair)
2. rtr-04 carried as raw data (no class)
3. Flat and nested structures NOT merged
4. Different key names NOT treated as equivalent

---

## Set E — Heterogeneous

**Purpose:** Classification boundary (low Jaccard).

**What it tests:** Can decoct correctly determine that structurally different
data should NOT be compressed, even with incidental field name overlap?

**Input (Tier A):** Each host has a completely different configuration block with
a different schema. A few field names (`timeout`, `protocol`) appear in multiple
hosts coincidentally.

```yaml
# rtr-00 (BGP)
protocol: bgp
neighbor: "10.1.0.0"
remote_as: 65100
family: ipv4-unicast
graceful_restart: true
timeout: 30

# rtr-01 (static route)
type: static_route
prefix: "10.99.0.0/24"
next_hop: "10.1.0.1"
ad: 200
tag: 100

# rtr-02 (ACL)
acl_name: PROTECT-RE
seq: 10
action: permit
protocol: tcp
src: "10.100.0.0/24"
dst: any

# rtr-03 (TE tunnel)
tunnel_id: 1
destination: "10.0.0.99"
bandwidth: 1g
path_type: dynamic
timeout: 30

# rtr-04 (TACACS)
host: "10.100.4.0"
port: 49
key_encrypted: 0F5A3E7C
timeout: 10
```

`timeout` appears in rtr-00, rtr-03, rtr-04. `protocol` appears in rtr-00,
rtr-02. This is incidental overlap.

**Ideal Tier B:** (nothing)

**Ideal Tier C:**

```yaml
rtr-00:
  protocol: bgp
  neighbor: "10.1.0.0"
  remote_as: 65100
  family: ipv4-unicast
  graceful_restart: true
  timeout: 30

rtr-01:
  type: static_route
  prefix: "10.99.0.0/24"
  next_hop: "10.1.0.1"
  ad: 200
  tag: 100

rtr-02:
  acl_name: PROTECT-RE
  seq: 10
  action: permit
  protocol: tcp
  src: "10.100.0.0/24"
  dst: any

rtr-03:
  tunnel_id: 1
  destination: "10.0.0.99"
  bandwidth: 1g
  path_type: dynamic
  timeout: 30

rtr-04:
  host: "10.100.4.0"
  port: 49
  key_encrypted: 0F5A3E7C
  timeout: 10
```

**Scoring:**

1. Zero classes created
2. All fields preserved verbatim per host
3. Incidental field name overlap (`timeout`, `protocol`) did NOT trigger false
   class extraction

---

## Set G — Ordered List

**Purpose:** Canonicalisation (list ordering matters).

**What it tests:** Can decoct recognise that a list with a different order is
NOT the same as the canonical order, and handle it without forcing compression?

**Input (Tier A):** Maintenance schedule with 10 ordered steps. 4 hosts have
identical order. 1 host (rtr-03) has steps 4 and 5 swapped.

**Ideal Tier B:**

```yaml
MaintenanceSchedule:
  approval_required: true
  steps:
    - drain_traffic
    - snapshot_config
    - backup_database
    - apply_patches
    - restart_services
    - validate_health
    - run_smoke_tests
    - restore_traffic
    - notify_stakeholders
    - close_ticket
```

**Ideal Tier C:**

```yaml
rtr-00:
  _class: MaintenanceSchedule

rtr-01:
  _class: MaintenanceSchedule

rtr-02:
  _class: MaintenanceSchedule

rtr-03:
  approval_required: true
  steps:
    - drain_traffic
    - snapshot_config
    - backup_database
    - restart_services
    - apply_patches
    - validate_health
    - run_smoke_tests
    - restore_traffic
    - notify_stakeholders
    - close_ticket

rtr-04:
  _class: MaintenanceSchedule
```

rtr-03 carries the full list inline — no class reference, no delta notation.
The difference is visible by direct comparison with the class definition.

**Scoring:**

1. Class extracted from the 4 matching hosts
2. rtr-03 carried as raw data — no `_class`, full list inline
3. Reordered list NOT treated as matching the class
4. B + C reconstructs original exactly

---

## Set L — Repeating Entities (Interfaces)

**Purpose:** Multiple instances of the same entity type per host.

**What it tests:** Can decoct extract a shared class for entities that repeat
within a host, correctly identify identity fields, and handle per-instance
overrides and removals?

**Input (Tier A):** Each host has 8 interfaces. 6 fields per interface. `mtu`,
`speed`, `duplex`, `admin_state`, `isis_metric`, `mpls_ldp` are identical across
all interfaces on all hosts. `name` and `ipv4_address` are unique per interface.
One interface on rtr-02 has `speed: 1g` instead of `10g`. One interface on
rtr-03 has no `mpls_ldp` field.

**Ideal Tier B:**

```yaml
InterfaceConfig:
  mtu: 9000
  speed: 10g
  duplex: full
  admin_state: up
  isis_metric: 10
  mpls_ldp: true
  _identity:
    - name
    - ipv4_address
```

**Ideal Tier C:**

```yaml
rtr-00:
  _class: InterfaceConfig
  instances:
    - {name: GigE0/0/0/0, ipv4_address: 10.0.0.1}
    - {name: GigE0/0/0/1, ipv4_address: 10.0.0.2}
    - {name: GigE0/0/0/2, ipv4_address: 10.0.0.3}
    - {name: GigE0/0/0/3, ipv4_address: 10.0.0.4}
    - {name: GigE0/0/0/4, ipv4_address: 10.0.0.5}
    - {name: GigE0/0/0/5, ipv4_address: 10.0.0.6}
    - {name: GigE0/0/0/6, ipv4_address: 10.0.0.7}
    - {name: GigE0/0/0/7, ipv4_address: 10.0.0.8}

rtr-01:
  _class: InterfaceConfig
  instances:
    - {name: GigE0/0/0/0, ipv4_address: 10.0.1.1}
    - {name: GigE0/0/0/1, ipv4_address: 10.0.1.2}
    - {name: GigE0/0/0/2, ipv4_address: 10.0.1.3}
    - {name: GigE0/0/0/3, ipv4_address: 10.0.1.4}
    - {name: GigE0/0/0/4, ipv4_address: 10.0.1.5}
    - {name: GigE0/0/0/5, ipv4_address: 10.0.1.6}
    - {name: GigE0/0/0/6, ipv4_address: 10.0.1.7}
    - {name: GigE0/0/0/7, ipv4_address: 10.0.1.8}

rtr-02:
  _class: InterfaceConfig
  instances:
    - {name: GigE0/0/0/0, ipv4_address: 10.0.2.1}
    - {name: GigE0/0/0/1, ipv4_address: 10.0.2.2}
    - {name: GigE0/0/0/2, ipv4_address: 10.0.2.3}
    - {name: GigE0/0/0/3, ipv4_address: 10.0.2.4}
    - {name: GigE0/0/0/4, ipv4_address: 10.0.2.5}
    - {name: GigE0/0/0/5, ipv4_address: 10.0.2.6}
    - {name: GigE0/0/0/6, ipv4_address: 10.0.2.7, speed: 1g}
    - {name: GigE0/0/0/7, ipv4_address: 10.0.2.8}

rtr-03:
  _class: InterfaceConfig
  instances:
    - {name: GigE0/0/0/0, ipv4_address: 10.0.3.1}
    - {name: GigE0/0/0/1, ipv4_address: 10.0.3.2}
    - {name: GigE0/0/0/2, ipv4_address: 10.0.3.3}
    - {name: GigE0/0/0/3, ipv4_address: 10.0.3.4}
    - {name: GigE0/0/0/4, ipv4_address: 10.0.3.5}
    - {name: GigE0/0/0/5, ipv4_address: 10.0.3.6}
    - {name: GigE0/0/0/6, ipv4_address: 10.0.3.7}
    - {name: GigE0/0/0/7, ipv4_address: 10.0.3.8, _remove: [mpls_ldp]}

rtr-04:
  _class: InterfaceConfig
  instances:
    - {name: GigE0/0/0/0, ipv4_address: 10.0.4.1}
    - {name: GigE0/0/0/1, ipv4_address: 10.0.4.2}
    - {name: GigE0/0/0/2, ipv4_address: 10.0.4.3}
    - {name: GigE0/0/0/3, ipv4_address: 10.0.4.4}
    - {name: GigE0/0/0/4, ipv4_address: 10.0.4.5}
    - {name: GigE0/0/0/5, ipv4_address: 10.0.4.6}
    - {name: GigE0/0/0/6, ipv4_address: 10.0.4.7}
    - {name: GigE0/0/0/7, ipv4_address: 10.0.4.8}
```

### Instance-Level Mechanics

Instance-level supports the same mechanics as host-level:

| Condition | Representation |
|-----------|---------------|
| Field inherited from class | Absent from instance |
| Field overridden for this instance | Present with new value (e.g. `speed: 1g`) |
| Field removed for this instance | `_remove: [field_name]` |

**Scoring:**

1. One class extracted with 6 shared fields
2. `name` and `ipv4_address` identified as `_identity`
3. Instances carry only identity fields + per-instance overrides/removals
4. rtr-02 GigE0/0/0/6 override (`speed: 1g`) correctly placed inline
5. rtr-03 GigE0/0/0/7 removal (`_remove: [mpls_ldp]`) correctly placed inline
6. All other instances are identity-only (maximum compression)
7. B + C reconstructs original exactly

---

## Set M — Nested Overrides

**Purpose:** Path-qualified overrides at depth using dot notation.

**What it tests:** Can decoct correctly override, add, remove, and replace
fields and subtrees within nested structures without ambiguity? Covers all dot
notation operations: scalar override at depth, same field name at different
depths, nested field removal, subtree addition, subtree removal, and list
replacement.

**Input (Tier A):** Service configuration block with nested sub-sections. Same
field name (`interval`) appears at multiple depths. Hosts exercise different
dot notation operations.

```yaml
# rtr-00 (matches base exactly)
service_policy:
  interval: 30
  retry: 3
  telemetry:
    interval: 30
    protocol: grpc
    encoding: gpb
    collectors:
      - "10.0.0.1"
      - "10.0.0.2"
  logging:
    interval: 60
    facility: local6
    severity: informational

# rtr-01 (scalar override at depth + list replacement)
service_policy:
  interval: 60
  retry: 3
  telemetry:
    interval: 30
    protocol: grpc
    encoding: gpb
    collectors:
      - "10.0.0.3"
      - "10.0.0.4"
      - "10.0.0.5"
  logging:
    interval: 60
    facility: local6
    severity: informational

# rtr-02 (overrides at multiple depths + new subtree added)
service_policy:
  interval: 60
  retry: 3
  telemetry:
    interval: 30
    protocol: grpc
    encoding: json
    collectors:
      - "10.0.0.1"
      - "10.0.0.2"
    auth:
      method: certificate
      ca: /etc/pki/ca.pem
      verify: true
  logging:
    interval: 60
    facility: local6
    severity: informational

# rtr-03 (nested field removal + subtree removal)
service_policy:
  interval: 30
  retry: 3
  telemetry:
    interval: 30
    protocol: grpc
    encoding: gpb
    collectors:
      - "10.0.0.1"
      - "10.0.0.2"

# rtr-04 (combination: override + subtree remove + list replace + field remove)
service_policy:
  interval: 60
  retry: 3
  telemetry:
    interval: 30
    protocol: grpc
    collectors:
      - "10.0.0.9"
  logging:
    interval: 120
    facility: local6
    severity: informational
```

**Ideal Tier B:**

```yaml
ServiceConfig:
  service_policy:
    interval: 30
    retry: 3
    telemetry:
      interval: 30
      protocol: grpc
      encoding: gpb
      collectors:
        - "10.0.0.1"
        - "10.0.0.2"
    logging:
      interval: 60
      facility: local6
      severity: informational
```

**Ideal Tier C:**

```yaml
rtr-00:
  _class: ServiceConfig

rtr-01:
  _class: ServiceConfig
  service_policy.interval: 60
  service_policy.telemetry.collectors: ["10.0.0.3", "10.0.0.4", "10.0.0.5"]

rtr-02:
  _class: ServiceConfig
  service_policy.interval: 60
  service_policy.telemetry.encoding: json
  service_policy.telemetry.auth.method: certificate
  service_policy.telemetry.auth.ca: /etc/pki/ca.pem
  service_policy.telemetry.auth.verify: true

rtr-03:
  _class: ServiceConfig
  _remove: [service_policy.logging]

rtr-04:
  _class: ServiceConfig
  service_policy.interval: 60
  service_policy.logging.interval: 120
  service_policy.telemetry.collectors: ["10.0.0.9"]
  _remove: [service_policy.telemetry.encoding]
```

### Scenarios covered

| Host | Operations | Dot notation features tested |
|------|-----------|------------------------------|
| rtr-00 | None — matches class | Baseline |
| rtr-01 | Scalar override + list replace | `service_policy.interval: 60`, full list replacement |
| rtr-02 | Overrides at 2 depths + new subtree | `service_policy.telemetry.auth.*` (subtree add via per-leaf keys) |
| rtr-03 | Entire subtree removal | `_remove: [service_policy.logging]` |
| rtr-04 | Override + list replace + field remove | All operations combined in one host |

**Scoring:**

1. Dot-notation overrides correctly target specific depth
2. `service_policy.interval` and `service_policy.telemetry.interval` handled
   independently — same field name at different paths, no confusion
3. `_remove` with dot-notation targets correct nested field
4. `_remove: [service_policy.logging]` removes entire subtree including all children
5. New subtree (`telemetry.auth`) added via per-leaf dot-notation keys
6. List replacement is wholesale — no partial list patching
7. rtr-00 matches class exactly — no overrides
8. rtr-04 combines overrides, list replacement, and removal in one host entry
9. B + C reconstructs original exactly

---

## Trap 4 — Same Children, Different Parents (adjacent to Set M)

**Purpose:** Negative test. Verify decoct compares full paths, not just leaf
field names, when assessing similarity.

**Placement:** Adjacent to Set M. Identical leaf values under different parent
keys. High leaf-level Jaccard, zero path-level Jaccard.

**Input (Tier A):**

```yaml
# rtr-00
service_policy:
  telemetry:
    interval: 30
    protocol: grpc
    encoding: gpb

# rtr-01
service_policy:
  sflow:
    interval: 30
    protocol: grpc
    encoding: gpb

# rtr-02
service_policy:
  netflow:
    interval: 30
    protocol: grpc
    encoding: gpb

# rtr-03
service_policy:
  streaming:
    interval: 30
    protocol: grpc
    encoding: gpb

# rtr-04
service_policy:
  diagnostics:
    interval: 30
    protocol: grpc
    encoding: gpb
```

Leaf values identical across all 5 hosts (`interval: 30`, `protocol: grpc`,
`encoding: gpb`). But the full paths differ:
`service_policy.telemetry.interval` vs `service_policy.sflow.interval` etc.
These are different configuration sections that happen to use the same transport
settings.

**Ideal output:** No class extracted. Each host carries raw data. Decoct must
use full path comparison, not leaf-only.

**Scoring:**

1. Zero classes created
2. All data preserved as-is per host
3. Identical leaf values under different parent keys did NOT trigger false class
   extraction
4. Full-path Jaccard used, not leaf-only Jaccard

---

## Summary

### Positive Tests (should compress)

| Set | Tests | Class count | Key mechanic |
|-----|-------|-------------|--------------|
| A | Overlap | 1 | Override |
| B | Subtraction | 1 | `_remove` |
| C | Addition | 1 | Extra fields in Tier C |
| D | Identity | 1 | `_identity` |
| G | Ordered list | 1 | Non-matching host carries raw data |
| L | Repeating entities | 1 | `instances` with per-instance override/remove |
| M | Nested overrides | 1 | Dot-notation override/remove/add subtree/replace list |

### Negative Tests (should NOT compress)

| Trap | Adjacent to | Tests | Expected classes |
|------|-------------|-------|-----------------|
| 1 — Type coercion | Set A | Textually different values not normalised | 0 |
| 2 — Low Jaccard | Set C | Similar structure, different fields | 0 |
| 3 — Structural nesting | Set D | Same data, different YAML paths | 0 or 2 (not 1) |
| 4 — Same children, different parents | Set M | Same leaf values, different parent paths | 0 |
| E — Heterogeneous | Standalone | Different schemas, incidental overlap | 0 |

### Format Primitives

```
_class: ClassName              # this host/instance inherits from ClassName
_remove: [field, ...]          # these fields from the class do not exist here
_remove: [a.b.field]           # nested field removal using dot notation
_remove: [a.b]                 # nested subtree removal (removes all children)
_identity: [field, ...]        # these fields are unique per host/instance (in Tier B)
instances:                     # list of entity instances (for repeating types)
parent.child.field: value      # nested scalar override using dot notation
parent.child.new_field: value  # nested field addition using dot notation
parent.child.list: [a, b]     # nested list replacement (whole list, no partial)
(no _class)                    # raw data, read as-is
```
