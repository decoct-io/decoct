# Writing Custom Assertions for decoct

Assertions are decoct's mechanism for encoding design standards as structured,
machine-evaluable rules. When you run the compression pipeline with assertions,
decoct can strip values that conform to your standards (saving tokens) and
annotate values that deviate (highlighting what matters).

This guide covers the assertion file format, how to write effective assertions,
and how to test and maintain them.

---

## Assertion File Format

Assertion files are YAML documents with a top-level `assertions` key containing
a list of assertion objects:

```yaml
assertions:
  - id: unique-identifier
    assert: Human-readable description of the standard
    rationale: Why this standard exists
    severity: must  # must | should | may
    match:
      path: services.*.image
      pattern: "^(?!.*:latest$)"
    example: "nginx:1.25.3"
    exceptions: "Base images used in CI builds"
    related: [other-assertion-id]
    source: "Team standards doc v2"
```

### Required Fields

Every assertion must include these four fields:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier for the assertion. Used for cross-references, merge deduplication, and pipeline output. |
| `assert` | string | Human-readable statement of what the standard requires. In the data model this maps to the `assert_` field. |
| `rationale` | string | Explanation of why this standard exists and what problem it prevents. |
| `severity` | string | One of `must`, `should`, or `may`. Controls how the pipeline treats conformant and deviating values. |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `match` | object | Machine-evaluable condition (path + one condition type). Without this, the assertion is LLM-context only. |
| `example` | string | Example of a conformant value. Helps both humans and LLMs understand the intent. |
| `exceptions` | string | Describes cases where the assertion may be legitimately violated. |
| `related` | list of strings | IDs of related assertions for cross-referencing. |
| `source` | string | Origin reference (e.g., standards document name, policy ID, RFC number). |

---

## Writing Effective Assertions

### ID Naming

Use lowercase, hyphenated, descriptive identifiers. A good convention is to
prefix with a namespace representing the team or standards document:

- `require-healthcheck` -- clear about what is required
- `no-privileged` -- clear about what is prohibited
- `ops-image-pinned` -- namespaced to a specific standards document
- `k8s-resource-limits` -- namespaced to a platform

Avoid generic IDs like `rule-1` or `check-a`. The ID appears in pipeline
output, deviation reports, and merge operations, so it should be self-documenting.

### Writing the `assert` Text

State what **should** be true, not what should not be true. The assertion text
is included in LLM context and deviation annotations, so it should read as a
positive requirement:

| Good | Bad |
|------|-----|
| "Image tags must be pinned to specific versions" | "Don't use :latest" |
| "Containers must have health checks configured" | "Missing healthcheck is bad" |
| "Restart policy must be unless-stopped or always" | "Restart should not be no" |

### Writing the `rationale`

Explain **why** the standard exists, not just what it checks. The rationale
gives LLMs the context needed to make judgment calls:

| Good | Bad |
|------|-----|
| "Pinned versions ensure reproducible deployments and auditable rollbacks" | "Because latest is bad" |
| "Unbounded logs cause disk exhaustion" | "Logs should be rotated" |
| "Privileged mode gives full host access, violating container isolation" | "Privileged is a security risk" |

### Choosing Severity

Choose severity based on how the pipeline should treat the assertion:

- **`must`** -- Hard requirements. The `strip-conformant` pass removes conformant
  values (they match the standard, so they carry no information). The
  `annotate-deviations` pass marks violations with `[!]` comments.
- **`should`** -- Advisory standards. Not stripped, but deviations are annotated
  by `annotate-deviations`. Use for best practices where exceptions are common.
- **`may`** -- Informational. Included in output as LLM context only. Neither
  stripped nor annotated. Use for aspirational standards or recommendations.

---

## Match Conditions Deep Dive

Each `match` object requires a `path` and exactly one condition. The condition
determines how the matcher evaluates the value found at the path. Only one
condition should be set per match (if multiple are set, the first one found in
evaluation order takes precedence).

### `value` -- Exact Match

Performs case-insensitive string comparison for string values, or direct
equality for other types.

```yaml
# Logging driver must be json-file
- id: require-json-logging
  assert: Logging driver must be json-file
  rationale: Consistent json-file logging enables centralised log collection
  severity: must
  match:
    path: services.*.logging.driver
    value: json-file

# Network mode must be bridge
- id: require-bridge-network
  assert: Container network mode must be bridge
  rationale: Bridge networking provides proper isolation between containers
  severity: must
  match:
    path: services.*.network_mode
    value: bridge

# TLS version must be 1.3
- id: require-tls-13
  assert: TLS minimum version must be 1.3
  rationale: TLS versions below 1.3 have known vulnerabilities
  severity: must
  match:
    path: servers.*.tls.min_version
    value: "1.3"
```

### `pattern` -- Regex Match

The value is converted to a string and tested against the regex using
`re.search` (not `re.match`), so patterns match anywhere in the value unless
anchored with `^` and `$`.

```yaml
# Image tags must be pinned (not :latest)
- id: image-pinned
  assert: Image tags must be pinned to specific versions, not :latest
  rationale: Pinned versions ensure reproducible deployments and auditable rollbacks
  severity: must
  match:
    path: services.*.image
    pattern: "^(?!.*:latest$)(?=.*:.+$)"
  example: "nginx:1.25.3"

# Restart policy must be one of allowed values
- id: restart-policy
  assert: Restart policy must be unless-stopped or always
  rationale: Services must automatically recover from crashes
  severity: must
  match:
    path: services.*.restart
    pattern: "^(unless-stopped|always)$"

# Log rotation max-size must be configured (any non-empty value)
- id: log-max-size
  assert: Log rotation max-size must be configured
  rationale: Unbounded logs cause disk exhaustion
  severity: must
  match:
    path: services.*.logging.options.max-size
    pattern: ".+"
  example: "10m"
```

### `range` -- Numeric Range (Inclusive)

Tests whether the value, converted to a float, falls within `[min, max]`
inclusive. Non-numeric values fail the match. The range must be a two-element
list.

```yaml
# Port must be in valid range
- id: valid-port-range
  assert: Exposed ports must be in the valid range
  rationale: Ports outside 1-65535 are invalid and will cause runtime errors
  severity: must
  match:
    path: services.*.ports[*].published
    range: [1, 65535]

# Replica count should be reasonable
- id: reasonable-replicas
  assert: Replica count should be between 1 and 10
  rationale: Excessive replicas waste resources; zero replicas means the service is down
  severity: should
  match:
    path: services.*.deploy.replicas
    range: [1, 10]

# Memory limit should be within bounds
- id: memory-limit-range
  assert: Memory limits should be between 64 and 8192 MB
  rationale: Too-small limits cause OOM kills; too-large limits defeat resource governance
  severity: should
  match:
    path: deploy.resources.limits.memory_mb
    range: [64, 8192]
```

### `contains` -- List Membership

Tests whether a list value contains the specified item. Returns false if the
value is not a list.

```yaml
# Security options must include no-new-privileges
- id: no-new-privileges
  assert: Containers should set no-new-privileges security option
  rationale: Prevents privilege escalation via setuid/setgid binaries
  severity: should
  match:
    path: services.*.security_opt
    contains: "no-new-privileges:true"
  example: "no-new-privileges:true"

# Required capability must be present
- id: require-net-bind
  assert: Web-facing containers must have NET_BIND_SERVICE capability
  rationale: Required to bind to ports below 1024 without running as root
  severity: must
  match:
    path: services.*.cap_add
    contains: NET_BIND_SERVICE

# DNS servers must include internal resolver
- id: require-internal-dns
  assert: DNS configuration must include the internal resolver
  rationale: Internal service discovery requires the corporate DNS resolver
  severity: must
  match:
    path: services.*.dns
    contains: "10.0.0.2"
```

### `not_value` -- Negated Exact Match

Tests that the value does **not** equal the specified value. Uses direct
equality comparison (not case-insensitive).

```yaml
# Containers must not run in privileged mode
- id: no-privileged
  assert: Containers must not run in privileged mode
  rationale: Privileged mode gives full host access, violating container isolation
  severity: must
  match:
    path: services.*.privileged
    not_value: true

# Network mode must not be host
- id: no-host-network
  assert: Containers must not use host network mode
  rationale: Host networking bypasses container network isolation
  severity: must
  match:
    path: services.*.network_mode
    not_value: host

# PID mode must not be host
- id: no-host-pid
  assert: Containers must not share the host PID namespace
  rationale: Sharing the host PID namespace allows containers to see and signal host processes
  severity: must
  match:
    path: services.*.pid
    not_value: host
```

### `exists` -- Presence/Absence Check

Tests whether a key exists (`true`) or does not exist (`false`) at the given
path. For `exists` checks, the matcher splits the path into a parent pattern
and a leaf key -- it walks to all matching parents and then checks whether the
leaf key is present.

Note: The `strip-conformant` pass skips `exists` assertions (there is no value
to strip for a presence check). The `annotate-deviations` pass will report
missing keys as deviations.

```yaml
# Containers must have health checks
- id: require-healthcheck
  assert: All application containers must have health checks configured
  rationale: Health checks enable proper orchestration, dependency ordering, and monitoring
  severity: must
  match:
    path: services.*.healthcheck
    exists: true
  exceptions: Infrastructure-only containers may rely on built-in health mechanisms

# Container name must be explicit
- id: require-container-name
  assert: Container name must be explicitly set
  rationale: Explicit naming prevents Docker-generated names and aids log correlation
  severity: must
  match:
    path: services.*.container_name
    exists: true

# Environment file must not be used in production
- id: no-env-file
  assert: Production services must not use env_file
  rationale: env_file makes secrets management opaque; use explicit environment variables or secrets
  severity: should
  match:
    path: services.*.env_file
    exists: false
```

---

## Path Patterns

Paths use dot-separated segments to navigate the document tree. Two wildcard
types are supported (implemented via `fnmatch` per segment):

| Pattern | Meaning | Example |
|---------|---------|---------|
| Literal | Exact key name | `services.web.image` matches only `services.web.image` |
| `*` | Any single segment | `services.*.image` matches `services.web.image`, `services.api.image`, etc. |
| `**` | Any number of segments (including zero) | `**.image` matches `services.web.image`, `a.b.c.image`, etc. |

### Examples

```yaml
# Single service, specific key
path: services.web.image

# All services, specific key
path: services.*.restart

# Nested key under all services
path: services.*.logging.driver

# Deeply nested -- any depth
path: "**.containers.*.image"

# Multi-level wildcard
path: services.*.logging.options.max-size
```

Path matching works for both dictionary keys and list items. List items are
addressed with `[index]` notation internally, but wildcard patterns match
across dictionary keys -- list items are traversed automatically during the
tree walk.

---

## Assertions Without `match`

Omitting the `match` field makes an assertion LLM-context only. It will not be
machine-evaluated -- no values are stripped and no deviations are annotated.
These assertions are included in the output as context for LLM consumers of
the compressed data.

This is useful for standards that require human or LLM judgment and cannot be
reduced to a simple path + condition check:

```yaml
assertions:
  - id: resource-limits
    assert: Production and multi-container stacks should define resource limits
    rationale: Resource limits prevent runaway containers from exhausting host resources
    severity: should
    exceptions: Single-container development stacks may omit limits

  - id: named-networks
    assert: Services should use named networks, not the default bridge
    rationale: Named networks provide DNS resolution and isolation between stacks
    severity: should

  - id: no-host-0000
    assert: Ports must not bind to 0.0.0.0; use specific IPs or 127.0.0.1
    rationale: Binding to all interfaces exposes services beyond intended network boundaries
    severity: should
    exceptions: Containers behind reverse proxy should bind to 127.0.0.1
```

These assertions still carry value -- they communicate team standards to any
LLM processing the compressed output.

---

## Severity Levels

How each severity level interacts with the compression pipeline:

| Level | `strip-conformant` Pass | `annotate-deviations` Pass | Use When |
|-------|------------------------|---------------------------|----------|
| `must` | Removes conformant values (they match the standard, so they add no information) | Annotates violations with `[!]` inline comments | Hard requirements that every config must meet |
| `should` | No effect (values are kept) | Annotates violations with `[!]` inline comments | Best practices where exceptions are expected |
| `may` | No effect | No effect | Informational standards for LLM context |

### Annotation Format

When `annotate-deviations` finds a violation, it adds an end-of-line YAML
comment to the deviating value. The comment format depends on the condition type:

- For `value` mismatches: `# [!] standard: <expected_value>`
- For missing keys (`exists: true`): reported as deviation `[!] missing: <assert text>` (no inline comment since the key is absent)
- For all other conditions: `# [!] assertion: <assert text>`

---

## Using `decoct assertion learn`

The `assertion learn` command uses Claude to derive assertions from your
existing standards documents and configuration files. It requires the LLM
extras: `pip install decoct[llm]`.

### Three Modes

1. **Standards + examples** -- provide a standards document and example configs.
   Claude reads both and produces assertions that capture the standards in
   machine-evaluable form:

   ```bash
   decoct assertion learn -s deployment-standards.md -e docker-compose.yml -o assertions.yaml
   ```

2. **Corpus analysis** -- provide multiple configuration files. Claude analyses
   cross-file patterns to discover implicit standards (values that are
   consistent across all files):

   ```bash
   decoct assertion learn -c prod/*.yaml -p docker-compose -o learned.yaml
   ```

   The `--corpus` (`-c`) and `--example` (`-e`) options are mutually exclusive.
   The optional `--platform` (`-p`) flag gives Claude a hint about the
   configuration format.

3. **Combined** -- provide standards documents together with corpus files.
   Claude uses the standards as guidance while analysing the corpus for
   patterns:

   ```bash
   decoct assertion learn -s standards.md -c config1.yaml -c config2.yaml -o assertions.yaml
   ```

### Model Selection

By default, `assertion learn` uses `claude-sonnet-4-20250514`. You can specify a
different Anthropic model with `--model`:

```bash
decoct assertion learn -s standards.md -e config.yaml --model claude-opus-4-20250514 -o assertions.yaml
```

---

## Testing Assertions

Before deploying assertions in your pipeline, test them against real
configuration files to verify they match what you expect.

### Preview Compression with Assertions

```bash
decoct compress config.yaml --assertions my-assertions.yaml
```

This runs the full pipeline with your assertions and prints the compressed
output. Values conforming to `must` assertions are stripped; deviations are
annotated with `[!]` comments.

### See What Was Removed

```bash
decoct compress config.yaml --assertions my-assertions.yaml --show-removed
```

The `--show-removed` flag prints a per-pass breakdown to stderr showing how
many items each pass removed and which specific deviations were detected:

```
--- strip-conformant ---
  Removed: 5 items
--- annotate-deviations ---
  ops-image-pinned: services.web.image
  ops-healthcheck: services.web.healthcheck
```

### Token Statistics

```bash
decoct compress config.yaml --assertions my-assertions.yaml --stats
```

The `--stats` flag appends token count information showing input tokens,
output tokens, and the savings percentage. Use `--stats-only` to see only the
statistics without the compressed output.

---

## Merging and Maintaining

As standards evolve, you can regenerate assertions and merge them into your
existing file:

```bash
decoct assertion learn -s updated-standards.md -m existing-assertions.yaml -o existing-assertions.yaml
```

The `--merge` (`-m`) flag loads the existing assertions file, merges in the
newly generated assertions, and deduplicates by ID. Updated assertions (same
ID, different content) are replaced with the new version.

### Workflow Tips

- Keep assertions in version control alongside the configurations they govern.
- Use the `source` field to link assertions back to the standards document or
  policy that defines them.
- Use the `related` field to group assertions that work together (e.g., all
  logging-related assertions).
- Split large assertion sets into multiple files and load them via a profile,
  or merge them into a single file for simplicity.
- Re-run `assertion learn` periodically as standards documents are updated,
  using `--merge` to integrate changes without losing manual edits.
