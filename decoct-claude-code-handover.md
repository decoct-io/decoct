# decoct — Claude Code Handover

## What is decoct?

decoct is an open source LLM-powered infrastructure context compression system. It ingests diverse infrastructure data (JSON, XML, YAML, CLI output, prose documentation), normalises it, and produces optimised YAML for LLM context windows — stripping platform defaults, removing noise, and highlighting deviations from design standards.

Repository: https://github.com/decoct-io/decoct
Package: `decoct` on PyPI (not yet published — reserve with first release)
Licence: MIT
Domain: decoct.io

## Architecture (three phases)

**Phase A: Assertion Preparation.** Design standards/conventions are transformed into structured, machine-evaluable assertions. An LLM reads documentation through domain-specific scaffolding packs (reusable expert knowledge) and produces candidate assertions. Humans review and commit.

**Phase B: Schema Preparation.** Platform defaults extracted from best available source — authoritative vendor schemas via adapters (YANG, OpenAPI, JSON Schema, ADMX, Augeas) where they exist, LLM-learned from corpus analysis where they don't. All adapters produce the same internal schema format.

**Phase C: Deterministic Processing.** Pipeline applies assertions and schemas as tree transformations. Strip-secrets runs first (before any LLM contact). Falls back to LLM for ambiguity resolution, caching answers. Stripped values recorded in class definitions for reconstitution.

## Three compression tiers

1. Generic cleanup (strip comments, drop fields) → ~15% savings
2. Platform defaults (schema-aware stripping) → ~45% cumulative
3. Standards conformance (assertion-aware stripping + deviation annotation) → ~60% cumulative

## Current state

The repo exists at `decoct-io/decoct` with an MIT licence file and nothing else. The project skeleton needs to be created as the first deliverable.

## Development plan — Phase 1: Foundation + Core Pipeline

Complete these items in order. Each is independently testable.

### 1.1 Project Skeleton
- `pyproject.toml` — hatchling build, dependencies: ruamel.yaml>=0.18, tiktoken>=0.7, click>=8.0. Dev deps: pytest>=8.0, pytest-cov, ruff>=0.8, mypy>=1.0. Optional `[llm]` extra: anthropic>=0.40. Entry point: `decoct = "decoct.cli:cli"`
- `src/decoct/__init__.py` — version 0.1.0.dev0
- `src/decoct/cli.py` — click group with `compress` subcommand (stub). Options: `--schema`, `--assertions`, `--profile`, `--stats`, `--stats-only`, `--show-removed`, `--output/-o`. Accepts files as arguments. Stdin support.
- `src/decoct/py.typed` — marker for mypy
- `.gitignore` — Python standard + `.decoct/`
- `.github/workflows/ci.yaml` — lint + test on push/PR, Python 3.10-3.13 matrix
- `tests/test_cli.py` — test version, help, compress stub
- `README.md` — minimal: name, one-liner, status badge, install, link to decoct.io

### 1.2 Internal Data Formats
- Schema internal format: dataclass or Pydantic model — fields: `platform` (str), `source` (str), `confidence` (Literal["authoritative", "high", "medium", "low"]), `defaults` (dict of dotted-path → value), `drop_patterns` (list of glob strings), `system_managed` (list of glob strings)
- Assertion format: dataclass or Pydantic model — fields: `id` (str), `assert_` (str, maps from YAML key `assert`), `match` (optional Match object with path + value/pattern/range/contains/not_value), `rationale` (str), `severity` (Literal["must", "should", "may"]), `exceptions` (optional str), `example` (optional str), `related` (optional list of str), `source` (optional str)
- Assertion file loader: read YAML, validate structure, return list of typed assertion objects
- Schema file loader: read YAML, validate, return typed schema object
- Profile format: dataclass with schema_ref (path), assertion_refs (list of paths), pass config
- Profile loader
- Tests with fixture files for each

### 1.3 Token Counting
- `src/decoct/tokens.py` — count tokens for string/file using tiktoken
- Support cl100k_base (default) and o200k_base (configurable via option)
- Report dataclass: input_tokens, output_tokens, savings_tokens, savings_pct
- Wire `--stats` and `--stats-only` into CLI
- Tests

### 1.4 Strip-Secrets Pass
- Entropy detector: flag strings above configurable Shannon entropy threshold (default ~4.5 for strings >16 chars)
- Regex pattern library: AWS access keys (`AKIA...`), Azure connection strings, `password=`, `secret=`, `token=`, bearer tokens, base64 private keys (BEGIN PRIVATE KEY), common API key formats, UUIDs in credential-like paths
- Path-based rules: configurable always-strip paths — `*.env.*`, `*.secret`, `*.secrets`, `*.credentials`, `*.password`, `*.private_key`, `*.api_key`, `*.connection_string`
- Replacement: swap matched values with `[REDACTED]`
- Audit log: list of (path, detection_method) tuples — never log the value itself
- This pass MUST run before any LLM contact — it is the first pass after normalisation in the pipeline
- Tests: fixture YAML with embedded secrets of each type, verify all caught, verify non-secrets preserved (IP addresses, hostnames, non-secret base64, etc.)

### 1.5 Pipeline Framework
- Pass base class: `run(doc: CommentedMap) -> CommentedMap`, class-level `run_after: list[str]` and `run_before: list[str]` for ordering
- Pipeline builder: accepts list of pass names/instances, validates ordering constraints (topological sort), raises on cycles or conflicts
- Pass registry: decorator-based registration, lookup by string name
- Pipeline runner: executes passes in order, collects per-pass timing and stats (tokens before/after each pass)
- Tests: ordering validation, registry, mock passes

### 1.6 Generic Passes
- `strip-comments`: walk ruamel.yaml CommentedMap/CommentedSeq, remove all comment tokens
- `drop-fields`: accept list of glob patterns (e.g. `metadata.managedFields`, `**.uuid`), walk tree, prune matching paths. `**` matches any depth. `*` matches single segment.
- `keep-fields`: inverse — retain only paths matching patterns, prune everything else
- Register all in pass registry
- Tests: fixture YAML in → expected YAML out for each pass

### 1.7 Schema-Aware Pass
- `strip-defaults`: load schema, walk YAML tree, for each leaf check if path matches a schema default entry and value equals the default — if so, remove
- Path matching with `*` wildcard in segments: `services.*.restart` matches `services.hairtrigger.restart`
- If schema has `confidence: low` or `medium`, optionally annotate instead of strip (controlled by CLI flag or profile setting)
- Also apply schema's `drop_patterns` and `system_managed` lists (functionally equivalent to drop-fields but sourced from schema)
- Register in pass registry with `run_after: ["strip-secrets", "strip-comments"]`
- Tests: fixture YAML + fixture schema → expected output

### 1.8 Assertion-Aware Passes
- `strip-conformant`: load assertions, for each assertion with a `match` field and severity `must`, evaluate match against YAML tree. If value matches (conformant), strip it. Skip assertions without `match` (those are LLM-context only).
- `annotate-deviations`: for each assertion with `match`, if value exists and does NOT match, insert ruamel.yaml comment: `# [!] standard: {expected_value}` (or `# [!] assertion: {assertion.assert_}` for pattern/range matches)
- `deviation-summary`: collect all deviations, emit a comment block at document start: `# decoct: N deviations from standards` followed by one line per deviation with assertion ID
- Match evaluator supporting: `value` (equality), `pattern` (regex), `range` ([min, max] inclusive), `contains` (value in list), `not_value` (inequality)
- Register all with appropriate ordering: strip-conformant after strip-defaults, annotate-deviations after strip-conformant, deviation-summary last
- Tests: fixture YAML + fixture assertions → verify stripping, annotation placement, summary content

### 1.9 CLI Integration
- Wire all passes into `decoct compress`:
  - Load schema if `--schema` provided
  - Load assertions if `--assertions` provided  
  - Load profile if `--profile` provided (profile bundles schema + assertions + pass config)
  - Build pipeline from profile or defaults
  - Read input files (or stdin)
  - Run pipeline
  - Output compressed YAML to stdout or `--output`
  - Print stats if `--stats` or `--stats-only`
  - Print removed items if `--show-removed`
- `decoct assertions validate --assertions <path> --fixtures <dir>` — run assertions against fixture YAML, report matches/deviations/ambiguous
- Integration tests: end-to-end CLI invocations with fixture files

## Key design decisions

- **Assertions not rules.** The structured standards are called "assertions" throughout.
- **`match` is optional on assertions.** Assertions without `match` are loaded as LLM context, not machine-evaluated. No cross-field logic or AND/OR/IF in match — keep it simple, send complex conditions to the LLM.
- **strip-secrets is non-negotiable.** Runs before everything else, before any LLM contact. Entropy + regex + path patterns.
- **ruamel.yaml for round-trip.** Use CommentedMap/CommentedSeq throughout to preserve structure and enable comment insertion for annotations.
- **Scaffolding packs are versioned.** Manifest includes `version:` field, CLI supports `--domain pack@version` pinning.
- **Classes for reconstitution.** When values are stripped (defaults or conformant), they're recorded in a class definition that allows reconstruction. Class references appear as comments in output. Classes compose via inheritance (platform defaults + organisational assertions).
- **Diverse input, YAML output.** Phase 1 handles YAML and JSON input. XML and CLI output normalisation comes later.
- **LLM dependencies are optional.** `pip install decoct` gets the deterministic pipeline. `pip install decoct[llm]` adds Anthropic SDK for learning phase and LLM-direct compression.

## Tech stack

- Python 3.10+
- ruamel.yaml for YAML handling (round-trip preservation)
- tiktoken for token counting
- click for CLI
- pytest for testing
- ruff for linting
- hatchling for build

## File structure target (Phase 1 complete)

```
decoct/
├── .github/workflows/ci.yaml
├── .gitignore
├── LICENSE
├── README.md
├── pyproject.toml
├── src/decoct/
│   ├── __init__.py
│   ├── cli.py
│   ├── py.typed
│   ├── tokens.py
│   ├── pipeline.py
│   ├── passes/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── strip_secrets.py
│   │   ├── strip_comments.py
│   │   ├── drop_fields.py
│   │   ├── keep_fields.py
│   │   ├── strip_defaults.py
│   │   ├── strip_conformant.py
│   │   ├── annotate_deviations.py
│   │   └── deviation_summary.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── loader.py
│   │   └── models.py
│   ├── assertions/
│   │   ├── __init__.py
│   │   ├── loader.py
│   │   ├── matcher.py
│   │   └── models.py
│   └── profiles/
│       ├── __init__.py
│       └── loader.py
├── tests/
│   ├── __init__.py
│   ├── test_cli.py
│   ├── test_tokens.py
│   ├── test_pipeline.py
│   ├── test_passes/
│   │   ├── __init__.py
│   │   ├── test_strip_secrets.py
│   │   ├── test_strip_comments.py
│   │   ├── test_drop_fields.py
│   │   ├── test_keep_fields.py
│   │   ├── test_strip_defaults.py
│   │   ├── test_strip_conformant.py
│   │   ├── test_annotate_deviations.py
│   │   └── test_deviation_summary.py
│   ├── test_schemas.py
│   ├── test_assertions.py
│   └── fixtures/
│       ├── schemas/
│       ├── assertions/
│       └── yaml/
└── fixtures/              # shipped example assertions
    ├── assertions/
    │   ├── docker-services.yaml
    │   └── linux-hardening.yaml
    └── schemas/
        └── docker-compose.yaml
```

## Immediate next step

Start with item 1.1: create the project skeleton. The skeleton zip has already been generated — extract it into the repo, verify `pip install -e ".[dev]"` works, `decoct --version` runs, `pytest` passes, `ruff check` passes, then commit and push. CI should go green.

After that, proceed through 1.2 → 1.3 → 1.4 → 1.5 → 1.6 → 1.7 → 1.8 → 1.9 in order. Each item is independently testable and produces a working increment.

## Reference documents

The full project plan is in `decoct-plan.md` (attached or in the enable-infra repo). The development breakdown is in `decoct-dev-plan.md`.
