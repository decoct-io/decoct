# Profile Authoring Guide

## What is a Profile?

A profile bundles a schema reference, assertion references, and pass configuration into a single file for repeatable compression. Instead of passing `--schema`, `--assertions`, and individual pass options on the command line every time, you define them once in a profile and reference it with `--profile`.

Profiles are plain YAML files. They can be committed to your repository, shared across a team, or published as part of a configuration package.

## Profile File Format

```yaml
name: my-profile
schema: path/to/schema.yaml
assertions:
  - path/to/assertions-1.yaml
  - path/to/assertions-2.yaml
passes:
  strip-secrets:
  strip-comments:
  strip-defaults:
    skip_low_confidence: true
  emit-classes:
  strip-conformant:
  annotate-deviations:
  deviation-summary:
  drop-fields:
    patterns:
      - "**.uuid"
  prune-empty:
```

### Fields

- **name** (str, optional) -- human-readable profile name for display purposes.
- **schema** (str, optional) -- relative path to a schema file. The path is resolved relative to the profile file's directory.
- **assertions** (list, optional) -- relative paths to assertion files. Each path is resolved relative to the profile file's directory.
- **passes** (dict) -- mapping of pass name to configuration. Use `null` or leave the value empty for default pass settings. When a pass accepts options, provide them as a nested mapping.

### Path Resolution

All paths in a profile (schema and assertion references) are resolved relative to the directory containing the profile file itself, not relative to the current working directory. This makes profiles portable -- you can move a profile along with its schema and assertion files as a unit, and all references continue to work.

For example, given this directory layout:

```
my-project/
  profiles/
    production.yaml       # profile file
  schemas/
    docker-compose.yaml
  assertions/
    deployment.yaml
```

The profile `profiles/production.yaml` would reference:

```yaml
schema: ../schemas/docker-compose.yaml
assertions:
  - ../assertions/deployment.yaml
```

## Bundled Profiles

decoct ships with bundled profiles for common platforms. Currently one bundled profile is available: `docker-compose`.

Use a bundled profile by passing its short name (no path separators, no file extension):

```bash
decoct compress config.yaml --profile docker-compose
```

The bundled `docker-compose` profile includes:

```yaml
name: docker-compose
schema: ../../schemas/bundled/docker-compose.yaml
assertions:
  - ../../assertions/bundled/deployment-standards.yaml
passes:
  strip-secrets:
  strip-comments:
  strip-defaults:
  strip-conformant:
  prune-empty:
  annotate-deviations:
  deviation-summary:
```

If the name you pass to `--profile` does not match a bundled profile short name, decoct treats it as a file path and loads the profile from disk.

## Pass Configuration Options

Each pass can be included in a profile with optional configuration. Passes with no configuration options accept `null` or an empty value.

| Pass | Config Options |
|------|---------------|
| `strip-secrets` | `secret_paths` (list of path patterns), `entropy_threshold` (float, default 4.5), `min_entropy_length` (int, default 16) |
| `strip-comments` | (none) |
| `strip-defaults` | `skip_low_confidence` (bool, default false) |
| `drop-fields` | `patterns` (list of path glob patterns to remove) |
| `keep-fields` | `patterns` (list of path glob patterns to retain) |
| `emit-classes` | (none) |
| `strip-conformant` | (none) |
| `annotate-deviations` | (none) |
| `deviation-summary` | (none) |
| `prune-empty` | (none) |

### Pass option details

**strip-secrets:**
- `secret_paths` -- additional path patterns that always indicate secrets (e.g., `"*.api_token"`). Merged with built-in patterns like `*.password`, `*.secret`, `*.credentials`.
- `entropy_threshold` -- Shannon entropy threshold for high-entropy string detection. Higher values reduce false positives but may miss some secrets.
- `min_entropy_length` -- minimum string length before entropy-based detection kicks in.

**strip-defaults:**
- `skip_low_confidence` -- when true, skips stripping defaults if the schema's confidence level is `low` or `medium`. Useful when working with LLM-generated schemas that may not be fully accurate.

**drop-fields / keep-fields:**
- `patterns` -- list of path glob patterns. Supports `*` (matches a single path segment) and `**` (matches any number of segments including zero). Examples: `"**.uuid"`, `"services.*.labels"`, `"metadata.**"`.

## Choosing Passes

Select passes based on what data you have (schema, assertions) and what output you need:

- **strip-secrets** -- always include. This is the security boundary of the pipeline. It redacts passwords, API keys, tokens, and high-entropy strings before any other processing.
- **strip-comments** -- include unless you specifically need to preserve YAML comments in the output.
- **strip-defaults** -- include when you have a schema. Removes values that match platform defaults, which typically accounts for the largest token savings.
- **emit-classes** -- include alongside strip-defaults. Adds a comment header listing what defaults were stripped, allowing LLMs to reconstruct full configurations from the compressed output.
- **strip-conformant** -- include when you have assertions. Removes values that conform to `must`-severity assertions, since conformant values carry no information.
- **annotate-deviations** -- include when you want inline `[!]` comments marking values that deviate from assertions.
- **deviation-summary** -- include for a quick overview comment block at the top of the document listing all deviations.
- **drop-fields** -- include when you want to remove specific noise fields by path pattern (e.g., UUIDs, timestamps, internal metadata).
- **keep-fields** -- include when you want to focus on specific paths and drop everything else.
- **prune-empty** -- include to clean up empty mappings and sequences left behind after other passes strip values.

## Pass Ordering

You do not need to worry about ordering passes in your profile. The pipeline automatically sorts passes using topological ordering based on `run_after` and `run_before` constraints declared by each pass.

The key ordering constraints are:

- `strip-secrets` always runs first (no `run_after` dependencies).
- `strip-defaults` runs after `strip-secrets` and `strip-comments`.
- `strip-conformant` runs after `strip-defaults`.
- `emit-classes` runs after `strip-defaults` and `prune-empty`, and before `annotate-deviations` and `deviation-summary`.
- `annotate-deviations` runs after `strip-conformant`.
- `deviation-summary` runs after `annotate-deviations`.
- `prune-empty` runs after `strip-defaults`, `strip-conformant`, `drop-fields`, and `keep-fields`.

This means you can list passes in any order in the profile YAML and the pipeline will execute them correctly.

## Example Profiles

### Minimal (generic cleanup only)

No schema or assertions needed. Strips secrets, removes comments, and cleans up empty containers.

```yaml
name: minimal
passes:
  strip-secrets:
  strip-comments:
  prune-empty:
```

### Schema-aware

Uses a schema to strip platform defaults. The `emit-classes` pass adds reconstruction metadata for LLMs.

```yaml
name: kubernetes-defaults
schema: schemas/kubernetes.yaml
passes:
  strip-secrets:
  strip-comments:
  strip-defaults:
  emit-classes:
  prune-empty:
```

### Full compliance check

Combines schema-aware default stripping with assertion-based conformance checking and deviation reporting.

```yaml
name: docker-full
schema: schemas/docker-compose.yaml
assertions:
  - assertions/deployment-standards.yaml
passes:
  strip-secrets:
  strip-comments:
  strip-defaults:
  emit-classes:
  strip-conformant:
  annotate-deviations:
  deviation-summary:
  prune-empty:
```

### Focused extraction

Uses `keep-fields` to extract only networking configuration, dropping everything else.

```yaml
name: networking-only
schema: schemas/docker-compose.yaml
passes:
  strip-secrets:
  keep-fields:
    patterns:
      - "services.*.ports"
      - "services.*.networks"
      - "networks.**"
  prune-empty:
```

### Noise reduction with drop-fields

Removes common noise fields like UUIDs, timestamps, and status metadata.

```yaml
name: clean-output
passes:
  strip-secrets:
  strip-comments:
  drop-fields:
    patterns:
      - "**.uuid"
      - "**.created_at"
      - "**.updated_at"
      - "**.status"
      - "metadata.managedFields"
  prune-empty:
```

### Conservative schema stripping

Uses `skip_low_confidence` to only strip defaults when the schema has high confidence.

```yaml
name: conservative
schema: schemas/learned-schema.yaml
passes:
  strip-secrets:
  strip-comments:
  strip-defaults:
    skip_low_confidence: true
  emit-classes:
  prune-empty:
```

## Sharing Profiles

Profiles are plain YAML files that can be:

- **Committed to your repository** -- place profiles alongside your infrastructure configs for team-wide consistency.
- **Shared in a team config directory** -- maintain a central directory of profiles for different platforms and use cases.
- **Published as a package** -- distribute profiles alongside custom schemas and assertions.

When sharing profiles, keep schema and assertion paths relative to the profile file. This ensures the profile works regardless of where it is checked out on disk. If your schemas and assertions live in a different repository, consider using a monorepo layout or a shared directory structure.
