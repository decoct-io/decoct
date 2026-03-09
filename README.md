# decoct

Infrastructure context compression for LLMs.

> **Status: Under active development.** API may change before 1.0.

decoct compresses infrastructure data (YAML, JSON, INI/config files) for LLM context windows --
stripping platform defaults, removing noise, and highlighting deviations from
your design standards. Saves 20-80% of tokens depending on input verbosity,
while making output more informative, not less.

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

# INI/config file input
decoct compress postgresql.conf --schema postgresql

# Kubernetes manifests
decoct compress deployment.yaml --schema kubernetes

# Ansible playbooks
decoct compress playbook.yaml --schema ansible-playbook

# Learn assertions from a corpus of existing configs
decoct assertion learn -c config1.yaml -c config2.yaml -o standards.yaml

# Derive a schema from example files using Claude (requires decoct[llm])
decoct schema learn -e nginx.conf.yaml -e haproxy.yaml -o my-schema.yaml
```

## What It Does

Three-tier compression pipeline, each tier building on the last:

1. **Generic cleanup** (~15%) -- strip secrets, comments, empty containers
2. **Platform defaults** (~20-55%) -- remove values matching known schema defaults
3. **Standards conformance** (~30-80%) -- strip values conforming to your assertions, annotate deviations

Input formats: YAML, JSON, and INI/config files (`.ini`, `.conf`, `.cfg`, `.cnf`, `.properties`).
All input is normalised to YAML for processing.

## Supported Platforms

decoct ships with bundled schemas for 25 platforms. Platforms marked with **(auto)** are
detected automatically from file content or naming conventions.

**Container/Orchestration** -- Docker Compose **(auto)**, Kubernetes **(auto)**

**Configuration Management** -- Ansible **(auto)**, cloud-init **(auto)**, OpenSSH sshd_config

**Infrastructure as Code** -- Terraform state **(auto)**, AWS CloudFormation, Azure ARM, GCP Resources

**CI/CD** -- GitHub Actions **(auto)**, GitLab CI, Argo CD

**Databases** -- PostgreSQL, MariaDB/MySQL, MongoDB, Redis, Kafka

**Observability** -- Prometheus **(auto)**, Grafana, OpenTelemetry Collector, Fluent Bit

**Networking** -- Traefik **(auto)**

**Identity** -- Keycloak, Entra ID, Intune

### Bundled Schemas

| Category | Schema | Platform | Defaults |
|----------|--------|----------|----------|
| Container/Orchestration | `docker-compose` | Docker Compose | ~35 defaults from the Compose spec |
| | `kubernetes` | Kubernetes | ~55 defaults + system-managed fields |
| Configuration Management | `ansible-playbook` | Ansible | ~120 defaults from builtin module docs |
| | `cloud-init` | cloud-init | ~55 defaults from upstream JSON Schema |
| | `sshd-config` | OpenSSH | ~35 defaults from sshd_config(5) |
| Infrastructure as Code | `terraform-state` | Terraform | System-managed envelope fields |
| | `aws-cloudformation` | AWS CloudFormation | ~60 defaults from CFN spec |
| | `azure-arm` | Azure ARM | ~80 defaults from ARM schema |
| | `gcp-resources` | GCP Resources | ~45 defaults from GCP API schemas |
| CI/CD | `github-actions` | GitHub Actions | ~10 defaults from workflow spec |
| | `gitlab-ci` | GitLab CI | ~30 defaults from CI config spec |
| | `argocd` | Argo CD | ~20 defaults from Argo CD CRDs |
| Databases | `postgresql` | PostgreSQL | ~150+ defaults from postgresql.conf |
| | `mariadb-mysql` | MariaDB/MySQL | ~70 defaults from server config |
| | `mongodb` | MongoDB | ~15 defaults from mongod.conf |
| | `redis` | Redis | ~60 defaults from redis.conf |
| | `kafka` | Kafka | ~60 defaults from server.properties |
| Observability | `prometheus` | Prometheus | ~55 defaults from prometheus.yml spec |
| | `grafana` | Grafana | ~150+ defaults from grafana.ini |
| | `opentelemetry-collector` | OpenTelemetry Collector | ~20 defaults from OTel config |
| | `fluent-bit` | Fluent Bit | ~65 defaults from fluent-bit.conf |
| Networking | `traefik` | Traefik | ~55 defaults from Traefik config |
| Identity | `keycloak` | Keycloak | ~80 defaults from Keycloak config |
| | `entra-id` | Entra ID | ~65 defaults from Entra ID policies |
| | `intune` | Intune | ~85 defaults from Intune profiles |

### Bundled Profiles

Profiles combine a schema with assertion checks:

| Profile | Includes |
|---------|----------|
| `docker-compose` | Docker Compose schema + deployment standards assertions |

### Example Output

Input (docker-compose.yml):
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

Compressed output:
```yaml
# decoct: defaults stripped using docker-compose schema
# @class service-defaults: privileged=false, read_only=false, restart=no, ...
# @class service-healthcheck-defaults: interval=30s, retries=3, timeout=30s, ...
# @class service-logging-defaults: driver=json-file
services:
  web:
    image: nginx:1.25.3
    restart: unless-stopped
    healthcheck:
      test: [CMD, curl, -f, http://localhost]
```

Savings vary by input: 12-20% on well-configured files (most values are intentional), 50-80% on verbose configs with many redundant defaults.

## Pipeline Passes

| Pass | What It Does |
|------|-------------|
| `strip-secrets` | Redacts secrets (entropy + regex + path patterns) |
| `strip-comments` | Removes YAML comments |
| `strip-defaults` | Removes values matching schema defaults |
| `strip-conformant` | Strips values matching assertion expectations |
| `annotate-deviations` | Adds `[!]` comments on non-conformant values |
| `deviation-summary` | Appends a summary of all deviations |
| `emit-classes` | Adds header comment listing stripped default classes |
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
  emit-classes:
  strip-conformant:
  annotate-deviations:
  deviation-summary:
  prune-empty:
```

```bash
decoct compress config.yaml --profile my-profile.yaml
```

## CLI Features

- `decoct compress` -- compress one or more files with optional schema/assertions/profile
- `decoct schema learn` -- derive a schema from example files using Claude
- `decoct assertion learn` -- learn assertions from a corpus of existing configs
- `decoct schema list` -- list bundled schemas
- `--stats` / `--show-removed` / `--recursive` / `-o` output options

## Documentation

- [Getting Started](docs/getting-started.md)
- [CLI Reference](docs/cli-reference.md)
- [User Manual](docs/manual.md)
- [Schema Authoring](docs/schema-authoring.md)
- [Assertion Authoring](docs/assertion-authoring.md)
- [Cookbook](docs/cookbook.md)
- [API Reference](docs/dev/api-reference.md)
- [Contributing](CONTRIBUTING.md)

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
