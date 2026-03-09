# Integration Guide

decoct is designed to fit into existing infrastructure workflows. This guide covers CI/CD pipelines, pre-commit hooks, shell pipelines, MCP tool servers, and direct Python library usage.

## CI/CD Integration

### GitHub Actions

A minimal workflow step that compresses configuration files and reports token savings:

```yaml
- name: Compress configs
  run: |
    pip install decoct
    decoct compress ./configs/ --recursive --profile docker-compose --stats-only
```

A full workflow that validates configuration conformance by checking for deviations from design standards. The `--show-removed` flag surfaces exactly which values deviate, and `--stats` reports token savings:

```yaml
name: Config Conformance Check
on:
  pull_request:
    paths:
      - '*.yaml'
      - '*.yml'
      - 'configs/**'

jobs:
  config-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install decoct
        run: pip install decoct

      - name: Check config conformance
        run: |
          decoct compress configs/ \
            --recursive \
            --schema docker-compose \
            --assertions assertions/docker-services.yaml \
            --stats \
            --show-removed

      - name: Compress for LLM context (artifact)
        run: |
          decoct compress configs/ \
            --recursive \
            --profile docker-compose \
            -o compressed-configs.yaml \
            --stats
        continue-on-error: true

      - name: Upload compressed configs
        uses: actions/upload-artifact@v4
        with:
          name: compressed-configs
          path: compressed-configs.yaml
```

### GitLab CI

```yaml
config-check:
  image: python:3.12-slim
  stage: validate
  script:
    - pip install decoct
    - decoct compress docker-compose.yml --profile docker-compose --stats --show-removed
  rules:
    - changes:
        - docker-compose.yml
        - configs/**/*.yaml
```

To fail the pipeline when deviations exceed a threshold, capture the stats output and parse it:

```yaml
config-conformance:
  image: python:3.12-slim
  stage: validate
  script:
    - pip install decoct
    - |
      decoct compress docker-compose.yml \
        --schema docker-compose \
        --assertions assertions/docker-services.yaml \
        --stats-only 2>&1 | tee /tmp/stats.txt
    - echo "Config conformance check complete. Review stats above."
```

## Pre-Commit Hook

### Using pre-commit framework

Add this to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: decoct-secrets
        name: Check for secrets in configs
        entry: bash -c 'for f in "$@"; do decoct compress "$f" --stats-only 2>&1; done'
        language: system
        files: '\.(yaml|yml|json)$'
        additional_dependencies: ['decoct']
```

### Shell script hook

Save as `.git/hooks/pre-commit` and make it executable (`chmod +x`):

```bash
#!/usr/bin/env bash
set -e

# Find staged YAML/JSON config files
staged_configs=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\.(yaml|yml|json)$' || true)

if [ -z "$staged_configs" ]; then
    exit 0
fi

echo "Running decoct secret check on staged config files..."

for file in $staged_configs; do
    # Run decoct and check if secrets were redacted
    output=$(decoct compress "$file" --show-removed 2>&1 1>/dev/null)
    if echo "$output" | grep -q "strip-secrets"; then
        echo "WARNING: Potential secrets detected in $file"
        echo "$output" | grep -A5 "strip-secrets" >&2
        echo "Review the file before committing."
        exit 1
    fi
done

echo "No secrets detected in config files."
```

## Shell Pipeline Integration

decoct reads from stdin when no file arguments are given, so it integrates naturally with shell pipelines. Platform auto-detection works on piped content as well.

### Kubernetes

```bash
# Compress a single deployment
kubectl get deployment myapp -o yaml | decoct compress --schema kubernetes

# Compress all deployments in a namespace
kubectl get deployments -o yaml | decoct compress --schema kubernetes --stats

# Compress and save for LLM context
kubectl get deployment myapp -o yaml | decoct compress --schema kubernetes -o myapp-compressed.yaml
```

### Terraform

```bash
# Compress Terraform state for LLM analysis
terraform show -json | decoct compress --schema terraform-state

# Compress plan output
terraform show -json tfplan | decoct compress --stats
```

### Docker

```bash
# Compress docker inspect output
docker inspect mycontainer | decoct compress

# Compress docker compose config
docker compose config | decoct compress --schema docker-compose --stats
```

### Ansible

```bash
# Compress inventory
ansible-inventory --list | decoct compress

# Compress a playbook
decoct compress playbook.yaml --schema ansible-playbook --stats
```

### Cloud Init

```bash
# Compress cloud-init config
decoct compress cloud-init.yaml --schema cloud-init

# Pipe from a cloud provider metadata endpoint
curl -s http://169.254.169.254/latest/user-data | decoct compress --schema cloud-init
```

### Chaining with other tools

```bash
# Compress then count tokens with a different tool
kubectl get deployment myapp -o yaml | decoct compress --schema kubernetes | wc -c

# Compress and pipe to an LLM CLI
decoct compress k8s-manifest.yaml --schema kubernetes | llm "Review this Kubernetes deployment"

# Diff original vs compressed
diff <(cat docker-compose.yaml) <(decoct compress docker-compose.yaml --schema docker-compose)
```

## MCP Tool Server Integration

decoct can be exposed as an MCP (Model Context Protocol) tool, allowing LLM agents to compress infrastructure data before inserting it into their context window.

```python
# Conceptual example — expose decoct as an MCP tool
from io import StringIO

from ruamel.yaml import YAML

from decoct.pipeline import Pipeline
from decoct.passes.strip_secrets import StripSecretsPass
from decoct.passes.strip_comments import StripCommentsPass
from decoct.passes.strip_defaults import StripDefaultsPass
from decoct.passes.prune_empty import PruneEmptyPass
from decoct.schemas.loader import load_schema
from decoct.schemas.resolver import resolve_schema
from decoct.tokens import create_report


def compress_config(yaml_text: str, schema_name: str | None = None) -> dict:
    """Compress infrastructure YAML for LLM context.

    Args:
        yaml_text: Raw YAML or JSON string to compress.
        schema_name: Optional bundled schema name (e.g. 'kubernetes',
            'docker-compose'). Enables platform-default stripping.

    Returns:
        Dict with 'compressed' (YAML string), 'input_tokens', 'output_tokens',
        and 'savings_pct'.
    """
    yaml = YAML(typ="rt")
    doc = yaml.load(yaml_text)

    passes = [
        StripSecretsPass(),
        StripCommentsPass(),
    ]

    if schema_name:
        schema = load_schema(resolve_schema(schema_name))
        passes.append(StripDefaultsPass(schema=schema))

    passes.append(PruneEmptyPass())

    pipeline = Pipeline(passes)
    pipeline.run(doc)

    stream = StringIO()
    yaml.dump(doc, stream)
    compressed = stream.getvalue()

    report = create_report(yaml_text, compressed)

    return {
        "compressed": compressed,
        "input_tokens": report.input_tokens,
        "output_tokens": report.output_tokens,
        "savings_pct": round(report.savings_pct, 1),
    }
```

Register this function with your MCP server framework. The function handles secret redaction automatically, so it is safe to pass untrusted configuration data.

## Python Library Integration

### Quick compression

Load a file, run the pipeline, and dump the result:

```python
from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML

from decoct.formats import load_input, detect_platform
from decoct.pipeline import Pipeline
from decoct.passes.strip_secrets import StripSecretsPass
from decoct.passes.strip_comments import StripCommentsPass
from decoct.passes.strip_defaults import StripDefaultsPass
from decoct.passes.prune_empty import PruneEmptyPass
from decoct.schemas.loader import load_schema
from decoct.schemas.resolver import resolve_schema
from decoct.tokens import create_report

# Load input (auto-detects JSON, YAML, or INI format)
doc, raw_text = load_input(Path("docker-compose.yaml"))

# Auto-detect the platform from document structure
platform = detect_platform(doc)

# Build pipeline
passes = [StripSecretsPass(), StripCommentsPass()]
if platform:
    schema = load_schema(resolve_schema(platform))
    passes.append(StripDefaultsPass(schema=schema))
passes.append(PruneEmptyPass())

pipeline = Pipeline(passes)
stats = pipeline.run(doc)

# Dump compressed output
yaml = YAML(typ="rt")
stream = StringIO()
yaml.dump(doc, stream)
compressed = stream.getvalue()

# Report token savings
report = create_report(raw_text, compressed)
print(f"Tokens: {report.input_tokens} -> {report.output_tokens} "
      f"(saved {report.savings_pct:.1f}%)")
```

### Custom pass selection

Choose exactly which passes to run:

```python
from decoct.pipeline import Pipeline
from decoct.passes.strip_secrets import StripSecretsPass
from decoct.passes.strip_defaults import StripDefaultsPass
from decoct.passes.drop_fields import DropFieldsPass
from decoct.passes.keep_fields import KeepFieldsPass
from decoct.schemas.loader import load_schema
from decoct.schemas.resolver import resolve_schema

schema = load_schema(resolve_schema("kubernetes"))

# Only strip secrets, remove defaults, and drop specific fields
pipeline = Pipeline([
    StripSecretsPass(),
    StripDefaultsPass(schema=schema),
    DropFieldsPass(patterns=["**.managedFields", "**.uid", "**.resourceVersion"]),
])
```

Or keep only the fields you care about:

```python
pipeline = Pipeline([
    StripSecretsPass(),
    KeepFieldsPass(patterns=[
        "metadata.name",
        "metadata.namespace",
        "spec.containers.*.image",
        "spec.containers.*.resources",
    ]),
])
```

### Getting statistics

The `pipeline.run()` method returns a `PipelineStats` object with per-pass results and timing:

```python
stats = pipeline.run(doc)

for result in stats.pass_results:
    print(f"{result.name}: removed {result.items_removed} items")
    for detail in result.details:
        print(f"  {detail}")

print(f"Total pipeline time: {stats.total_time:.3f}s")
for name, elapsed in stats.pass_timings.items():
    print(f"  {name}: {elapsed:.3f}s")
```

### Using assertions for conformance checking

```python
from decoct.pipeline import Pipeline
from decoct.passes.strip_secrets import StripSecretsPass
from decoct.passes.strip_conformant import StripConformantPass
from decoct.passes.annotate_deviations import AnnotateDeviationsPass
from decoct.passes.deviation_summary import DeviationSummaryPass
from decoct.assertions.loader import load_assertions

assertions = load_assertions("assertions/docker-services.yaml")

pipeline = Pipeline([
    StripSecretsPass(),
    StripConformantPass(assertions=assertions),
    AnnotateDeviationsPass(assertions=assertions),
    DeviationSummaryPass(assertions=assertions),
])

stats = pipeline.run(doc)

# The doc now has:
# - Conformant values removed
# - Deviating values annotated with # [!] comments
# - A summary block at the top listing all deviations
```

### Using profiles

Profiles bundle schema, assertions, and pass configuration into a single file:

```python
from decoct.profiles.loader import load_profile
from decoct.profiles.resolver import resolve_profile
from decoct.schemas.loader import load_schema
from decoct.assertions.loader import load_assertions

resolved_path = resolve_profile("docker-compose")
profile = load_profile(resolved_path)

# Access profile fields
print(f"Profile: {profile.name}")
print(f"Schema ref: {profile.schema_ref}")
print(f"Assertion refs: {profile.assertion_refs}")
print(f"Passes: {list(profile.passes.keys())}")
```

## Caching and Performance

decoct is fully deterministic: the same input combined with the same schema and assertions always produces the same output. This property makes it straightforward to cache results.

**Cache compressed output alongside source configs.** Since the output is deterministic, you can skip recompression when the input file, schema, and assertions have not changed. Use file modification timestamps or content hashes as cache keys.

**Schema and assertion loading is cheap.** These files are small YAML documents parsed once at startup. The dominant cost in a pipeline run is YAML parsing and tree traversal of the input document.

**For batch processing, use directory mode.** The CLI accepts directories as input and the `--recursive` flag walks subdirectories:

```bash
decoct compress ./configs/ --recursive --schema kubernetes --stats-only
```

This is more efficient than invoking decoct separately for each file, since schema and assertion loading happens once.

**Token counting adds minimal overhead.** The `--stats` flag uses tiktoken to count tokens before and after compression. This is a fast operation compared to YAML parsing, so there is little reason to skip it.

**Pipeline construction is lightweight.** If you are integrating decoct as a library in a long-running process, you can construct the `Pipeline` once and call `run()` on each document. The pipeline object is reusable:

```python
from decoct.pipeline import Pipeline
from decoct.passes.strip_secrets import StripSecretsPass
from decoct.passes.strip_defaults import StripDefaultsPass
from decoct.schemas.loader import load_schema
from decoct.schemas.resolver import resolve_schema

schema = load_schema(resolve_schema("kubernetes"))
pipeline = Pipeline([
    StripSecretsPass(),
    StripDefaultsPass(schema=schema),
])

# Reuse pipeline across multiple documents
for doc in documents:
    stats = pipeline.run(doc)
```
