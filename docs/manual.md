# decoct User Manual

decoct compresses infrastructure configuration (YAML, JSON) for LLM context windows. It strips platform defaults, removes noise, redacts secrets, and highlights deviations from your design standards — typically saving 40-60% of tokens while making output more informative.

## Installation

```bash
pip install decoct
```

For development:

```bash
pip install -e ".[dev]"
```

## Quick Start

Compress a YAML file with basic cleanup (secret redaction + comment stripping):

```bash
decoct compress docker-compose.yaml
```

Pipe from stdin:

```bash
cat docker-compose.yaml | decoct compress
```

See token savings:

```bash
decoct compress docker-compose.yaml --stats
```

Output:

```
services:
  web:
    image: nginx:1.25.3
    ports:
      - "8080:80"
Tokens: 142 → 58 (saved 84, 59.2%)
```

## Commands

### `decoct compress`

```
decoct compress [FILES...] [OPTIONS]
```

Runs the compression pipeline on one or more YAML/JSON files. If no files are given, reads from stdin.

#### Arguments

| Argument | Description |
|----------|-------------|
| `FILES` | One or more input files. Omit to read from stdin. |

#### Options

| Option | Description |
|--------|-------------|
| `--schema PATH` | Schema file defining platform defaults to strip. |
| `--assertions PATH` | Assertions file defining design standards. |
| `--profile PATH` | Profile file bundling schema, assertions, and pass config. |
| `--stats` | Print token statistics to stderr after the compressed output. |
| `--stats-only` | Print only token statistics (no YAML output). |
| `--show-removed` | Print details of what each pass removed (to stderr). |
| `-o, --output PATH` | Write compressed output to a file instead of stdout. |
| `--encoding TEXT` | Tiktoken encoding for token counting. Default: `cl100k_base`. |

#### Examples

```bash
# Basic compression (secrets + comments stripped)
decoct compress my-config.yaml

# With platform defaults removed
decoct compress my-config.yaml --schema schemas/docker-compose.yaml

# With design standard enforcement
decoct compress my-config.yaml \
  --schema schemas/docker-compose.yaml \
  --assertions assertions/docker-services.yaml

# Using a profile (bundles schema + assertions + pass config)
decoct compress my-config.yaml --profile profiles/docker.yaml

# Save to file with stats
decoct compress my-config.yaml --schema schema.yaml -o compressed.yaml --stats

# Just check token savings without output
decoct compress my-config.yaml --schema schema.yaml --stats-only

# See what was removed
decoct compress my-config.yaml --schema schema.yaml --show-removed

# Multiple files
decoct compress service-a.yaml service-b.yaml

# From stdin
kubectl get deployment myapp -o yaml | decoct compress --schema k8s-schema.yaml
```

### `decoct --version`

Print the installed version.

### `decoct --help`

Print help for the top-level command or any subcommand.

## Compression Pipeline

decoct runs a sequence of passes on your input. Each pass transforms the document in-place. The default pipeline (no profile) runs these passes in order:

| Pass | What it does | Requires |
|------|-------------|----------|
| **strip-secrets** | Redacts passwords, API keys, tokens, and high-entropy strings. Always runs first. | — |
| **strip-comments** | Removes all YAML comments. | — |
| **strip-defaults** | Removes values that match platform defaults from a schema. | `--schema` |
| **strip-conformant** | Removes values conforming to `must`-severity assertions. | `--assertions` |
| **annotate-deviations** | Adds `# [!]` comments on values that deviate from assertions. | `--assertions` |
| **deviation-summary** | Adds a summary comment block at the top listing all deviations. | `--assertions` |

Passes that require `--schema` or `--assertions` are only included when those options are provided.

### Three Compression Tiers

1. **Generic cleanup** (~15% savings) — secrets redacted, comments stripped.
2. **Platform defaults** (~45% savings) — add `--schema` to strip values matching known defaults.
3. **Standards conformance** (~60% savings) — add `--assertions` to also strip conformant values and annotate deviations.

## Configuration Files

### Schema Files

A schema describes platform defaults and system-managed fields. When a value in your input matches a default, it gets stripped.

```yaml
platform: docker-compose
source: Docker Compose specification v3.8
confidence: authoritative

defaults:
  services.*.restart: "no"
  services.*.network_mode: bridge
  services.*.privileged: false
  services.*.read_only: false
  services.*.stdin_open: false
  services.*.tty: false

drop_patterns:
  - "**.uuid"
  - "**.managedFields"

system_managed:
  - "**.creationTimestamp"
  - "**.resourceVersion"
```

#### Schema Fields

| Field | Required | Description |
|-------|----------|-------------|
| `platform` | Yes | Platform name (e.g. `docker-compose`, `kubernetes`). |
| `source` | Yes | Where the defaults come from (e.g. spec name and version). |
| `confidence` | Yes | One of `authoritative`, `high`, `medium`, `low`. |
| `defaults` | No | Map of path patterns to their default values. |
| `drop_patterns` | No | List of path patterns to always drop (e.g. UUIDs). |
| `system_managed` | No | List of path patterns for system-generated fields. |

### Assertion Files

Assertions encode your design standards. The pipeline uses them to identify conformant values (strip them) and deviations (annotate them).

```yaml
assertions:
  - id: no-latest
    assert: Image tags must not use latest
    match:
      path: services.*.image
      pattern: "^(?!.*:latest$)"
    rationale: Reproducible deployments
    severity: must
    example: "nginx:1.25.3"

  - id: restart-policy
    assert: Containers must use unless-stopped restart policy
    match:
      path: services.*.restart
      value: unless-stopped
    rationale: Proper restart behaviour
    severity: must

  - id: healthcheck-required
    assert: All containers should have health checks
    rationale: Monitoring
    severity: should
```

#### Assertion Fields

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Unique identifier. |
| `assert` | Yes | Human-readable description of the standard. |
| `rationale` | Yes | Why this standard exists. |
| `severity` | Yes | `must`, `should`, or `may`. Only `must` assertions trigger stripping. |
| `match` | No | Machine-evaluable match condition (see below). Without `match`, the assertion is LLM context only. |
| `exceptions` | No | Documented exceptions to the rule. |
| `example` | No | Example of a conformant value. |
| `related` | No | List of related assertion IDs. |
| `source` | No | Where this standard comes from. |

#### Match Conditions

The `match` field defines how to evaluate conformance. It requires a `path` and one condition type:

| Condition | Description | Example |
|-----------|-------------|---------|
| `value` | Exact value match (case-insensitive). | `value: json-file` |
| `pattern` | Regex pattern the value must match. | `pattern: "^(?!.*:latest$)"` |
| `range` | Numeric range `[min, max]` (inclusive). | `range: [1, 65535]` |
| `contains` | Value (a list) must contain this item. | `contains: http` |
| `not_value` | Value must NOT equal this. | `not_value: latest` |

If no condition is specified (just a `path`), the assertion matches any value at that path.

#### Path Patterns

Paths use dot notation with wildcards:

| Pattern | Matches |
|---------|---------|
| `services.web.image` | Exact path. |
| `services.*.image` | `*` matches any single segment — e.g. `services.web.image`, `services.db.image`. |
| `**.managedFields` | `**` matches any number of segments — finds `managedFields` at any depth. |
| `metadata.**.name` | `**` in the middle — `metadata.labels.name`, `metadata.annotations.app.name`, etc. |

### Profile Files

A profile bundles a schema reference, assertion references, and pass configuration into a single file.

```yaml
name: docker-compose
schema: schemas/docker-compose.yaml
assertions:
  - assertions/docker-services.yaml
passes:
  strip-comments:
  strip-defaults:
    skip_low_confidence: true
  drop-fields:
    patterns:
      - "**.uuid"
```

Paths in `schema` and `assertions` are relative to the profile file's directory.

#### Profile Fields

| Field | Description |
|-------|-------------|
| `name` | Profile name (informational). |
| `schema` | Relative path to a schema file. |
| `assertions` | List of relative paths to assertion files. |
| `passes` | Map of pass names to their configuration. Use `null` (or empty) for default config. |

#### Available Pass Configurations

| Pass | Config Options |
|------|----------------|
| `strip-secrets` | `secret_paths` (list), `entropy_threshold` (float), `min_entropy_length` (int) |
| `strip-comments` | — |
| `strip-defaults` | `skip_low_confidence` (bool) |
| `drop-fields` | `patterns` (list of path patterns) |
| `keep-fields` | `patterns` (list of path patterns to retain) |
| `strip-conformant` | — |
| `annotate-deviations` | — |
| `deviation-summary` | — |

## Secret Detection

The `strip-secrets` pass always runs first and uses three detection methods:

1. **Path patterns** — keys like `*.password`, `*.secret`, `*.api_key`, `*.credentials`, `*.private_key`, `*.connection_string`, `*.env.*` are always redacted.

2. **Regex patterns** — matches known secret formats:
   - AWS access keys (`AKIA...`)
   - Azure connection strings
   - PEM private key blocks
   - Bearer tokens
   - GitHub tokens (`ghp_`, `gho_`, `ghs_`, `ghr_`, `github_pat_`)
   - Generic credential pairs (`password=...`, `secret:...`)

3. **Shannon entropy** — strings longer than 16 characters with entropy >= 4.5 bits are flagged as likely secrets.

All redacted values are replaced with `[REDACTED]`. The original values are never logged or stored.

## Output Format

### Compressed YAML

The compressed output preserves YAML structure and ordering. Annotations appear as comments:

```yaml
# decoct: 2 deviations from standards
# [!] no-latest: services.db.image
# [!] restart-policy: services.db.restart
services:
  web: {}
  db:
    image: postgres:latest  #  [!] assertion: Image tags must not use latest
    restart: always  #  [!] standard: unless-stopped
```

- Conformant values are removed (the `web` service is empty because all its values conformed).
- Deviating values are kept and annotated with `# [!]` comments.
- A summary block at the top lists all deviations.

### Token Statistics

When using `--stats` or `--stats-only`:

```
Tokens: 142 → 58 (saved 84, 59.2%)
```

Statistics are printed to stderr so they don't mix with the YAML output.

### Removed Items

When using `--show-removed`:

```
--- strip-secrets ---
  Removed: 2 items
  db.password (path_pattern)
  db.connection_string (regex:azure_connection_string)
--- strip-defaults ---
  Removed: 5 items
--- strip-conformant ---
  Removed: 3 items
```

Details are printed to stderr.

## Library Usage

decoct can also be used as a Python library:

```python
from ruamel.yaml import YAML

from decoct.assertions.loader import load_assertions
from decoct.passes.strip_secrets import strip_secrets
from decoct.passes.strip_conformant import strip_conformant
from decoct.passes.annotate_deviations import annotate_deviations
from decoct.passes.deviation_summary import deviation_summary
from decoct.schemas.loader import load_schema
from decoct.passes.strip_defaults import strip_defaults
from decoct.tokens import create_report, format_report

# Load input
yaml = YAML(typ="rt")
doc = yaml.load(open("docker-compose.yaml"))

# Run individual passes
audit = strip_secrets(doc)
schema = load_schema("schemas/docker-compose.yaml")
count = strip_defaults(doc, schema)
assertions = load_assertions("assertions/docker-services.yaml")
count = strip_conformant(doc, assertions)
deviations = annotate_deviations(doc, assertions)
summary_lines = deviation_summary(doc, assertions)
```

Or use the pipeline:

```python
from decoct.pipeline import Pipeline
from decoct.passes.strip_secrets import StripSecretsPass
from decoct.passes.strip_comments import StripCommentsPass
from decoct.passes.strip_defaults import StripDefaultsPass
from decoct.schemas.loader import load_schema

schema = load_schema("schemas/docker-compose.yaml")
pipeline = Pipeline([
    StripSecretsPass(),
    StripCommentsPass(),
    StripDefaultsPass(schema=schema),
])

yaml = YAML(typ="rt")
doc = yaml.load(open("docker-compose.yaml"))
stats = pipeline.run(doc)

# doc is now modified in-place
# stats.pass_results contains per-pass statistics
```

## Token Counting

decoct uses [tiktoken](https://github.com/openai/tiktoken) for accurate token counting. Supported encodings:

| Encoding | Used by |
|----------|---------|
| `cl100k_base` (default) | GPT-4, GPT-3.5-turbo, Claude |
| `o200k_base` | GPT-4o |

Change the encoding with `--encoding`:

```bash
decoct compress input.yaml --stats --encoding o200k_base
```
