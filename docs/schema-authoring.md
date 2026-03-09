# Schema Authoring Guide

Schemas tell decoct what a platform's default values are, which fields are noise,
and which fields are system-managed. When you compress a config file with a matching
schema, decoct strips those defaults and noise fields so only the intentional,
non-default parts of your configuration remain in the LLM context window.

This guide covers writing custom schemas from scratch, using LLM-assisted schema
generation, and contributing schemas upstream.

---

## Schema File Format

A schema is a YAML file with the following structure:

```yaml
platform: my-platform
source: vendor documentation v2.1
confidence: authoritative
defaults:
  settings.timeout: 30
  settings.retries: 3
  services.*.enabled: true
drop_patterns:
  - "**.uuid"
  - "**.generated_id"
system_managed:
  - "**.creationTimestamp"
  - "**.lastModified"
```

The schema is loaded by `decoct.schemas.loader.load_schema()` and validated into a
`Schema` dataclass defined in `decoct.schemas.models`.

### Required Fields

- **`platform`** (str) -- Platform identifier. Used for display, auto-detection, and
  as the bundled schema short name (e.g. `docker-compose`, `kubernetes`).
- **`source`** (str) -- Where the defaults came from. Cite the specification version,
  documentation URL, or source code reference so others can verify the values.
- **`confidence`** -- One of: `authoritative`, `high`, `medium`, `low`. Controls
  whether defaults are stripped or skipped. See [Confidence Levels](#confidence-levels)
  below.

### Optional Fields

- **`defaults`** (mapping) -- Map of dotted path patterns to their default values.
  When a field in the input document matches both the path pattern and the default
  value, it is stripped from the output. Values are compared with type coercion
  (e.g. string `"true"` matches boolean `true`).
- **`drop_patterns`** (list of strings) -- Glob patterns for fields that should be
  unconditionally removed regardless of their value. Use for noise fields like UUIDs,
  hashes, and generated identifiers.
- **`system_managed`** (list of strings) -- Glob patterns for fields that are
  generated and managed by the platform, not user-configured. Semantically distinct
  from defaults: these fields are injected by the system at runtime.

---

## Path Pattern Syntax

Path patterns use dot-separated segments with glob-style wildcards. The matching
engine is implemented in `decoct.passes.drop_fields._path_matches()`.

| Pattern | Matches |
|---------|---------|
| `services.web.image` | Exact path `services.web.image` |
| `services.*.restart` | `services.web.restart`, `services.api.restart`, etc. |
| `**.managedFields` | `managedFields` at any depth: `metadata.managedFields`, `a.b.c.managedFields` |
| `metadata.**.name` | `metadata.name`, `metadata.labels.name`, `metadata.annotations.app.name` |
| `**.containers.*.ports.*.protocol` | `protocol` under any container port at any nesting depth |

Rules:

- **Dot-separated segments**: `services.web.image` matches the literal path
  `services` -> `web` -> `image`.
- **`*` (single wildcard)**: Matches exactly one path segment. `services.*.restart`
  matches `services.<anything>.restart` but not `services.web.config.restart`.
- **`**` (double wildcard)**: Matches zero or more segments. Can appear at the start,
  middle, or end of a pattern. `**.name` matches `name` at any depth.
  `metadata.**.name` matches `metadata.name` and `metadata.labels.name`.
- List indices are path segments: `services.*.ports.*.protocol` matches through
  list items where `*` covers the numeric index.

---

## Finding Defaults for Your Platform

Before writing a schema, you need to identify the platform's actual default values.
Here are strategies in order of reliability:

1. **Vendor documentation / specifications** -- Official docs are the most
   authoritative source. Look for "default value" tables in configuration references.
   Example: Docker Compose specification, Kubernetes API reference.

2. **CLI dumps** -- Many tools expose their defaults through help output or verbose
   config dumps:
   ```bash
   my-tool config dump --defaults
   my-tool --help
   my-tool config show --verbose
   ```

3. **JSON Schema / OpenAPI definitions** -- If the platform publishes a JSON Schema
   or OpenAPI spec, default values are often declared in `default` fields within the
   schema definition.

4. **`decoct schema learn`** -- Use LLM-assisted extraction to analyze example
   configs and documentation. See [Using `decoct schema learn`](#using-decoct-schema-learn)
   below.

---

## Using `decoct schema learn`

The `schema learn` subcommand uses Claude to extract defaults from example
configuration files and/or documentation.

```bash
# From example config files
decoct schema learn -e config1.yaml -e config2.yaml -p my-platform -o schema.yaml

# From vendor documentation
decoct schema learn -d vendor-docs.md -p my-platform -o schema.yaml

# From both examples and docs
decoct schema learn -e config.yaml -d docs.md -o schema.yaml
```

**Requirements:**
- Install the LLM extra: `pip install decoct[llm]`
- Set the `ANTHROPIC_API_KEY` environment variable.
- At least one `--example` (`-e`) or `--doc` (`-d`) file is required.

**Options:**

| Flag | Description |
|------|-------------|
| `-e`, `--example` | Example config file (repeatable) |
| `-d`, `--doc` | Documentation file (repeatable) |
| `-p`, `--platform` | Platform name hint (e.g. `nginx`, `haproxy`) |
| `-o`, `--output` | Output file path (prints to stdout if omitted) |
| `-m`, `--merge` | Merge into an existing schema file |
| `--model` | Anthropic model to use (default: `claude-sonnet-4-20250514`) |

The generated schema will have `confidence: medium` or `confidence: high` depending
on the quality of the input. Always review the output and verify defaults against
official documentation before using in production.

---

## Confidence Levels

The `confidence` field controls how aggressively decoct strips defaults. When the
`skip_low_confidence` option is enabled on the `strip-defaults` pass, schemas with
lower confidence are skipped entirely.

| Level | Meaning | Behaviour |
|-------|---------|-----------|
| `authoritative` | From official specification or schema | Stripped without question |
| `high` | Verified against vendor documentation | Stripped by default |
| `medium` | Derived from examples or inferred with high agreement | Stripped by default |
| `low` | Inferred or uncertain | Skipped when `skip_low_confidence: true` |

When `skip_low_confidence` is `true`, schemas with confidence `low` or `medium` are
skipped -- no defaults, drop_patterns, or system_managed fields are applied from
that schema. This is a conservative mode for pipelines where accuracy is critical.

Set confidence honestly. An `authoritative` schema with a wrong default is worse
than a `medium` schema that can be reviewed.

---

## drop_patterns

Use `drop_patterns` to unconditionally remove matching paths regardless of their
value. This is for noise fields that add no useful information to an LLM context
window.

```yaml
drop_patterns:
  - "**.uuid"
  - "**.generated_id"
  - "**.checksum"
  - "**.etag"
```

- Patterns use the same [path pattern syntax](#path-pattern-syntax) as defaults.
- The field is removed entirely (key and value), not replaced with a sentinel.
- Unlike `defaults`, no value comparison is performed -- any value at a matching
  path is dropped.
- Applied after default stripping in the `strip-defaults` pass.

---

## system_managed

Use `system_managed` for fields that are generated and managed by the platform at
runtime. These are semantically distinct from defaults: they are not values a user
would ever set, but values the platform injects.

```yaml
system_managed:
  - metadata.uid
  - metadata.resourceVersion
  - metadata.generation
  - metadata.creationTimestamp
  - metadata.managedFields
  - status
```

Common examples:

- Kubernetes: `metadata.uid`, `metadata.resourceVersion`, `metadata.creationTimestamp`,
  `metadata.managedFields`, `status`
- Cloud resources: creation timestamps, ARNs, internal IDs
- Databases: `_id`, `_rev`, internal sequence numbers

Like `drop_patterns`, these are removed unconditionally (no value comparison).
They are applied after both default stripping and drop_patterns in the
`strip-defaults` pass.

---

## Testing Your Schema

Always verify a schema before relying on it in production.

```bash
# See what gets stripped and how many items each pass removes
decoct compress config.yaml --schema my-schema.yaml --show-removed

# Check token savings
decoct compress config.yaml --schema my-schema.yaml --stats

# See only the statistics without output
decoct compress config.yaml --schema my-schema.yaml --stats-only

# Compare compressed output to original
decoct compress config.yaml --schema my-schema.yaml -o compressed.yaml
diff config.yaml compressed.yaml

# Compress multiple files at once
decoct compress configs/ --schema my-schema.yaml --stats -r
```

Things to check:

- **No important fields removed**: Review `--show-removed` output to confirm only
  actual defaults and noise were stripped.
- **Token savings in expected range**: Platform-aware schemas typically achieve
  30-50% token savings. If savings are very low, you may be missing defaults. If
  savings are very high, double-check that meaningful values are not being stripped.
- **Value accuracy**: If a default value in your schema is wrong, user-configured
  values matching that wrong default will be silently removed.

---

## Merging Defaults

When you discover additional defaults (from new documentation, new platform
versions, or additional example files), merge them into an existing schema:

```bash
decoct schema learn -e new-examples.yaml -m existing-schema.yaml
```

The `--merge` (`-m`) flag loads the existing schema, generates new defaults from the
provided inputs, and merges them together. Existing entries are preserved; only new
path/value pairs are added. The merged result is written to stdout (or to `-o` if
specified).

This is useful for iteratively building up a schema as you encounter more
configuration patterns.

---

## Example: Docker Compose Schema

The bundled `docker-compose` schema demonstrates the format for a real platform.
Selected entries:

```yaml
platform: docker-compose
source: Docker Compose specification + compose-go source
confidence: authoritative
defaults:
  # Service-level booleans
  services.*.restart: "no"
  services.*.privileged: false
  services.*.read_only: false
  services.*.stdin_open: false
  services.*.tty: false
  services.*.init: false

  # Healthcheck
  services.*.healthcheck.interval: 30s
  services.*.healthcheck.timeout: 30s
  services.*.healthcheck.retries: 3

  # Deploy
  services.*.deploy.replicas: 1
  services.*.deploy.restart_policy.condition: any
  services.*.deploy.update_config.parallelism: 1
  services.*.deploy.update_config.order: stop-first

  # Network declarations
  networks.*.driver: bridge
  networks.*.external: false
drop_patterns: []
system_managed: []
```

Key observations:

- The `*` wildcard is used for service names (`services.*.restart`) so the same
  default applies to every service in the file.
- Values are YAML-native types: `false` (boolean), `3` (integer), `"no"` (string,
  quoted because bare `no` is YAML boolean false).
- `drop_patterns` and `system_managed` are empty lists -- Docker Compose configs
  rarely contain system-generated noise.

---

## Example: Kubernetes Schema

The bundled `kubernetes` schema shows heavy use of `**` patterns and `system_managed`:

```yaml
platform: kubernetes
source: Kubernetes API Reference (v1.29+)
confidence: authoritative
defaults:
  "**.restartPolicy": Always
  "**.dnsPolicy": ClusterFirst
  "**.terminationGracePeriodSeconds": 30
  "**.containers.*.imagePullPolicy": IfNotPresent
  "**.containers.*.ports.*.protocol": TCP
  spec.replicas: 1
  spec.revisionHistoryLimit: 10
  spec.strategy.type: RollingUpdate
  spec.strategy.rollingUpdate.maxSurge: 25%
  spec.strategy.rollingUpdate.maxUnavailable: 25%
system_managed:
  - metadata.uid
  - metadata.resourceVersion
  - metadata.generation
  - metadata.creationTimestamp
  - metadata.managedFields
  - status
```

Key observations:

- `**` patterns like `"**.restartPolicy"` match through any nesting depth. This
  handles both Pod specs and Deployment `spec.template.spec` paths with a single
  entry.
- Patterns with `**` that contain dots must be quoted in YAML to avoid parsing
  issues.
- The `system_managed` list removes Kubernetes API server metadata that appears in
  `kubectl get -o yaml` output but is never part of the desired state.

---

## Contributing Schemas Upstream

To add a schema to the bundled set shipped with decoct:

### Requirements

1. **Confidence**: Must be `authoritative` or `high` (with a documented source).
2. **Source**: Cite the exact specification, documentation version, or source code
   reference (e.g. `Docker Compose specification + compose-go source`,
   `Kubernetes API Reference (v1.29+)`).
3. **Defaults**: Every default value must be verified against actual platform
   behaviour. Do not guess.
4. **Schema file**: Place the YAML file in `src/decoct/schemas/bundled/` with a
   descriptive filename (e.g. `my-platform.yaml`).
5. **Resolver entry**: Add the short name to `BUNDLED_SCHEMAS` in
   `src/decoct/schemas/resolver.py`:
   ```python
   BUNDLED_SCHEMAS: dict[str, str] = {
       # ... existing entries ...
       "my-platform": "my-platform.yaml",
   }
   ```
6. **Test fixture**: Add a test fixture in `tests/fixtures/` that exercises the
   schema against representative input and verifies the expected output.

### Naming conventions

- Use the community-recognized short name for the platform (e.g. `docker-compose`
  not `docker_compose`, `kubernetes` not `k8s`).
- Use hyphens, not underscores, in schema filenames and short names.

### Checklist

- [ ] Schema file in `src/decoct/schemas/bundled/<name>.yaml`
- [ ] Short name added to `BUNDLED_SCHEMAS` in `resolver.py`
- [ ] Source field cites a verifiable reference
- [ ] Confidence is `authoritative` or `high`
- [ ] All default values verified against platform documentation or source code
- [ ] Test fixture added in `tests/fixtures/`
- [ ] `pytest --cov=decoct -v` passes
