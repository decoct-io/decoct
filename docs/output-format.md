# Understanding decoct Output

decoct compresses infrastructure configuration for LLM context windows. This guide
explains every element that can appear in decoct's output, how to read it, and how
to work with compressed documents.

## Compressed YAML

decoct always emits valid YAML. The output preserves the original document's structure
and key ordering -- it is a strict subset of the input, not a reorganisation.

Values removed by compression passes are simply absent from the output. There is no
placeholder or tombstone; the key-value pair is gone entirely. If removing a value
leaves an empty mapping or sequence, the `prune-empty` pass removes that container
too, recursing upward until no empty containers remain.

For example, given this input:

```yaml
services:
  web:
    image: nginx:1.25.3
    restart: "no"
    privileged: false
    stdin_open: false
    tty: false
    ports:
      - "8080:80"
  db:
    image: postgres:16
    restart: always
    privileged: false
    stdin_open: false
    tty: false
```

After stripping docker-compose defaults (`restart: "no"`, `privileged: false`,
`stdin_open: false`, `tty: false`), the compressed output retains only the
non-default values:

```yaml
services:
  web:
    image: nginx:1.25.3
    ports:
      - "8080:80"
  db:
    image: postgres:16
    restart: always
```

## Class Definitions

The `emit-classes` pass adds a header comment block that lists every default value
that was stripped, grouped into named classes by path prefix. This block allows an
LLM reading the compressed output to reconstruct the full configuration.

### Format

The header begins with a provenance line, followed by one `@class` line per group:

```
# decoct: defaults stripped using <platform> schema
# @class <name>: <field>=<value>, <field>=<value>, ...
```

### Class naming

Classes are derived from the path structure of the stripped defaults:

| Path pattern                       | Class name                       |
|------------------------------------|----------------------------------|
| `services.*.restart`               | `service-defaults`               |
| `services.*.healthcheck.interval`  | `service-healthcheck-defaults`   |
| Single top-level keys              | `top-level-defaults`             |

The first meaningful path segment (after stripping wildcards) forms the category.
If there are three or more meaningful segments, the second segment becomes a
subcategory (e.g., `service-healthcheck-defaults`).

### Example

Given a docker-compose schema with these defaults:

```yaml
defaults:
  services.*.restart: "no"
  services.*.privileged: false
  services.*.read_only: false
  services.*.stdin_open: false
  services.*.tty: false
```

The emitted class block is:

```yaml
# decoct: defaults stripped using docker-compose schema
# @class service-defaults: privileged=False, read_only=False, restart=no, stdin_open=False, tty=False
services:
  web:
    image: nginx:1.25.3
    read_only: true
    ports:
      - "8080:80"
  db:
    image: postgres:16
    restart: always
```

Here `read_only: true` and `restart: always` remain because they differ from the
defaults listed in `@class service-defaults`.

Long class lines are truncated to 100 characters with a trailing `...` to avoid
excessive comment width.

## Deviation Annotations

The `annotate-deviations` pass adds inline end-of-line comments to values that
violate assertions. These comments use the `[!]` marker so they stand out visually.

### Format

Three annotation styles are used depending on the assertion:

| Situation                              | Comment format                              |
|----------------------------------------|---------------------------------------------|
| Value violates a pattern/value check   | `# [!] standard: <expected value>`          |
| Value violates a general assertion     | `# [!] assertion: <assertion text>`         |
| Required key is missing entirely       | `# [!] missing: <assertion text>` (logged but not written as YAML comment) |

Annotations are only added for assertions that have a `match` block with a
machine-evaluable condition. Assertions without `match` serve as LLM context only
and do not produce annotations.

### Example

Given an assertion requiring pinned image tags:

```yaml
assertions:
  - id: docker-no-latest
    assert: Image tags must be pinned to specific versions
    match:
      path: services.*.image
      pattern: "^(?!.*:latest$)"
    severity: must
```

A service using `:latest` is annotated:

```yaml
services:
  worker:
    image: acme-worker:latest  # [!] assertion: Image tags must be pinned to specific versions
```

An assertion with a `value` match (e.g., `value: json-file`) produces:

```yaml
services:
  worker:
    logging:
      driver: syslog  # [!] standard: json-file
```

## Deviation Summary

The `deviation-summary` pass adds a summary comment block at the top of the
document, before any content. This gives readers an immediate count of
non-conformance issues.

### Format

```
# decoct: N deviations from standards
# [!] <assertion-id>: <path>
# [!] <assertion-id>: <path>
```

The first line states the total count. Each subsequent line identifies one
deviation by its assertion ID and the dotted path to the offending value.

### Example

```yaml
# decoct: 2 deviations from standards
# [!] docker-no-latest: services.worker.image
# [!] docker-logging: services.worker.logging.driver
services:
  api:
    image: acme-api:3.1.0
    restart: unless-stopped
  worker:
    image: acme-worker:latest  # [!] assertion: Image tags must be pinned to specific versions
    logging:
      driver: syslog  # [!] standard: json-file
```

Note: when both `emit-classes` and `deviation-summary` run, the deviation summary
replaces the class block as the document start comment (since both use
`yaml_set_start_comment`). The pass ordering ensures deviation-summary runs after
emit-classes.

## Secret Redaction

The `strip-secrets` pass replaces detected secrets with the sentinel value
`[REDACTED]`. This pass always runs first in the pipeline, before any other
processing or LLM contact.

Secrets are detected by three methods:

- **path_pattern** -- the key path matches a known secret pattern (e.g.,
  `*.password`, `*.api_key`, `*.credentials.*`)
- **regex** -- the value matches a known secret format (e.g., AWS access keys,
  GitHub tokens, private key blocks, bearer tokens)
- **entropy** -- the value is long enough (16+ characters by default) and has
  Shannon entropy above the threshold (4.5 bits by default), suggesting a
  random token or key

Original secret values are never logged, printed, or stored anywhere. The audit
trail records only the path and detection method.

### Example

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: "[REDACTED]"
      DATABASE_URL: "[REDACTED]"
```

## Token Statistics

Token statistics are printed to stderr when `--stats` or `--stats-only` is used.

### Format

```
Tokens: <input> -> <output> (saved <count>, <pct>%)
```

For example:

```
Tokens: 342 -> 187 (saved 155, 45.3%)
```

### Multi-file runs

When processing multiple files, each file gets its own statistics line prefixed
with the filename, followed by an aggregate total:

```
docker-compose.yaml: Tokens: 342 -> 187 (saved 155, 45.3%)
docker-compose.prod.yaml: Tokens: 218 -> 104 (saved 114, 52.3%)
Total: Tokens: 560 -> 291 (saved 269, 48.0%)
```

### Encoding

Token counts use the `cl100k_base` tiktoken encoding by default (used by GPT-4
and Claude). This can be changed with `--encoding`, for example
`--encoding o200k_base`.

When `--stats-only` is used, the compressed YAML is suppressed and only the
statistics line is printed.

## Removed Items Report

The `--show-removed` flag prints a detailed report to stderr showing what each
pass removed.

### Format

Each pass that removed items or produced details gets a section:

```
=== <filename> ===
--- <pass-name> ---
  Removed: <count> items
  <detail line>
  <detail line>
```

The filename header (`=== ... ===`) appears only for multi-file runs or when
processing a named file (not stdin).

### Example

```
=== docker-compose.yaml ===
--- strip-secrets ---
  Removed: 2 items
  db.environment.POSTGRES_PASSWORD (path_pattern)
  db.environment.DATABASE_URL (entropy)
--- strip-comments ---
  Removed: 4 items
--- strip-defaults ---
  Removed: 8 items
--- strip-conformant ---
  Removed: 3 items
  docker-no-latest: services.api.image
  docker-logging: services.api.logging.driver
  docker-logging: services.redis.logging.driver
--- emit-classes ---
  2 classes emitted
--- annotate-deviations ---
  docker-no-latest: services.worker.image
--- deviation-summary ---
  decoct: 1 deviations from standards
  [!] docker-no-latest: services.worker.image
```

For strip-secrets, the detail lines show the path and detection method in
parentheses. The actual secret values are never included.

## Using Compressed Output with LLMs

decoct output is designed to be pasted directly into LLM prompts. Each element
serves a specific purpose:

- **`@class` definitions** tell the LLM what default values were stripped and how
  to reconstruct them.
- **`[!]` deviation annotations** highlight exactly which values need attention,
  saving the LLM from having to evaluate the entire config against standards.
- **The deviation summary** gives a quick count and index of non-conformance at
  the top of the document.

### Suggested prompt preamble

When providing compressed output to an LLM, include context like this:

> The following config has been compressed by decoct. Default values have been
> stripped -- see @class definitions for reconstruction. Items marked [!] are
> deviations from standards.

This primes the LLM to understand the format and interpret the annotations
correctly.

## Reconstituting Full Documents

The compressed output can be expanded back to its full form using the `@class`
definitions.

### How to reconstruct

1. Read each `@class` line to get the field=value pairs that were stripped.
2. For every node matching the class path pattern (e.g., every service for
   `service-defaults`), add back each field=value pair that is not already
   present in the compressed output.
3. Values already present in the compressed output take precedence -- they were
   kept because they differ from the default.

### Example

Given this compressed output:

```yaml
# decoct: defaults stripped using docker-compose schema
# @class service-defaults: privileged=False, restart=no, stdin_open=False, tty=False
services:
  web:
    image: nginx:1.25.3
    restart: always
```

Reconstituting `services.web`:

```yaml
services:
  web:
    image: nginx:1.25.3
    restart: always         # kept: differs from default "no"
    privileged: false       # restored from @class service-defaults
    stdin_open: false       # restored from @class service-defaults
    tty: false              # restored from @class service-defaults
```

### Limitations

- **Comments are gone.** The `strip-comments` pass removes YAML comments from the
  original input. These cannot be recovered from the compressed output.
- **Pruned empty containers** are not recorded. If removing defaults left an empty
  mapping that was then pruned, the key itself will be absent and not listed in
  any class definition.
- **Assertion-only stripping.** Values removed by `strip-conformant` (because they
  fully conform to assertions) are not recorded in class definitions. They can be
  inferred from the assertions file but are not self-contained in the output.

An LLM can perform reconstruction automatically when given the compressed output
and the prompt preamble described above. For programmatic reconstruction, parse
the `@class` comments and apply the defaults to matching paths.
