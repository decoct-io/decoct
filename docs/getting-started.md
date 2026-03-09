# Getting Started with decoct

decoct compresses infrastructure configuration for LLM context windows. It strips platform defaults, redacts secrets, removes noise, and highlights deviations from your design standards -- saving 20-80% of tokens while making the output more informative, not less.

This guide walks you through installation, your first compression, and progressively deeper features using a Docker Compose file as a running example.

## Installation

```bash
pip install decoct              # Core pipeline
pip install decoct[llm]         # Add LLM-powered features (schema/assertion learning)
pip install -e ".[dev]"         # Development install
```

Requires Python 3.10+.

Verify the installation:

```bash
decoct --version
```

## Your First Compression

Create a file called `docker-compose.yml` with a typical web service definition:

```yaml
# Main web application
services:
  web:
    image: nginx:1.25.3
    restart: unless-stopped
    privileged: false
    read_only: false
    ports:
      - "8080:80"
    environment:
      DATABASE_URL: "postgres://admin:s3cret-p4ss@db:5432/myapp"
      API_KEY: "sk-proj-abc123def456ghi789jklmnopqrstuvwxyz"
    healthcheck:
      test: [CMD, curl, -f, http://localhost]
      interval: 30s
      timeout: 30s
      retries: 3
      start_period: 0s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

Run the basic compression pipeline:

```bash
decoct compress docker-compose.yml
```

Output:

```yaml
services:
  web:
    image: nginx:1.25.3
    restart: unless-stopped
    privileged: false
    read_only: false
    ports:
    - '8080:80'
    environment:
      DATABASE_URL: '[REDACTED]'
      API_KEY: '[REDACTED]'
    healthcheck:
      test: [CMD, curl, -f, http://localhost]
      interval: 30s
      timeout: 30s
      retries: 3
      start_period: 0s
    logging:
      driver: json-file
      options:
        max-size: '10m'
        max-file: '3'
```

Without a schema, decoct applies generic cleanup: secrets are redacted (`DATABASE_URL` and `API_KEY` both replaced with `[REDACTED]`) and YAML comments are stripped. The structure and all non-secret values are preserved.

## Adding a Schema

decoct ships with bundled schemas for 25 platforms. The `docker-compose` schema knows about ~35 default values from the Compose specification. When a value in your file matches a known default, it gets stripped -- because defaults carry zero information.

```bash
decoct compress docker-compose.yml --schema docker-compose --stats
```

Output:

```yaml
# decoct: defaults stripped using docker-compose schema
# @class service-defaults: privileged=false, read_only=false, restart=no, ...
# @class service-healthcheck-defaults: interval=30s, retries=3, start_period=0s, timeout=30s, ...
# @class service-logging-defaults: driver=json-file
services:
  web:
    image: nginx:1.25.3
    restart: unless-stopped
    ports:
    - '8080:80'
    environment:
      DATABASE_URL: '[REDACTED]'
      API_KEY: '[REDACTED]'
    healthcheck:
      test: [CMD, curl, -f, http://localhost]
    logging:
      options:
        max-size: '10m'
        max-file: '3'
Tokens: 128 -> 82 (saved 46, 35.9%)
```

Several things happened:

- **`privileged: false`** and **`read_only: false`** were stripped -- they are the Compose defaults.
- **`healthcheck.interval: 30s`**, **`timeout: 30s`**, **`retries: 3`**, and **`start_period: 0s`** were all stripped -- all defaults.
- **`logging.driver: json-file`** was stripped -- the default driver.
- **`restart: unless-stopped`** was kept -- it differs from the default (`no`).
- **`@class` header comments** document what was stripped, so the reader (human or LLM) can reconstruct the full configuration.

The `--stats` flag prints token statistics to stderr. The token line shows input and output token counts with savings percentage.

## Adding Assertions

Assertions encode your organisation's design standards as machine-evaluable rules. Create a file called `standards.yaml`:

```yaml
assertions:
  - id: require-pinned-images
    assert: Image tags must be pinned to specific versions, not :latest
    match:
      path: services.*.image
      pattern: "^(?!.*:latest$)(?=.*:.+$)"
    rationale: Pinned versions ensure reproducible deployments
    severity: must
    example: "nginx:1.25.3"

  - id: require-restart-policy
    assert: Restart policy must be unless-stopped or always
    match:
      path: services.*.restart
      pattern: "^(unless-stopped|always)$"
    rationale: Services must automatically recover from crashes
    severity: must

  - id: require-healthcheck
    assert: All application containers must have health checks configured
    match:
      path: services.*.healthcheck
      exists: true
    rationale: Health checks enable proper orchestration and monitoring
    severity: must

  - id: require-log-rotation
    assert: Log rotation max-size must be configured
    match:
      path: services.*.logging.options.max-size
      pattern: ".+"
    rationale: Unbounded logs cause disk exhaustion
    severity: must
```

Now run with both schema and assertions:

```bash
decoct compress docker-compose.yml --schema docker-compose --assertions standards.yaml
```

Output:

```yaml
# decoct: defaults stripped using docker-compose schema
# @class service-defaults: privileged=false, read_only=false, restart=no, ...
# @class service-healthcheck-defaults: interval=30s, retries=3, start_period=0s, timeout=30s, ...
# @class service-logging-defaults: driver=json-file
services:
  web:
    ports:
    - '8080:80'
    environment:
      DATABASE_URL: '[REDACTED]'
      API_KEY: '[REDACTED]'
    healthcheck:
      test: [CMD, curl, -f, http://localhost]
    logging:
      options:
        max-size: '10m'
        max-file: '3'
```

The assertions added another layer of compression:

- **`image: nginx:1.25.3`** was stripped -- it conforms to the `require-pinned-images` assertion (it is pinned and not `:latest`). Since it meets the standard, it carries no surprising information.
- **`restart: unless-stopped`** was stripped -- it conforms to `require-restart-policy`.
- The healthcheck and log rotation values were kept because they carry meaningful configuration detail.

If a value _deviates_ from an assertion, it stays in the output and gets annotated. For example, if a service used `image: postgres:latest`, the output would include:

```yaml
    image: postgres:latest  #  [!] assertion: Image tags must be pinned to specific versions, not :latest
```

A deviation summary block at the top lists all violations:

```yaml
# decoct: 1 deviation from standards
# [!] require-pinned-images: services.db.image
```

This way, the compressed output actively draws attention to problems rather than burying them in noise.

## Using a Profile

A profile bundles a schema, assertions, and pass configuration into a single reusable unit. decoct ships with a bundled `docker-compose` profile that combines the Docker Compose schema with deployment standards assertions.

```bash
decoct compress docker-compose.yml --profile docker-compose
```

This is equivalent to specifying the schema and assertions separately:

```bash
decoct compress docker-compose.yml \
  --schema docker-compose \
  --assertions deployment-standards.yaml
```

Profiles are useful when you want a consistent compression configuration across a team or CI pipeline. You can also create your own profile files:

```yaml
name: my-team-docker
schema: ./schemas/docker-compose.yaml
assertions:
  - ./assertions/team-standards.yaml
passes:
  strip-secrets:
  strip-comments:
  strip-defaults:
  strip-conformant:
  annotate-deviations:
  deviation-summary:
  prune-empty:
```

Then reference it by path:

```bash
decoct compress docker-compose.yml --profile my-profile.yaml
```

## Processing Multiple Files

Compress several files at once by listing them:

```bash
decoct compress service-a.yaml service-b.yaml service-c.yaml --stats
```

Or use shell globbing:

```bash
decoct compress *.yaml --stats
```

For directories, use `--recursive` to walk subdirectories:

```bash
decoct compress ./configs/ --recursive --stats
```

When processing multiple files, decoct prints per-file statistics and an aggregate total:

```
configs/docker-compose.yaml: Tokens: 142 -> 82 (saved 60, 42.3%)
configs/prometheus.yaml: Tokens: 310 -> 185 (saved 125, 40.3%)
configs/grafana.yaml: Tokens: 520 -> 248 (saved 272, 52.3%)
Total: Tokens: 972 -> 515 (saved 457, 47.0%)
```

Each file's compressed output is separated by a header comment (`# --- path ---`) in the output stream.

Write compressed output to a file with `-o`:

```bash
decoct compress docker-compose.yml --schema docker-compose -o compressed.yaml
```

Or show only statistics without any YAML output:

```bash
decoct compress ./configs/ --recursive --stats-only
```

## Next Steps

- [CLI Reference](cli-reference.md) -- full list of commands and options
- [Schema Authoring](schema-authoring.md) -- create custom schemas for your platforms
- [Assertion Authoring](assertion-authoring.md) -- encode your team's design standards
- [Bundled Schemas](bundled-schemas.md) -- schemas for all 25 supported platforms
- [Cookbook](cookbook.md) -- recipes for common workflows (Kubernetes, Terraform, CI pipelines, and more)
