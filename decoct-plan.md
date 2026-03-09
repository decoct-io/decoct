# decoct

## Infrastructure Context Compression for LLMs

---

### The Problem

Infrastructure state is increasingly fed into LLM context windows — for AI-assisted troubleshooting, agent-driven operations, code generation against live state, and architecture review.

The source data is heterogeneous. Device configurations arrive as CLI output, XML from NETCONF, or YANG-modelled data via gRPC. Cloud and endpoint management state comes as JSON from Microsoft Graph, Azure ARM, or vendor APIs. Linux host state is collected as structured text from systemd, sysctl, and package managers. Container workloads are defined in Docker Compose YAML. Deployment intent lives in Ansible inventories, Terraform state, or Kubernetes manifests. Design standards and architecture decisions are scattered across wikis, documents, ADRs, and tribal knowledge.

All of this needs to reach the LLM as compact, high-value context. YAML is the natural output format — human-readable, token-efficient for hierarchical data, universally parseable. But the path from raw infrastructure data to an optimised YAML context window is full of waste: platform defaults the model already knows, system-managed metadata, fields irrelevant to the current question, and structural noise.

Worse, the design standards that govern how infrastructure *should* look are typically disconnected from the state data they govern — expensive in tokens when included, absent when they'd be most useful.

The result is a context window packed with noise, missing intent, and costing more than it should.

---

### The Approach

**decoct** is an LLM-powered context compression system for infrastructure data. It ingests diverse infrastructure sources, normalises them, and produces optimised YAML for LLM context windows — stripping defaults, removing noise, and highlighting deviations from your design standards.

The name comes from the process of extracting the essence of something by sustained application of heat. That's what the tool does: raw infrastructure data goes in, intelligence is applied, and what comes out is the concentrated essence — the information the model actually needs.

The system operates in three phases:

**Phase A: Assertion Preparation.** Your design standards, architecture decisions, and operational conventions are transformed into structured, machine-evaluable assertions. The LLM reads your documentation through a domain-specific scaffolding lens and produces candidate assertions. Humans review and commit them.

**Phase B: Schema Preparation.** Platform defaults and structural knowledge are extracted from the best available source for each ecosystem — formal machine-readable schemas where vendors provide them, LLM-learned schemas from your corpus where they don't. The adapter framework is open and extensible: any platform with an authoritative schema source can have an adapter.

**Phase C: Deterministic Processing.** On every compression run, the pipeline applies assertions and schemas as tree transformations — fast, free, predictable. When it encounters ambiguity or unknown structure, it falls back to the LLM for resolution, caching the answer for future runs. Stripped values are recorded in class definitions that allow the LLM to reconstitute full state when needed.

---

### One-Liner

Decoct your infrastructure for LLMs.

---

### Design Principles

1. **Diverse input, YAML output.** Ingests whatever format your infrastructure produces — XML, JSON, YANG, CLI output, prose documentation. Outputs valid YAML optimised for LLM context windows.

2. **Zero-setup value.** Works immediately on any input via LLM-direct compression. Gets faster, cheaper, and more precise over time as schemas and assertions are built.

3. **Best available schema source.** Authoritative vendor schemas where they exist. LLM-learned schemas where they don't. The adapter framework is open — any platform with a machine-readable schema can have an adapter contributed.

4. **Standards as first-class input.** Design assertions are a compression tier — conformant values are stripped, deviations are highlighted. The output is more aggressive *and* more informative than state compression alone.

5. **Scaffolding accelerates everything.** Domain-specific knowledge packs give the LLM expert-level context for each infrastructure domain, producing higher-quality assertions and schemas with less input.

6. **Reconstitutable.** Stripped values are recorded in class definitions. The LLM can combine compressed state with its class to reconstruct full state when the task requires it.

7. **Secrets never leave.** Infrastructure data is full of credentials, keys, and sensitive topology. A dedicated secrets-stripping pass runs before any data reaches an LLM provider, using entropy detection and pattern matching. This is a safety guarantee, not an optional feature.

8. **Human-in-the-loop for trust.** Generated assertions, schemas, and resolution decisions are committed to git and reviewed before use. The LLM proposes; the human approves.

9. **Measurable.** Every run reports token counts. An evaluation harness validates that compression preserves LLM comprehension.

---

### What It Is Not

- Not a YAML minifier (whitespace savings are incidental)
- Not a new data format (output is standard YAML)
- Not a prompt compression tool (it operates on structured data, not prose)
- Not a compliance engine (it surfaces deviations, it doesn't enforce policy)

---

### Core Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   PHASE A: ASSERTION PREPARATION                │
│                                                                 │
│  ┌──────────────────────┐    ┌────────────────────────────────┐ │
│  │  Scaffolding          │    │  Input                         │ │
│  │  (domain expertise    │    │  (organisation's material)     │ │
│  │   pack — generic,     │    │                                │ │
│  │   reusable)           │    │  • Design documents (prose)    │ │
│  │                       │    │  • Architecture standards      │ │
│  │  • Typical assertions │    │  • Wiki / BookStack pages      │ │
│  │  • Reference patterns │    │  • Golden configs (any format) │ │
│  │  • Known anti-patterns│    │  • Convention documents         │ │
│  │  • Interview questions│    │  • Worked examples             │ │
│  │  • Test cases         │    │  • Team decisions / ADRs       │ │
│  │  • Output examples    │    │  • Runbooks                    │ │
│  └──────────┬───────────┘    └──────────────┬─────────────────┘ │
│             │                               │                   │
│             ▼                               ▼                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  LLM reads input THROUGH scaffolding lens               │    │
│  │                                                         │    │
│  │  Scaffolding provides: what to look for, what good      │    │
│  │  looks like, what questions to ask, output format        │    │
│  │                                                         │    │
│  │  Input provides: this organisation's specific            │    │
│  │  decisions, conventions, exceptions, context             │    │
│  └────────────────────────┬────────────────────────────────┘    │
│                           ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Candidate assertions → validate against fixtures        │    │
│  │  → human review → git commit                             │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    PHASE B: SCHEMA PREPARATION                  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              Schema Adapter Framework (open, extensible) │    │
│  │                                                         │    │
│  │  Built-in adapters          │  LLM-learned adapter      │    │
│  │  (authoritative sources)    │  (corpus analysis)        │    │
│  │                             │                           │    │
│  │  ┌──────────────────────┐   │  ┌─────────────────────┐  │    │
│  │  │ YANG      IOS-XE     │   │  │ Any data corpus     │  │    │
│  │  │ adapter   IOS-XR     │   │  │ + scaffolding pack  │  │    │
│  │  │           Junos      │   │  │                     │  │    │
│  │  ├──────────────────────┤   │  │ → LLM infers        │  │    │
│  │  │ OpenAPI   K8s        │   │  │   defaults,         │  │    │
│  │  │ adapter   Graph API  │   │  │   conventions,      │  │    │
│  │  ├──────────────────────┤   │  │   system fields     │  │    │
│  │  │ JSON      Compose    │   │  │                     │  │    │
│  │  │ Schema    Terraform  │   │  │ → distinguishes     │  │    │
│  │  │ adapter   ARM        │   │  │   platform defaults  │  │    │
│  │  ├──────────────────────┤   │  │   from local        │  │    │
│  │  │ ADMX      GPO        │   │  │   conventions       │  │    │
│  │  │ adapter   Intune     │   │  └─────────────────────┘  │    │
│  │  ├──────────────────────┤   │                           │    │
│  │  │ Augeas    Linux      │   │  Community adapters       │    │
│  │  │ adapter   app cfg    │   │  (same interface,         │    │
│  │  ├──────────────────────┤   │   contributed for any     │    │
│  │  │ (community-          │   │   platform with an        │    │
│  │  │  contributed)        │   │   authoritative schema)   │    │
│  │  └──────────────────────┘   │                           │    │
│  │                             │                           │    │
│  │             ▼               │           ▼               │    │
│  │  ┌──────────────────────────────────────────────────┐   │    │
│  │  │  Unified internal schema format                  │   │    │
│  │  │  (defaults, drop patterns, field metadata)       │   │    │
│  │  │  → human review → git commit                     │   │    │
│  │  └──────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                 PHASE C: DETERMINISTIC PROCESSING               │
│                                                                 │
│  ┌──────────────────┐  ┌────────────┐  ┌────────────┐          │
│  │  Infrastructure   │  │ Assertions │  │  Schemas   │          │
│  │  data (any format)│  └─────┬──────┘  └─────┬──────┘          │
│  └────────┬─────────┘        │               │                  │
│           │                  │               │                  │
│           ▼                  │               │                  │
│  ┌─────────────────┐        │               │                  │
│  │  Normalise       │        │               │                  │
│  │  to YAML         │        │               │                  │
│  └────────┬────────┘        │               │                  │
│           │                  │               │                  │
│           ▼                  │               │                  │
│  ┌─────────────────┐        │               │                  │
│  │  Strip secrets   │        │               │                  │
│  │  (before any LLM │        │               │                  │
│  │   contact)       │        │               │                  │
│  └────────┬────────┘        │               │                  │
│           │                  │               │                  │
│           ▼                  ▼               ▼                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Compression Pipeline (ordered passes)                  │    │
│  │                                                         │    │
│  │  strip-comments ──▶ strip-defaults (schema)             │    │
│  │  ──▶ drop-fields ──▶ strip-conformant (assertions)      │    │
│  │  ──▶ annotate-deviations ──▶ deviation-summary          │    │
│  │  ──▶ emit-class-definition                              │    │
│  └────────────────────────┬────────────────────────────────┘    │
│                           │                                     │
│              ┌────────────┼─────────────┐                       │
│              │    on ambiguity /        │                        │
│              │    unknown structure     │                        │
│              ▼                          ▼                        │
│  ┌─────────────────────┐  ┌────────────────────────┐           │
│  │  LLM resolution     │  │  Operator escalation   │           │
│  │  (auto mode)        │  │  (interactive mode)    │           │
│  │  → cache answer     │  │  → confirm + cache     │           │
│  └─────────────────────┘  └────────────────────────┘           │
│                           │                                     │
│                           ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Output                                                 │    │
│  │  ┌───────────────────────┐  ┌────────────────────────┐  │    │
│  │  │ Compressed context    │  │ Class definition       │  │    │
│  │  │ (deviations,          │  │ (stripped defaults +   │  │    │
│  │  │  meaningful state,    │  │  assertions for        │  │    │
│  │  │  annotations,         │  │  reconstitution)       │  │    │
│  │  │  summary preamble)    │  │                        │  │    │
│  │  └───────────────────────┘  └────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

### Phase A: Assertion Preparation

Assertions are structured, machine-evaluable declarations about how infrastructure should be configured. They represent design standards, architectural decisions, and operational conventions.

#### Scaffolding vs Input

**Scaffolding** is a domain expertise pack — pre-prepared, generic to a domain, reusable across organisations. It's the equivalent of giving a consultant a briefing book before a client engagement. The consultant doesn't need to read the client's documents yet — they need to know what questions to ask, what good looks like, what the common patterns and anti-patterns are, and what assertions typically matter in this domain.

**Input** is the organisation's actual material — their specific design documents, architecture standards, golden configs, wiki pages, convention documents, worked examples. This is what varies per organisation. It's messy, incomplete, possibly contradictory, and in whatever format the team uses — prose, XML, JSON, proprietary config files, or structured YAML.

The scaffolding tells the LLM *how to read* the input. Without scaffolding, the LLM reading a service provider's BGP design document might miss that a particular timer value is non-standard, because it doesn't know what standard looks like in that domain. With the `service-provider-core` scaffolding loaded, it knows that BGP keepalive 60 / hold 180 is the platform default, keepalive 10 / hold 30 is a common fast-convergence convention, and anything else is worth flagging as an assertion candidate.

#### Scaffolding Pack Structure

```
scaffolding/
└── docker-services/
    ├── manifest.yaml            # metadata, version, dependencies
    ├── typical-assertions.yaml  # common assertions in this domain
    ├── reference-patterns.yaml  # what good looks like
    ├── anti-patterns.yaml       # what bad looks like
    ├── known-defaults.yaml      # platform defaults with sources
    ├── interview.yaml           # structured questions for the LLM
    ├── test-cases/              # fixture pairs (input → expected assertions)
    └── examples/                # example output assertions (few-shot)
```

Scaffolding packs are versioned. The manifest declares a semantic version and the CLI supports pinning to prevent unexpected changes when a pack updates:

```yaml
# scaffolding/docker-services/manifest.yaml
name: docker-services
version: 1.2.0
description: Docker Compose service conventions and patterns
platform: docker-compose
dependencies: []
```

```bash
# Pin to a specific pack version
decoct assertions init --domain docker-services@1.2
```

The `interview.yaml` gives the LLM a structured protocol when documentation is sparse:

```yaml
# scaffolding/docker-services/interview.yaml
questions:
  - id: restart-convention
    ask: "What restart policy do production services use?"
    options: [always, unless-stopped, on-failure, "no"]
    typical: unless-stopped
    why_it_matters: "Determines host-reboot resilience strategy"

  - id: network-strategy
    ask: "How do services that need external access get IP addresses?"
    options: [macvlan, host networking, published ports, load balancer]
    typical: [macvlan, published ports]
    why_it_matters: "Affects monitoring, firewall rules, DNS"

  - id: log-collection
    ask: "How are container logs collected?"
    options: [json-file + agent, syslog driver, journald, fluentd]
    typical: json-file + agent
    why_it_matters: "Determines logging driver and rotation config"
```

#### Scaffolding Packs

Phase 1:

| Pack | Domain | Key content |
|------|--------|-------------|
| `docker-services` | Container workloads | Compose conventions, restart patterns, networking modes, logging, image tagging, volume patterns, healthcheck norms |
| `linux-host` | OS configuration | systemd unit patterns, sysctl security/performance norms, filesystem conventions, user/group patterns, firewall baseline, time sync, log rotation |
| `ansible-automation` | Configuration management | Inventory conventions, role patterns, variable precedence norms, vault usage, connection defaults, fact caching |

Phase 2+:

| Pack | Domain |
|------|--------|
| `service-provider-core` | MPLS/SR design, BGP conventions, PE-CE patterns, QoS, label allocation |
| `data-centre` | Leaf-spine, VXLAN/EVPN, fabric design, overlay/underlay |
| `entra-intune` | Conditional Access, compliance policies, Autopilot, LAPS, security baselines |
| `it-management` | Monitoring, backup, DNS/DHCP, certificate lifecycle, change management |
| `kubernetes` | Resource patterns, RBAC, network policy, storage class conventions |

#### Assertion Format

```yaml
domain: services
scope: docker-deployment
version: 2025-03-01

assertions:
  - id: restart-policy
    assert: production services use restart=unless-stopped
    match:
      path: services.*.restart
      value: unless-stopped
    rationale: survive host reboot without systemd dependency
    severity: must

  - id: image-tags
    assert: production images use specific version tags
    match:
      path: services.*.image
      pattern: "^.+:.+(?<!latest)$"
    rationale: reproducibility and rollback capability
    severity: must

  - id: macvlan-networking
    assert: externally-accessible services use macvlan
    match:
      path: services.*.networks
      contains: macvlan
    rationale: clean IP allocation, avoids NAT complexity
    severity: must
    exceptions: development and testing environments
```

#### Assertion Field Reference

| Field | Purpose | Required |
|-------|---------|----------|
| `id` | Unique reference for cross-linking and reporting | Yes |
| `assert` | Human-readable declaration — one sentence | Yes |
| `match` | Machine-evaluable condition (path + value/pattern/range/contains) | No |
| `rationale` | Why this assertion exists — one sentence | Yes |
| `severity` | `must` / `should` / `may` (RFC 2119) | Yes |
| `exceptions` | When the assertion doesn't apply | No |
| `example` | Concrete illustration | No |
| `related` | IDs of related assertions | No |
| `source` | Origin (CIS, vendor best practice, internal) | No |

**Design note on match semantics.** The `match` field deliberately supports only simple structural conditions: single-path value equality, regex patterns, ranges, and contains checks. Cross-field dependencies ("if A is X then B must be Y") and semantic conditions ("externally-accessible services") are not expressed in `match`. There is no AND/OR/IF logic — that path leads to a DSL that's harder to author, harder to maintain, and worse than just asking the LLM.

Assertions that require semantic understanding omit `match` and serve as **LLM-context assertions** — the `assert` and `rationale` fields are loaded into context for the LLM to reason about during compression, but no deterministic pass evaluates them. This means not every assertion needs to be machine-evaluable. Some are documentation that the LLM uses directly, and that's by design.

#### Assertion Preparation Mechanism

```bash
# Interactive — LLM interviews operator using scaffolding questions
decoct assertions init --domain docker-services --interactive

# Document — LLM reads docs through scaffolding lens
decoct assertions init --domain docker-services \
  --docs ./standards/docker.md ./standards/networking.md

# Validate against real fixtures
decoct assertions validate \
  --assertions ./assertions/docker-services.yaml \
  --fixtures ./fixtures/docker-compose/
#   restart-policy: 11/12 match, 1 deviation (debug-tools)
#   image-tags: 10/12 match, 2 deviations
#   macvlan-networking: 8/12 match, 4 not applicable (internal)
#   
#   2 ambiguous results — resolve interactively? [Y/n]
```

---

### Phase B: Schema Preparation

Schemas capture platform defaults and structural knowledge — what values are standard for a given platform, what fields are system-managed, and what the data structure looks like.

#### Schema Adapter Framework

Different ecosystems have different levels of formal schema support. decoct uses the best available source for each through an open, extensible adapter framework. The following adapters are built-in; additional adapters can be contributed for any platform with an authoritative schema source.

| Adapter | Ecosystems | Source format | Coverage |
|---------|-----------|---------------|----------|
| YANG | IOS-XE, IOS-XR, Junos, EOS, NXOS | YANG models | Comprehensive, vendor-maintained |
| OpenAPI | Kubernetes, Microsoft Graph API | OpenAPI / JSON Schema | Comprehensive including CRDs |
| JSON Schema | Docker Compose, Terraform, ARM | JSON Schema | Comprehensive |
| ADMX | Windows Group Policy, Intune CSP | ADMX/ADML XML | Comprehensive |
| Augeas | Linux application configs (~200+ formats) | Augeas lenses | Strong for common apps |
| LLM-learned | Any platform | Corpus + scaffolding | Depends on corpus quality |

The adapter interface is simple: take a platform's authoritative schema source as input, produce decoct's internal schema format as output. Any platform with a machine-readable definition of its configuration structure, types, and defaults can have an adapter. The listed adapters are starting points, not an exhaustive list.

Every adapter produces the same internal format:

```yaml
# Internal schema format (adapter output)
platform: docker-compose
source: compose-spec-json-schema
confidence: authoritative          # or: high, medium, low
defaults:
  services.*.restart: "no"
  services.*.network_mode: bridge
  services.*.logging.driver: json-file
  networks.*.driver: bridge
  volumes.*.driver: local
drop_patterns:
  - services.*.container_name
  - version
system_managed:
  - "**.created_at"
  - "**.updated_at"
```

The compression pipeline doesn't know or care where the schema came from. The adapter is a preparation-time concern. Compression is uniform.

#### LLM-Learned Schema Preparation

For platforms without a formal adapter, the LLM analyses a corpus using the appropriate scaffolding pack:

```bash
decoct schema init --platform linux-state \
  --corpus ./infra-data/host-state/ \
  --scaffolding linux-host

#   Analysing 15 files...
#   Platform defaults identified: 12
#     systemd.units.*.Type: simple — confirmed systemd default
#     sysctl.vm.swappiness: 60 — confirmed kernel default
#   Local conventions detected (NOT platform defaults): 3
#     sysctl.net.ipv4.ip_forward: 1 — in 100% of files, but
#       kernel default is 0. Recommend expressing as an assertion.
#   System-managed fields: 4
#     **.uuid, **.last_change, ...
```

The critical distinction: platform defaults can be stripped unconditionally. Local conventions can only be stripped if a corresponding assertion exists. When the LLM detects a frequent value that isn't a known platform default, it routes it to an assertion candidate rather than baking it into the schema.

#### Formal Schema Adapter Preparation

```bash
# Compose spec JSON Schema
decoct schema init --platform docker-compose \
  --adapter json-schema \
  --source ./compose-spec.json

# Kubernetes OpenAPI (from cluster)
decoct schema init --platform kubernetes \
  --adapter openapi \
  --source https://cluster.local/openapi/v2

# YANG models (network devices)
decoct schema init --platform cisco-ios-xe \
  --adapter yang \
  --source ./yang-models/cisco-ios-xe/

# Microsoft Graph API metadata
decoct schema init --platform intune \
  --adapter odata-csdl \
  --source https://graph.microsoft.com/v1.0/\$metadata
```

Formal adapters produce schemas with `confidence: authoritative` — defaults are provably correct from the vendor's own specification. LLM-learned schemas produce `confidence: high` or `medium`. The pipeline can treat lower-confidence defaults more conservatively.

---

### Phase C: Deterministic Processing

The runtime compression phase. The primary path is deterministic: normalise input to YAML, then apply cached schemas and assertions as tree transformations. Fast, free, predictable, auditable.

#### Input Normalisation

Infrastructure data arrives in diverse formats. The normalisation step converts source data to YAML before the compression pipeline:

| Source format | Normalisation |
|---------------|---------------|
| YAML | Pass through |
| JSON (Graph API, Terraform, ARM) | JSON → YAML conversion |
| XML (NETCONF, ADMX, vendor exports) | XML → YAML with structure-aware mapping |
| CLI output (show running-config, etc.) | LLM-mediated parsing to structured YAML |
| YANG-modelled data | YANG-aware serialisation to YAML |

For well-structured formats (JSON, XML with known schemas), normalisation is deterministic. For unstructured or semi-structured formats (CLI output, proprietary dumps), the LLM handles the parsing. Normalisation results can be cached like any other artefact.

#### Compression Tiers

Each tier requires deeper knowledge and produces greater savings:

| Tier | Knowledge source | Action | Typical saving |
|------|-----------------|--------|---------------|
| Generic cleanup | None | Strip comments, drop fields by path | ~15% |
| Platform defaults | Schema (from adapter) | Strip values matching platform defaults | ~45% cumulative |
| Standards conformance | Assertions (from preparation) | Strip conformant values, annotate deviations | ~60% cumulative |

#### How Assertions Drive Compression

**Conformance stripping.** If a `must` assertion defines an expected value and the state matches, that value is stripped — it carries zero novel information.

```yaml
# Before (12 tokens)
services:
  acme-app:
    restart: unless-stopped
    image: acme-app:3.2.1

# After strip-conformant — restart matches assertion, removed (8 tokens)
services:
  acme-app:
    image: acme-app:3.2.1
```

**Deviation annotation.** Where state violates an assertion, an inline comment marks it at point of use.

```yaml
services:
  acme-app:
    restart: always  # [!] standard: unless-stopped
    image: acme-app:latest  # [!] standard: specific version tag
```

**Deviation summary preamble.**

```yaml
# decoct: 2 deviations from standards on app-01
# - acme-app.restart = always (standard: unless-stopped) [restart-policy]
# - acme-app.image uses :latest (standard: specific tag) [image-tags]
```

#### Classes: Reconstitution from Compressed State

When decoct strips a value — because it matches a platform default or conforms to an assertion — the LLM loses the ability to see it explicitly. For most tasks (troubleshooting, review, deviation analysis) this is correct: the model should focus on what's interesting, not what's expected. But for reconstruction tasks ("generate the full Compose file", "what would I see if I connected to this device?"), the model needs to recover what was stripped.

decoct records stripped values in a **class definition** — a compact representation of everything that was removed and why. The class is the inverse of the compression: combine the compressed state with its class, and you get back the full picture.

```yaml
# .decoct/classes/app-01-host.yaml
class: app-01-host
inherits:
  - linux-defaults         # platform defaults (from schema)
  - example-linux-standard  # organisational assertions
applied_defaults:
  systemd.units.*.Type: simple
  systemd.units.*.Restart: "no"
  sysctl.vm.swappiness: 60
  sysctl.net.ipv4.ip_forward: 0
applied_assertions:
  sysctl.net.ipv4.ip_forward: 1
  systemd.units.docker-*.Restart: always
  services.*.restart: unless-stopped
stripped_fields:
  - "**.uuid"
  - "**.last_change"
```

The compressed output references its class:

```yaml
# decoct: class=app-01-host, deviations=2
# - backup.service: Restart=no (assertion: always for docker units)
# - sysctl.vm.swappiness: 10 (default: 60)
interfaces:
  eth0:
    ip: 10.0.1.5/24
services:
  acme-app:
    image: acme-app:3.2.1
```

The class reference tells the LLM: "this document inherits from `app-01-host` — anything not shown matches that class." The model can reason without seeing every default:

- "What's the restart policy for acme-app?" → not shown, inherits from class → `unless-stopped`
- "What's the swappiness?" → shown explicitly as 10 — it's a deviation from default 60
- "Generate the full systemd unit for acme-app" → combine compressed state with class defaults

Classes compose through inheritance. `app-01-host` inherits from `linux-defaults` (platform) and `example-linux-standard` (organisational). This mirrors how compression itself works — platform defaults and assertion conformance are separate tiers.

Classes integrate naturally with tiered context loading: compressed state is always loaded (tier A), class definitions are loaded when the task needs full state (tier B), raw uncompressed data is available but rarely needed (tier C).

#### LLM Fallback and Resolution

The pipeline falls back to the LLM for unknown structure, ambiguous assertion matches, and inconsistency detection. Answers are cached as annotations for future deterministic use.

**Unknown structure.** Data contains fields not in any cached schema.

**Ambiguous assertion match.** A structural match is inconclusive — the path exists but applicability requires semantic understanding. Cached annotations resolve these:

```yaml
# .decoct/annotations/docker-services.yaml
- assertion: macvlan-networking
  annotations:
    - path: services.redis
      applicable: false
      reason: internal service, container-to-container only
    - path: services.acme-app
      applicable: true
      reason: serves external HTTP traffic
```

**Inconsistency detection.** State contradicts itself or the schema, suggesting data quality problems:

```yaml
# decoct: 1 inconsistency detected
# - backup.service: Restart=always conflicts with Type=oneshot
#   (oneshot services exit after running; Restart=always re-triggers)
```

Resolution modes:

```bash
decoct compress state.yaml --resolve auto          # LLM resolves, caches
decoct compress state.yaml --resolve interactive    # LLM suggests, operator confirms
decoct compress state.yaml --resolve skip           # leave uncertain items untouched
```

#### Decision Flow

```
For each key-value pair:
│
├─ Schema match?
│  ├─ Yes → Platform default? → Strip, record in class
│  │        Not default? → Keep, check assertions
│  └─ No → Unknown structure → resolve mode
│
├─ Assertion match?
│  ├─ Conclusive → Conformant? Strip, record in class.
│  │               Deviation? Keep, annotate inline.
│  └─ Ambiguous → Cached annotation? Use it.
│                  Otherwise → resolve mode.
│
├─ Inconsistency? → Flag in summary
│
└─ None of above → Keep as-is
```

---

### The Host Stack: Phase 1 Domain

Phase 1 focuses on a complete host context: Docker Compose, Linux state, and Ansible. These three describe a host from complementary angles:

| Layer | Source format(s) | Describes | Compression opportunity |
|-------|-----------------|-----------|------------------------|
| Docker Compose | YAML | What runs | High defaults ratio; JSON Schema available |
| Linux state | Structured collection output (YAML/JSON) | The OS underneath | Largest noise: sysctl, systemd defaults |
| Ansible | YAML (inventory, host_vars, group_vars) | Deployment intent | `ansible_facts` massive token sink |

They share overlapping concerns — networking, services, storage, users — which enables cross-domain understanding. Together they produce the context an LLM needs to reason about a host: what's running, what the OS looks like, how it was deployed, and where it deviates from standards.

#### Expected Savings

| Document | Raw | + Generic | + Schema | + Assertions | Total |
|----------|-----|-----------|----------|-------------|-------|
| Docker Compose | ~600 | ~520 (13%) | ~340 (43%) | ~260 (57%) | **57%** |
| Linux host state | ~1,400 | ~1,200 (14%) | ~650 (54%) | ~550 (61%) | **61%** |
| Ansible host vars | ~400 | ~340 (15%) | ~220 (45%) | ~180 (55%) | **55%** |
| **Combined host** | **~2,400** | **~2,060** | **~1,210** | **~990** | **59%** |

---

### User Experience

#### Day One — No Setup

```bash
pip install decoct

# Works immediately via LLM-direct compression
decoct compress docker-compose.yaml
#   Input:  612 tokens
#   Output: 258 tokens
#   Saved:  354 (57.8%)
#   Mode:   llm-direct (no cached schema)
```

No schemas to write. No config to create.

#### Build Assertions from Your Standards

```bash
# From documentation
decoct assertions init --domain docker-services \
  --docs ./standards/docker.md ./standards/networking.md

# Interactive (sparse/no documentation)
decoct assertions init --domain docker-services --interactive

# Validate against real fixtures
decoct assertions validate \
  --assertions ./assertions/docker.yaml \
  --fixtures ./fixtures/docker-compose/

# Review, commit
git add .decoct/ && git commit -m "docker service assertions"
```

#### Build Schemas from Your Infrastructure

```bash
# LLM-learned (analyses your corpus)
decoct schema init --platform linux-state \
  --corpus ./infra-data/host-state/ \
  --scaffolding linux-host

# Formal adapter (authoritative source)
decoct schema init --platform docker-compose \
  --adapter json-schema \
  --source ./compose-spec.json

# Review, commit
git add .decoct/ && git commit -m "host stack schemas"
```

#### Steady State — Instant, Free

```bash
decoct compress compose.yaml state.yaml host_vars.yaml \
  --profile host-context
#   Input:  2,412 tokens → Output: 988 tokens → Saved: 1,424 (59.0%)
#   Mode:   cached — Deviations: 3
#   Class:  .decoct/classes/app-01-host.yaml

# Pipeline from JSON source
curl -s https://graph.microsoft.com/... | decoct compress --schema intune

# Show what was stripped
decoct compress compose.yaml --show-removed

# Include class definition in output (for reconstruction tasks)
decoct compress compose.yaml --emit-class

# Stats only
decoct compress compose.yaml --stats-only
```

#### Refresh When Things Change

```bash
decoct schema init --platform linux-state \
  --corpus ./infra-data/host-state/ \
  --scaffolding linux-host \
  --update --diff
#   Schema linux-state:
#     + new default: systemd.units.*.ProtectSystem = full
#     - removed: sysctl.vm.swappiness (no longer consistent)
```

---

### Pass Registry

| Pass | Type | Description |
|------|------|-------------|
| `normalise` | Input | Convert source format to YAML |
| `strip-secrets` | Safety | Remove credentials, keys, and sensitive data before any LLM contact |
| `strip-comments` | Generic | Remove YAML comments |
| `drop-fields` | Configured | Remove fields by glob |
| `keep-fields` | Configured | Retain only specified fields |
| `strip-defaults` | Schema-aware | Remove platform default values |
| `strip-conformant` | Assertions-aware | Remove values matching assertions |
| `annotate-deviations` | Assertions-aware | Inline comments on violations |
| `deviation-summary` | Assertions-aware | Preamble listing non-conformances |
| `emit-class` | Structural | Record stripped values in class definition |
| `llm-direct` | LLM-mediated | Full LLM compression (fallback) |

`strip-secrets` runs immediately after normalisation and before any other pass — critically, before `llm-direct` or any LLM fallback path. This guarantees that sensitive data never reaches an LLM provider regardless of which resolution mode is selected. It uses entropy detection for high-randomness strings (API keys, tokens), regex patterns for common credential formats (AWS keys, connection strings, `password=`, base64-encoded certificates), and configurable path-based rules (always strip `*.env.*`, `*.secret`, `*.credentials`). Detected secrets are replaced with `[REDACTED]` placeholder tokens and logged (without values) for audit.

---

### Implementation Phases

#### Phase 1: Host Stack + LLM Core (8 weeks)

| Component | Detail |
|-----------|--------|
| LLM-direct compression | Works on any input immediately |
| **Strip-secrets pass** | Entropy detection + regex patterns, runs before any LLM contact |
| Assertion preparation | Interactive + document mode |
| Assertion validation | Against fixtures |
| Schema — LLM-learned | Corpus analysis with scaffolding |
| Schema — JSON Schema adapter | Docker Compose spec (cut if scope pressure; LLM-learned covers Compose adequately) |
| Input normalisation | YAML passthrough, JSON → YAML |
| Deterministic pipeline | All compression passes |
| Class definitions | Emit on every compression run |
| Fallback chain | Cached → LLM-direct → generic |
| Scaffolding packs | `docker-services`, `linux-host`, `ansible-automation` |
| Example assertions | Docker, networking, PKI, Linux hardening |
| Token counting | tiktoken, every run |
| CLI | compress, assertions, schema commands |
| Profiles | Named bundles |
| Benchmark corpus | Real data per domain |
| LLM eval harness | Comprehension before/after |

Gate: 40%+ savings, ≥95% accuracy retention.

#### Phase 2: Formal Adapters + Breadth (6-8 weeks)

YANG adapter (Cisco IOS-XE/XR), OpenAPI adapter (K8s), JSON Schema adapter (if not in Phase 1), ADMX adapter (Intune/GPO), OData CSDL adapter (Graph API). Scaffolding packs for `service-provider-core`, `entra-intune`, `kubernetes`. Input normalisation for XML and NETCONF sources. Diff-aware mode — compress two states and highlight the meaningful delta filtered through assertions ("what changed that matters"). Python API. Contribution guide.

Gate: formal adapter produces higher-confidence schemas than LLM-learned.

#### Phase 3: Advanced Features (8 weeks)

Augeas + Terraform + ARM adapters. Abbreviate-values, merge-documents, cross-document reasoning, anomaly detection. Claude Code integration, GitHub Action, pre-commit hook, streaming, compliance reports, security guide. Class hierarchy composition and inheritance.

#### Phase 4: Ecosystem (ongoing)

TypeScript/Node.js port, Go port, published benchmarks, documentation site.

---

### Repository Structure

```
decoct/
├── README.md
├── LICENSE                             # MIT
├── pyproject.toml
├── src/
│   └── decoct/
│       ├── __init__.py
│       ├── cli.py
│       ├── pipeline.py
│       ├── tokens.py
│       ├── normalise/
│       │   ├── __init__.py
│       │   ├── json_to_yaml.py
│       │   ├── xml_to_yaml.py
│       │   └── passthrough.py
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── client.py
│       │   ├── direct.py
│       │   ├── learn_schemas.py
│       │   ├── learn_assertions.py
│       │   └── resolve.py
│       ├── passes/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── strip_secrets.py
│       │   ├── strip_comments.py
│       │   ├── strip_defaults.py
│       │   ├── drop_fields.py
│       │   ├── keep_fields.py
│       │   ├── strip_conformant.py
│       │   ├── annotate_deviations.py
│       │   ├── deviation_summary.py
│       │   └── emit_class.py
│       ├── assertions/
│       │   ├── __init__.py
│       │   ├── loader.py
│       │   ├── matcher.py
│       │   └── format.py
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── llm_learned.py
│       │   ├── json_schema.py
│       │   └── _registry.py
│       ├── classes/
│       │   ├── __init__.py
│       │   ├── emitter.py
│       │   └── resolver.py
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── registry.py
│       │   ├── validator.py
│       │   └── internal_format.py
│       └── profiles/
│           ├── generic.yaml
│           ├── docker.yaml
│           ├── linux.yaml
│           ├── ansible.yaml
│           └── host-context.yaml
├── scaffolding/
│   ├── docker-services/
│   │   ├── manifest.yaml
│   │   ├── typical-assertions.yaml
│   │   ├── reference-patterns.yaml
│   │   ├── anti-patterns.yaml
│   │   ├── known-defaults.yaml
│   │   ├── interview.yaml
│   │   ├── test-cases/
│   │   └── examples/
│   ├── linux-host/
│   │   └── ...
│   └── ansible-automation/
│       └── ...
├── assertions/                         # shipped examples
│   ├── services/
│   │   └── docker.yaml
│   ├── networking/
│   │   └── vlans.yaml
│   ├── security/
│   │   └── pki.yaml
│   └── linux/
│       └── hardening.yaml
├── tests/
│   ├── test_passes/
│   ├── test_pipeline.py
│   ├── test_assertions.py
│   ├── test_adapters/
│   ├── test_classes.py
│   ├── test_normalise.py
│   ├── test_llm/
│   ├── test_schemas.py
│   ├── test_tokens.py
│   └── fixtures/
├── benchmarks/
│   ├── corpus/
│   ├── run_benchmarks.py
│   ├── llm_eval.py
│   ├── questions/
│   └── results/
├── docs/
│   ├── getting-started.md
│   ├── how-it-works.md
│   ├── scaffolding.md
│   ├── assertions.md
│   ├── schemas.md
│   ├── adapters.md
│   ├── classes.md
│   ├── passes.md
│   ├── contributing.md
│   └── security.md
└── CONTRIBUTING.md
```

---

### Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.10+ | Ecosystem, LLM SDK availability |
| YAML | ruamel.yaml | Round-trip preservation |
| Tokens | tiktoken | cl100k_base default, o200k_base option |
| CLI | click | Composable commands |
| LLM | Anthropic SDK primary, OpenAI secondary | Abstract behind client interface |
| Testing | pytest | Fixture-heavy strategy |
| Licence | MIT | Maximum adoption |

---

### README Structure

Must demonstrate value in 30 seconds.

**1. Hero example:**

```
Docker Compose for a production host:

  Raw input:               612 tokens
  + generic cleanup:       520 tokens  (15% saved)
  + platform defaults:     342 tokens  (44% saved)
  + design standards:      258 tokens  (58% saved)  ← decoct

  2 deviations found:
  - acme-app.restart = always (standard: unless-stopped)
  - acme-app.image uses :latest (standard: specific tag)
```

**2. One-liner:** Decoct your infrastructure for LLMs.

**3. Install + first run:** `pip install decoct && decoct compress your-file.yaml`

**4. Build assertions:** `decoct assertions init`

**5. Build schemas:** `decoct schema init`

**6. How it works:** Three phases, three compression tiers, class-based reconstitution.

**7. Benchmarks table.**

**8. Scaffolding packs and adapters available.**

Everything else in docs/.

---

### Positioning

**One-liner:** Decoct your infrastructure for LLMs.

**Elevator pitch:** decoct compresses infrastructure data for LLM context windows. It ingests diverse source formats — JSON, XML, YAML, CLI output, documentation — and produces optimised YAML by stripping platform defaults, removing noise, and highlighting deviations from your design standards. It uses authoritative vendor schemas where they exist and LLM intelligence where they don't. Typically saves 40-60% of tokens while making the output more informative, not less. Stripped values are recorded in class definitions so the LLM can reconstruct full state when needed.

**Target audience:** Engineers feeding infrastructure state into LLM context windows — building AI-assisted operations tooling, agent-driven infrastructure, or using LLMs for troubleshooting and architecture review.

**Key differentiators:**
- Diverse input, optimised YAML output
- Zero-setup value (LLM-direct works immediately)
- Secrets never reach the LLM (strip-secrets runs before any API contact)
- Best-available schema source (open adapter framework)
- Standards-aware (assertion stripping + deviation highlighting)
- Reconstitutable (class definitions preserve what was stripped)
- Domain scaffolding packs (expert knowledge per domain)

---

### Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Perceived as YAML minifier | High | Fatal | Three-tier savings headline; deviations and classes are the story |
| Secret leakage to LLM provider | Medium | Fatal | `strip-secrets` runs before any LLM contact; entropy + regex + path patterns; audit log |
| LLM-direct quality varies | Medium | High | Eval harness; cached schemas are steady state |
| Poor generated schemas | Medium | High | Human review; scaffolding; hand-authored seeds |
| Scaffolding requires domain expertise | High | Medium | Enable writes Phase 1 packs; community later |
| Input normalisation complexity | Medium | Medium | JSON/YAML deterministic; CLI output LLM-mediated; phase in formats |
| Class definitions add complexity | Medium | Medium | Optional output (--emit-class); omit when not needed |
| ruamel.yaml fragility | High | Medium | Fixture tests; non-round-trip fallback |
| Annotation cache staleness | Medium | Medium | --update re-evaluates; timestamps |
| Savings insufficient | Medium | Fatal | Hard gate: 40%+ or rethink |
| Comprehension degraded | Low | High | Eval harness; degrading passes disabled |

**Single biggest risk:** Perceived as a YAML minifier. The LLM-powered learning, assertion-driven compression, deviation annotations, class-based reconstitution, and scaffolding packs exist specifically to counter this.

---

### Timeline

| Phase | Scope | Duration | Gate |
|-------|-------|----------|------|
| Phase 1 | LLM core + strip-secrets + host stack + scaffolding + classes + benchmarks | 8 weeks | 40%+ savings, ≥95% accuracy |
| Phase 2 | YANG + OpenAPI + ADMX adapters + diff-aware mode + 4 scaffolding packs + XML normalisation + Python API | 6-8 weeks | Formal adapter beats LLM-learned |
| Phase 3 | Advanced passes + remaining adapters + integrations + class composition | 8 weeks | Claude Code integration working |
| Phase 4 | Multi-language ports + ecosystem | Ongoing | npm package published |

Phase 1 has a hard quality gate. If the host stack cannot demonstrate 40%+ token savings without degrading LLM accuracy, the approach needs rethinking before public release.

---

### Organisation

**Repository:** `github.com/example-corp/decoct`

Starting under Example Corp establishes credibility in infrastructure engineering. Transfer to a standalone organisation if community governance warrants it.

**Package:** `decoct` on PyPI.

**Licence:** MIT.
