# decoct

Infrastructure context compression for LLMs.

> **Status: Under active development.** API may change before 1.0.

decoct compresses infrastructure data (YAML, JSON) for LLM context windows --
stripping platform defaults, removing noise, and highlighting deviations from
your design standards. Typically saves 40-60% of tokens while making output
more informative, not less.

## Install

```bash
pip install decoct
```

For LLM-powered features (optional):

```bash
pip install decoct[llm]
```

## Quick Start

```bash
# Compress a Docker Compose file (auto-detects schema)
decoct compress docker-compose.yml

# Use a specific bundled schema
decoct compress docker-compose.yml --schema docker-compose

# Compress cloud-init config
decoct compress cloud-config.yaml --schema cloud-init

# Check conformance against deployment standards
decoct compress docker-compose.yml --profile docker-compose

# Show token savings
decoct compress docker-compose.yml --schema docker-compose --stats

# Show what was removed
decoct compress docker-compose.yml --schema docker-compose --show-removed

# Write compressed output to file
decoct compress docker-compose.yml --schema docker-compose -o compressed.yaml

# Process a directory of files
decoct compress ./config/ --recursive --stats

# JSON input (terraform state, etc.)
decoct compress terraform.tfstate --schema terraform-state
```

## What It Does

Three-tier compression pipeline, each tier building on the last:

1. **Generic cleanup** (~15% savings) -- strip secrets, comments, empty containers
2. **Platform defaults** (~45%) -- remove values matching known schema defaults
3. **Standards conformance** (~60%) -- strip values conforming to your assertions, annotate deviations

### Bundled Schemas

| Schema | Platform | Defaults |
|--------|----------|----------|
| `docker-compose` | Docker Compose | ~60 defaults from the Compose spec |
| `cloud-init` | cloud-init | ~55 defaults from upstream JSON Schema |
| `terraform-state` | Terraform | System-managed envelope fields |

### Bundled Profiles

Profiles combine a schema with assertion checks:

| Profile | Includes |
|---------|----------|
| `docker-compose` | Docker Compose schema + deployment standards assertions |

### Example Output

Input (docker-compose.yml with 1,400 tokens):
```yaml
services:
  web:
    image: nginx:1.25.3
    restart: unless-stopped
    privileged: false        # <-- default, stripped
    read_only: false         # <-- default, stripped
    healthcheck:
      test: [CMD, curl, -f, http://localhost]
      interval: 30s          # <-- default, stripped
      timeout: 30s           # <-- default, stripped
      retries: 3             # <-- default, stripped
    logging:
      driver: json-file      # <-- default, stripped
```

Compressed output (~1,200 tokens, 12% saved on well-configured files, up to 60% on verbose configs):
```yaml
services:
  web:
    image: nginx:1.25.3
    restart: unless-stopped
    healthcheck:
      test: [CMD, curl, -f, http://localhost]
    logging: {}
```

## Pipeline Passes

| Pass | What It Does |
|------|-------------|
| `strip-secrets` | Redacts secrets (entropy + regex + path patterns) |
| `strip-comments` | Removes YAML comments |
| `strip-defaults` | Removes values matching schema defaults |
| `strip-conformant` | Strips values matching assertion expectations |
| `annotate-deviations` | Adds `[!]` comments on non-conformant values |
| `deviation-summary` | Appends a summary of all deviations |
| `drop-fields` | Removes fields by glob pattern |
| `keep-fields` | Keeps only fields matching glob patterns |
| `prune-empty` | Removes empty dicts/lists left by other passes |

## Custom Schemas

Create a schema file to define defaults for any platform:

```yaml
platform: my-platform
source: vendor documentation
confidence: authoritative
defaults:
  services.*.restart: "no"
  services.*.privileged: false
  settings.timeout: 30
  settings.retries: 3
drop_patterns: []
system_managed: []
```

```bash
decoct compress config.yaml --schema my-schema.yaml
```

## Custom Assertions

Define deployment standards as machine-evaluable assertions:

```yaml
assertions:
  - id: require-pinned-images
    assert: All container images must use pinned versions
    severity: must
    match:
      path: services.*.image
      pattern: "^(?!.*:latest$)(?=.*:.+$)"
  - id: require-healthcheck
    assert: All services must have healthchecks
    severity: must
    match:
      path: services.*.healthcheck
      exists: true
```

```bash
decoct compress docker-compose.yml --assertions standards.yaml
```

## Profiles

Profiles bundle a schema, assertions, and pass configuration:

```yaml
name: my-profile
schema: ./my-schema.yaml
assertions:
  - ./my-assertions.yaml
passes:
  strip-secrets:
  strip-comments:
  strip-defaults:
  strip-conformant:
  annotate-deviations:
  deviation-summary:
  prune-empty:
```

```bash
decoct compress config.yaml --profile my-profile.yaml
```

## Development

```bash
git clone https://github.com/decoct-io/decoct.git
cd decoct
pip install -e ".[dev]"
pytest --cov=decoct -v    # Run tests
ruff check src/ tests/    # Lint
mypy src/                 # Type check
```

## Licence

MIT -- see [LICENSE](LICENSE).
