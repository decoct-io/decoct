# decoct — Development Plan

---

## Phases

1. **Foundation + Core Pipeline** — repo, packaging, data formats, deterministic passes, strip-secrets, token counting, CLI
2. **LLM Integration** — LLM client, direct compression, learning phase (schemas from corpus, assertions from docs), resolution/fallback
3. **Scaffolding + Assertions** — scaffolding pack format, interview mechanism, assertion preparation workflow, validation against fixtures
4. **Classes + Reconstitution** — class emitter, class resolver, inheritance, `--emit-class` flag
5. **Adapters** — JSON Schema adapter, LLM-learned adapter, adapter interface for community
6. **Benchmarks + Eval** — corpus collection, token benchmarks, LLM comprehension harness, published results
7. **Polish + Release** — README, docs site, PyPI publish, example assertions/scaffolding packs

---

## Phase 1: Foundation + Core Pipeline

### 1.1 Project Skeleton

- [ ] GitHub repo (`decoct-io/decoct`), MIT licence, `.gitignore`, `pyproject.toml`
- [ ] Package structure: `src/decoct/` with `__init__.py`, version
- [ ] Dependencies: `ruamel.yaml`, `tiktoken`, `click`
- [ ] Dev dependencies: `pytest`, `ruff`, `mypy`
- [ ] CLI entry point: `decoct` command with `compress` subcommand (stub)
- [ ] CI: GitHub Actions for lint + test on push

### 1.2 Internal Data Formats

- [ ] Schema internal format: dataclass/Pydantic model — `platform`, `source`, `confidence`, `defaults` dict, `drop_patterns` list, `system_managed` list
- [ ] Assertion format: dataclass/Pydantic model — `id`, `assert`, `match` (optional), `rationale`, `severity`, `exceptions`
- [ ] Assertion file loader: read YAML assertion files, validate structure, return typed objects
- [ ] Schema file loader: read YAML schema files, validate, return typed objects
- [ ] Profile format: named bundle of schema ref + assertion refs + pass config

### 1.3 Token Counting

- [ ] `tokens.py`: count tokens for a string/file using tiktoken
- [ ] Support `cl100k_base` (default) and `o200k_base` (configurable)
- [ ] Report dataclass: `input_tokens`, `output_tokens`, `savings_tokens`, `savings_pct`
- [ ] CLI `--stats` and `--stats-only` flags

### 1.4 Strip-Secrets Pass

- [ ] Entropy detector: flag strings above configurable entropy threshold
- [ ] Regex pattern library: AWS keys, Azure connection strings, `password=`, `secret=`, bearer tokens, base64 private keys, common API key formats
- [ ] Path-based rules: configurable list of always-strip paths (`*.env.*`, `*.secret`, `*.credentials`, `*.password`)
- [ ] Replacement: swap detected secrets with `[REDACTED]`
- [ ] Audit log: record what was stripped (path + detection method, never the value)
- [ ] Tests: fixture YAML files with embedded secrets, verify all caught, verify non-secrets preserved

### 1.5 Pipeline Framework

- [ ] Pass base class: `run(doc) -> doc`, ordering declarations (`run_after`, `run_before`)
- [ ] Pipeline builder: accept list of passes, validate ordering constraints, construct execution chain
- [ ] Pass registry: register passes by name, look up by string
- [ ] Pipeline runner: execute passes in order, collect timing/stats per pass

### 1.6 Generic Passes

- [ ] `strip-comments`: walk ruamel.yaml AST, remove comment tokens
- [ ] `drop-fields`: accept glob patterns, walk tree, prune matching paths
- [ ] `keep-fields`: inverse — retain only matching paths, prune everything else
- [ ] Tests for each: fixture YAML in, expected YAML out

### 1.7 Schema-Aware Pass

- [ ] `strip-defaults`: accept a loaded schema, walk tree, remove values matching `defaults` dict
- [ ] Path matching: support `*` wildcard in path segments (`services.*.restart`)
- [ ] Confidence-aware: optionally skip low-confidence defaults (annotate instead of strip)
- [ ] `drop-fields` integration: also drop paths matching schema's `drop_patterns` and `system_managed`
- [ ] Tests: fixture YAML + fixture schema, verify correct stripping

### 1.8 Assertion-Aware Passes

- [ ] `strip-conformant`: accept loaded assertions, walk tree, remove values matching `must` assertions with `match` conditions
- [ ] `annotate-deviations`: where values violate assertions, insert `# [!] standard: ...` comments
- [ ] `deviation-summary`: generate preamble comment block listing all deviations with assertion IDs
- [ ] Match evaluator: handle `value`, `pattern`, `range`, `contains`, `not_value` match types
- [ ] Assertions without `match`: skip in deterministic passes (these are LLM-context only)
- [ ] Tests: fixture YAML + fixture assertions, verify stripping/annotation/summary

### 1.9 CLI Integration

- [ ] `decoct compress <files>` — run pipeline, print compressed YAML + stats
- [ ] `--schema <path>` — load schema file
- [ ] `--assertions <path>` — load assertions file
- [ ] `--profile <path>` — load profile (schema + assertions + pass config)
- [ ] `--stats` / `--stats-only` — token reporting
- [ ] `--show-removed` — output what was stripped and why
- [ ] `--output <path>` / stdout default
- [ ] Stdin support: `cat file.yaml | decoct compress`

---

## Phase 2-7: Deferred

Structured at first level only. Items and deliverables to be broken down when Phase 1 nears completion.

---

## Detailed Breakdown: 1.1 Project Skeleton

This is the first thing to build. Everything else depends on it.

### Deliverables

**1.1.1 — GitHub repository**

Create `decoct-io/decoct` on GitHub:

```
decoct/
├── .github/
│   └── workflows/
│       └── ci.yaml          # lint + test on push/PR
├── .gitignore
├── LICENSE                   # MIT
├── README.md                 # minimal — name, one-liner, "under development"
├── pyproject.toml
└── src/
    └── decoct/
        ├── __init__.py       # __version__ = "0.1.0-dev"
        └── cli.py            # click group + compress stub
```

**1.1.2 — `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "decoct"
version = "0.1.0.dev0"
description = "Infrastructure context compression for LLMs"
readme = "README.md"
license = "MIT"
requires-python = ">=3.10"
authors = [
    { name = "Enable Network Services", email = "dev@enable.network" },
]
keywords = ["llm", "yaml", "infrastructure", "context", "compression"]
classifiers = [
    "Development Status :: 2 - Pre-Alpha",
    "Intended Audience :: System Administrators",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Topic :: System :: Systems Administration",
]
dependencies = [
    "ruamel.yaml>=0.18",
    "tiktoken>=0.7",
    "click>=8.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov",
    "ruff>=0.8",
    "mypy>=1.0",
]
llm = [
    "anthropic>=0.40",
]

[project.scripts]
decoct = "decoct.cli:cli"

[project.urls]
Homepage = "https://decoct.io"
Repository = "https://github.com/decoct-io/decoct"
Documentation = "https://decoct.io/docs"
Issues = "https://github.com/decoct-io/decoct/issues"

[tool.ruff]
line-length = 120
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.mypy]
python_version = "3.10"
strict = true
```

Note: LLM dependencies (`anthropic`) are optional — the core pipeline works without them. Install with `pip install decoct[llm]` when LLM features are needed.

**1.1.3 — CLI entry point**

```python
# src/decoct/cli.py
import click

@click.group()
@click.version_option()
def cli():
    """decoct — infrastructure context compression for LLMs."""
    pass

@cli.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--schema", type=click.Path(exists=True), help="Schema file")
@click.option("--assertions", type=click.Path(exists=True), help="Assertions file")
@click.option("--profile", type=click.Path(exists=True), help="Profile file")
@click.option("--stats", is_flag=True, help="Show token statistics")
@click.option("--stats-only", is_flag=True, help="Show only token statistics")
@click.option("--show-removed", is_flag=True, help="Show what was stripped")
@click.option("--output", "-o", type=click.Path(), help="Output file")
def compress(files, schema, assertions, profile, stats, stats_only, show_removed, output):
    """Compress infrastructure data for LLM context windows."""
    click.echo("decoct compress: not yet implemented", err=True)
    raise SystemExit(1)
```

**1.1.4 — CI workflow**

```yaml
# .github/workflows/ci.yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: ruff check src/ tests/
      - run: pytest --cov=decoct
```

**1.1.5 — Minimal README**

```markdown
# decoct

Infrastructure context compression for LLMs.

> **Status: Under active development.** Not yet ready for production use.

decoct compresses infrastructure data for LLM context windows — stripping
platform defaults, removing noise, and highlighting deviations from your
design standards. Typically saves 40-60% of tokens while making the output
more informative, not less.

## Install

```
pip install decoct
```

## Documentation

Coming soon at [decoct.io](https://decoct.io).

## Licence

MIT
```

**1.1.6 — First test**

```python
# tests/test_cli.py
from click.testing import CliRunner
from decoct.cli import cli

def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output

def test_compress_no_args():
    runner = CliRunner()
    result = runner.invoke(cli, ["compress"])
    # Should exit with error or usage, not crash
    assert result.exit_code != 0 or "not yet implemented" in result.output
```

### Definition of Done

- [ ] Repo exists on GitHub with all files above
- [ ] `pip install -e ".[dev]"` succeeds
- [ ] `decoct --version` prints version
- [ ] `decoct compress` prints stub message
- [ ] `ruff check` passes
- [ ] `pytest` passes (2 tests)
- [ ] CI green on push
- [ ] PyPI placeholder published (`0.1.0.dev0`) to reserve the name

### Time Estimate

Half a day. This is intentionally trivial — the point is to have a working repo with CI before writing any real code.

### What Comes Next

After 1.1, the natural sequence is:

**1.2 Internal Data Formats** → defines the core types everything else operates on
**1.3 Token Counting** → needed to measure everything from this point forward
**1.4 Strip-Secrets** → safety-critical, must exist before any LLM integration
**1.5 Pipeline Framework** → the orchestration layer that all passes plug into
**1.6 Generic Passes** → first real compression (strip-comments, drop-fields)
**1.7 Schema-Aware Pass** → first "intelligent" compression using platform defaults
**1.8 Assertion-Aware Passes** → the headline feature
**1.9 CLI Integration** → wire it all together

Each item is independently testable. Each produces a working increment. The pipeline framework (1.5) is the integration point where individual passes start composing into something useful.
