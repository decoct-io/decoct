# decoct Cookbook

Practical recipes for common tasks. Each recipe is self-contained -- copy, paste, adjust.

---

## 1. Compress Docker Compose for ChatGPT/Claude

Strip platform defaults, add `@class` headers so the LLM can reconstruct full values, and show token savings.

```bash
decoct compress docker-compose.yml --schema docker-compose --stats
```

The `docker-compose` short name resolves to the bundled schema that knows every Docker Compose default (restart, privileged, network_mode, healthcheck intervals, logging driver, deploy replicas, and more). The output includes `@class` comment headers that list what was stripped:

```yaml
# decoct: defaults stripped using docker-compose schema
# @class service-defaults: init=false, network_mode=bridge, privileged=false, ...
# @class service-healthcheck-defaults: interval=30s, retries=3, ...
services:
  web:
    image: nginx:1.25.3
    ports:
      - "8080:80"
Tokens: 312 -> 94 (saved 218, 69.9%)
```

Token statistics print to stderr so the YAML stays clean on stdout. Pipe the YAML into your clipboard or straight into a prompt.

---

## 2. Compress Kubernetes Manifests for Code Review

Pipe live cluster state through decoct to strip system-managed fields (`managedFields`, `resourceVersion`, `creationTimestamp`, `uid`, `generation`) and Kubernetes defaults.

```bash
kubectl get deployment myapp -o yaml | decoct compress --schema kubernetes
```

The bundled `kubernetes` schema knows common defaults and system-managed fields. To save the result to a file:

```bash
kubectl get deployment myapp -o yaml | decoct compress --schema kubernetes -o myapp-compressed.yaml
```

To see exactly what was removed:

```bash
kubectl get deployment myapp -o yaml | decoct compress --schema kubernetes --show-removed
```

The `--show-removed` output prints to stderr with per-pass breakdowns:

```
--- strip-secrets ---
  Removed: 0 items
--- strip-defaults ---
  Removed: 12 items
```

---

## 3. Compress Terraform State for Troubleshooting

Terraform state files are JSON but decoct auto-detects the format and converts internally.

```bash
decoct compress terraform.tfstate --schema terraform-state --stats
```

The bundled `terraform-state` schema strips the system-managed envelope (`serial`, `lineage`, `terraform_version` metadata) and known resource defaults. Output is always YAML regardless of input format.

For large state files, use `--stats-only` to check potential savings before committing to the full output:

```bash
decoct compress terraform.tfstate --schema terraform-state --stats-only
```

This prints only the token statistics line (no YAML output).

---

## 4. Compress Ansible Playbooks for Architecture Review

```bash
decoct compress playbook.yaml --schema ansible-playbook
```

The bundled `ansible-playbook` schema strips module defaults and system-managed fields. decoct also auto-detects Ansible playbooks (list of plays with `hosts` + `tasks`/`roles`) so you can often omit the `--schema` flag:

```bash
decoct compress playbook.yaml --stats
```

If auto-detection works, you will see the same default-stripping behavior without explicitly naming the schema.

---

## 5. Build a Custom Schema from Scratch

Create a file called `my-schema.yaml`:

```yaml
platform: my-platform
source: Internal documentation v2.1
confidence: high

defaults:
  settings.debug: false
  settings.log_level: info
  settings.timeout: 30
  settings.retries: 3
  server.port: 8080
  server.workers: 1

drop_patterns:
  - "**.internal_id"
  - "**.generated_at"

system_managed:
  - "**.last_modified"
  - "**.etag"
```

Test it against a config file:

```bash
decoct compress my-config.yaml --schema my-schema.yaml --show-removed --stats
```

The `--show-removed` flag confirms which fields matched your defaults. Iterate on the schema until the output looks right.

**Schema fields reference:**

| Field | Required | Description |
|-------|----------|-------------|
| `platform` | Yes | Platform name. |
| `source` | Yes | Where the defaults come from. |
| `confidence` | Yes | `authoritative`, `high`, `medium`, or `low`. |
| `defaults` | No | Path pattern to default value mappings. |
| `drop_patterns` | No | Paths to always remove (wildcards supported). |
| `system_managed` | No | Paths for system-generated fields. |

---

## 6. Learn a Schema from Production Configs

When you do not have vendor documentation handy, let Claude derive a schema from example configs. Requires `pip install decoct[llm]`.

```bash
decoct schema learn \
  -e prod-config1.yaml \
  -e prod-config2.yaml \
  -p my-platform \
  -o my-schema.yaml
```

You can also provide documentation files alongside examples for higher-quality results:

```bash
decoct schema learn \
  -e prod-config.yaml \
  -d vendor-docs.md \
  -p my-platform \
  -o my-schema.yaml
```

To merge learned defaults into an existing schema rather than overwriting:

```bash
decoct schema learn \
  -e new-config.yaml \
  -p my-platform \
  -m my-schema.yaml \
  -o my-schema.yaml
```

The `--merge` (`-m`) flag loads the existing schema, merges newly learned defaults in, and writes the combined result.

---

## 7. Encode Team Deployment Standards as Assertions

Create a file called `team-standards.yaml`:

```yaml
assertions:
  - id: no-latest-tags
    assert: Image tags must not use :latest
    match:
      path: services.*.image
      pattern: "^(?!.*:latest$)(?=.*:.+$)"
    rationale: Reproducible deployments require pinned versions
    severity: must
    example: "nginx:1.25.3"

  - id: restart-policy
    assert: Restart policy must be unless-stopped or always
    match:
      path: services.*.restart
      pattern: "^(unless-stopped|always)$"
    rationale: Services must recover from crashes automatically
    severity: must
    example: "unless-stopped"

  - id: healthcheck-required
    assert: All services should have health checks
    match:
      path: services.*.healthcheck
      exists: true
    rationale: Health checks enable proper dependency ordering
    severity: should
    exceptions: Infrastructure-only containers may rely on built-in health mechanisms

  - id: log-rotation
    assert: Log rotation max-size must be configured
    match:
      path: services.*.logging.options.max-size
      pattern: ".+"
    rationale: Unbounded logs cause disk exhaustion
    severity: must
    example: "10m"
```

Test against a real config:

```bash
decoct compress docker-compose.yaml \
  --schema docker-compose \
  --assertions team-standards.yaml \
  --stats
```

Conformant `must`-severity values are stripped. Deviations are annotated with `# [!]` comments and summarized at the top of the output:

```yaml
# decoct: 2 deviations from standards
# [!] no-latest-tags: services.db.image
# [!] restart-policy: services.db.restart
services:
  web: {}
  db:
    image: postgres:latest  #  [!] assertion: Image tags must not use :latest
    restart: always  #  [!] standard: unless-stopped or always
```

**Severity behavior:**

| Severity | Conformant values | Deviations |
|----------|-------------------|------------|
| `must` | Stripped (removed) | Annotated with `# [!]` |
| `should` | Kept | Annotated with `# [!]` |
| `may` | Kept | LLM context only |

---

## 8. Learn Assertions from a Corpus

Analyze a set of existing configs to discover common patterns and derive assertions automatically. Requires `pip install decoct[llm]`.

```bash
decoct assertion learn \
  -c configs/docker-compose-app1.yaml \
  -c configs/docker-compose-app2.yaml \
  -c configs/docker-compose-app3.yaml \
  -p docker-compose \
  -o learned-standards.yaml
```

The `-c` (corpus) flag triggers cross-file pattern analysis -- Claude examines what is consistent across files and what varies, then generates assertions for the consistent patterns.

You can also learn from standards documents or example files instead:

```bash
# From a standards document
decoct assertion learn -s deployment-policy.md -p docker-compose -o standards.yaml

# From example configs (not cross-file analysis)
decoct assertion learn -e good-config.yaml -p docker-compose -o standards.yaml
```

Note: `--corpus` (`-c`) and `--example` (`-e`) are mutually exclusive. Use `--corpus` for cross-file pattern discovery, `--example` for single-file analysis.

To merge learned assertions into an existing file:

```bash
decoct assertion learn \
  -c configs/*.yaml \
  -p docker-compose \
  -m existing-standards.yaml \
  -o existing-standards.yaml
```

---

## 9. Set Up a Profile for CI Integration

A profile bundles schema, assertions, and pass configuration into one reusable file. Create `.decoct/docker-compose.yaml` in your repo:

```yaml
name: docker-compose
schema: schemas/docker-compose.yaml
assertions:
  - assertions/team-standards.yaml
passes:
  strip-secrets:
  strip-comments:
  strip-defaults:
  strip-conformant:
  prune-empty:
  annotate-deviations:
  deviation-summary:
```

Paths in `schema` and `assertions` are relative to the profile file's directory.

Use it locally:

```bash
decoct compress docker-compose.yaml --profile .decoct/docker-compose.yaml --stats
```

You can also use the bundled `docker-compose` profile by short name (it includes bundled schema + bundled deployment-standards assertions):

```bash
decoct compress docker-compose.yaml --profile docker-compose --stats
```

Add to a GitHub Actions workflow for automated config review:

```yaml
# .github/workflows/config-review.yml
name: Config Review
on: [pull_request]
jobs:
  decoct:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install decoct
      - name: Check config compression
        run: |
          decoct compress docker-compose.yaml \
            --profile .decoct/docker-compose.yaml \
            --stats-only
      - name: Show deviations
        run: |
          decoct compress docker-compose.yaml \
            --profile .decoct/docker-compose.yaml \
            --show-removed
```

**Available pass configurations for profiles:**

| Pass | Config Options |
|------|----------------|
| `strip-secrets` | `secret_paths` (list), `entropy_threshold` (float), `min_entropy_length` (int) |
| `strip-comments` | (none) |
| `strip-defaults` | `skip_low_confidence` (bool) |
| `drop-fields` | `patterns` (list of path patterns) |
| `keep-fields` | `patterns` (list of path patterns to retain) |
| `strip-conformant` | (none) |
| `annotate-deviations` | (none) |
| `deviation-summary` | (none) |
| `prune-empty` | (none) |

---

## 10. Batch-Process a Config Directory

Compress all YAML and JSON files in a directory. The `--recursive` (`-r`) flag descends into subdirectories.

```bash
decoct compress ./configs/ --recursive --schema docker-compose --stats
```

decoct matches files with extensions `.yaml`, `.yml`, `.json`, `.ini`, `.conf`, `.cfg`, `.cnf`, and `.properties`. Each file is separated in the output with a header comment:

```
# --- configs/app1/docker-compose.yaml ---
services:
  web:
    image: nginx:1.25.3
# --- configs/app2/docker-compose.yaml ---
services:
  api:
    image: myapp:2.1.0
configs/app1/docker-compose.yaml: Tokens: 185 -> 62 (saved 123, 66.5%)
configs/app2/docker-compose.yaml: Tokens: 210 -> 71 (saved 139, 66.2%)
Total: Tokens: 395 -> 133 (saved 262, 66.3%)
```

Without `--recursive`, only top-level files in the directory are processed:

```bash
decoct compress ./configs/ --schema docker-compose --stats
```

You can also list multiple files explicitly:

```bash
decoct compress service-a.yaml service-b.yaml --schema docker-compose --stats
```

---

## 11. Pipe kubectl Output Through decoct

Get all resources from a namespace and compress in one shot:

```bash
kubectl get all -n production -o yaml | decoct compress --schema kubernetes
```

decoct reads from stdin when no files are given. The bundled `kubernetes` schema handles Deployments, Services, ConfigMaps, and other common resource types.

For a specific resource type:

```bash
kubectl get configmaps -n production -o yaml | decoct compress --schema kubernetes --stats
```

Save compressed output for later reference:

```bash
kubectl get deployment,service -n production -o yaml \
  | decoct compress --schema kubernetes -o cluster-snapshot.yaml --stats
```

Combine with assertions for standards review:

```bash
kubectl get deployments -o yaml \
  | decoct compress --schema kubernetes --assertions k8s-standards.yaml
```

---

## 12. Compare Compressed vs Uncompressed Token Counts

Use `--stats-only` to measure savings at each compression tier without producing YAML output.

**Tier 1 -- Generic cleanup** (secrets + comments only, no schema):

```bash
decoct compress config.yaml --stats-only
```

```
Tokens: 487 -> 412 (saved 75, 15.4%)
```

**Tier 2 -- Platform defaults** (add a schema):

```bash
decoct compress config.yaml --schema docker-compose --stats-only
```

```
Tokens: 487 -> 268 (saved 219, 45.0%)
```

**Tier 3 -- Standards conformance** (add a profile with assertions):

```bash
decoct compress config.yaml --profile docker-compose --stats-only
```

```
Tokens: 487 -> 195 (saved 292, 59.9%)
```

This progression shows how each tier adds incremental savings. Tier 1 is always safe (no config knowledge needed). Tier 2 requires platform awareness. Tier 3 requires your team's design standards.

---

## 13. Integrate decoct into an MCP Tool Server

Use decoct as a library inside an MCP (Model Context Protocol) tool server so LLM agents can compress configs on demand.

```python
from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML

from decoct.passes.strip_comments import StripCommentsPass
from decoct.passes.strip_defaults import StripDefaultsPass
from decoct.passes.strip_secrets import StripSecretsPass
from decoct.passes.emit_classes import EmitClassesPass
from decoct.passes.prune_empty import PruneEmptyPass
from decoct.pipeline import Pipeline
from decoct.schemas.loader import load_schema
from decoct.schemas.resolver import resolve_schema
from decoct.tokens import create_report, format_report


def compress_config(yaml_text: str, schema_name: str = "docker-compose") -> dict:
    """Compress a YAML config string and return result with stats.

    This function can be exposed as an MCP tool.
    """
    # Parse input
    yaml = YAML(typ="rt")
    doc = yaml.load(yaml_text)

    # Load bundled schema by short name
    schema = load_schema(resolve_schema(schema_name))

    # Build pipeline
    pipeline = Pipeline([
        StripSecretsPass(),
        StripCommentsPass(),
        StripDefaultsPass(schema=schema),
        EmitClassesPass(schema=schema),
        PruneEmptyPass(),
    ])

    # Run compression
    stats = pipeline.run(doc)

    # Serialize output
    stream = StringIO()
    yaml.dump(doc, stream)
    output_text = stream.getvalue()

    # Token report
    report = create_report(yaml_text, output_text)

    return {
        "compressed_yaml": output_text,
        "input_tokens": report.input_tokens,
        "output_tokens": report.output_tokens,
        "savings_pct": f"{report.savings_pct:.1f}%",
        "passes_run": [r.name for r in stats.pass_results],
    }
```

Register this function with your MCP framework. The function accepts raw YAML text and a bundled schema name, and returns a dict with compressed output and statistics.

**Available bundled schema names:** `docker-compose`, `kubernetes`, `terraform-state`, `ansible-playbook`, `github-actions`, `gitlab-ci`, `prometheus`, `grafana`, `traefik`, `cloud-init`, `postgresql`, `redis`, `mongodb`, `mariadb-mysql`, `kafka`, `fluent-bit`, `opentelemetry-collector`, `argocd`, `keycloak`, `entra-id`, `intune`, `azure-arm`, `aws-cloudformation`, `gcp-resources`, `sshd-config`.

---

## 14. Use decoct as a Python Library

### Basic: Run Individual Passes

```python
from pathlib import Path

from ruamel.yaml import YAML

from decoct.assertions.loader import load_assertions
from decoct.passes.annotate_deviations import annotate_deviations
from decoct.passes.deviation_summary import deviation_summary
from decoct.passes.strip_conformant import strip_conformant
from decoct.passes.strip_defaults import strip_defaults
from decoct.passes.strip_secrets import strip_secrets
from decoct.schemas.loader import load_schema
from decoct.schemas.resolver import resolve_schema
from decoct.tokens import create_report, format_report

# Load input
yaml = YAML(typ="rt")
with open("docker-compose.yaml") as f:
    input_text = f.read()
doc = yaml.load(input_text)

# Always strip secrets first
audit = strip_secrets(doc)
print(f"Redacted {len(audit)} secrets")

# Strip platform defaults
schema = load_schema(resolve_schema("docker-compose"))
removed = strip_defaults(doc, schema)
print(f"Stripped {removed} defaults")

# Evaluate against assertions
assertions = load_assertions(Path("team-standards.yaml"))
stripped = strip_conformant(doc, assertions)
print(f"Stripped {stripped} conformant values")

deviations = annotate_deviations(doc, assertions)
print(f"Annotated {len(deviations)} deviations")

summary_lines = deviation_summary(doc, assertions)
print(f"Added {len(summary_lines)} summary lines")

# Serialize and measure
from io import StringIO
stream = StringIO()
yaml.dump(doc, stream)
output_text = stream.getvalue()

report = create_report(input_text, output_text)
print(format_report(report))
# Tokens: 487 -> 195 (saved 292, 59.9%)
```

### Pipeline: Compose Passes Declaratively

```python
from io import StringIO

from ruamel.yaml import YAML

from decoct.assertions.loader import load_assertions
from decoct.passes.annotate_deviations import AnnotateDeviationsPass
from decoct.passes.deviation_summary import DeviationSummaryPass
from decoct.passes.emit_classes import EmitClassesPass
from decoct.passes.prune_empty import PruneEmptyPass
from decoct.passes.strip_comments import StripCommentsPass
from decoct.passes.strip_conformant import StripConformantPass
from decoct.passes.strip_defaults import StripDefaultsPass
from decoct.passes.strip_secrets import StripSecretsPass
from decoct.pipeline import Pipeline
from decoct.schemas.loader import load_schema
from decoct.schemas.resolver import resolve_schema
from decoct.tokens import create_report, format_report

# Load schema and assertions
schema = load_schema(resolve_schema("docker-compose"))
assertions = load_assertions("team-standards.yaml")

# Build pipeline -- pass ordering is resolved automatically via
# run_after/run_before constraints declared on each pass class
pipeline = Pipeline([
    StripSecretsPass(),
    StripCommentsPass(),
    StripDefaultsPass(schema=schema),
    EmitClassesPass(schema=schema),
    StripConformantPass(assertions=assertions),
    AnnotateDeviationsPass(assertions=assertions),
    DeviationSummaryPass(assertions=assertions),
    PruneEmptyPass(),
])

# Load and process
yaml = YAML(typ="rt")
with open("docker-compose.yaml") as f:
    input_text = f.read()
doc = yaml.load(input_text)

stats = pipeline.run(doc)

# doc is now modified in-place
stream = StringIO()
yaml.dump(doc, stream)
output_text = stream.getvalue()

# Per-pass statistics
for result in stats.pass_results:
    timing = stats.pass_timings.get(result.name, 0)
    print(f"{result.name}: removed {result.items_removed} items ({timing:.3f}s)")
    for detail in result.details:
        print(f"  {detail}")

print(f"\nTotal pipeline time: {stats.total_time:.3f}s")

# Token report
report = create_report(input_text, output_text)
print(format_report(report))
```

### Token Counting Only

```python
from decoct.tokens import count_tokens

text = open("big-config.yaml").read()

# Default encoding (cl100k_base, used by GPT-4 and Claude)
tokens = count_tokens(text)
print(f"{tokens} tokens (cl100k_base)")

# GPT-4o encoding
tokens_4o = count_tokens(text, encoding="o200k_base")
print(f"{tokens_4o} tokens (o200k_base)")
```
