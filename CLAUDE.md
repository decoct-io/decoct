# CLAUDE.md — decoct

## What This Project Is

decoct is an open source Python library and CLI that compresses infrastructure data
(JSON, YAML, XML, CLI output) for LLM context windows — stripping platform defaults,
removing noise, and highlighting deviations from design standards. Targets 40-60%
token savings while making output more informative, not less.

**Repository:** `decoct-io/decoct` on GitHub
**Package:** `decoct` on PyPI (not yet published)
**Licence:** MIT
**Python:** 3.10+

## Architecture

Three-phase compression pipeline:

1. **Assertion Preparation** — design standards → structured, machine-evaluable assertions
2. **Schema Preparation** — platform defaults extracted from vendor schemas or LLM-learned
3. **Deterministic Processing** — pipeline applies assertions and schemas as tree transformations

Three compression tiers: generic cleanup (~15%), platform defaults (~45%), standards conformance (~60%).

## Tech Stack

- **ruamel.yaml** — round-trip YAML (CommentedMap/CommentedSeq throughout)
- **tiktoken** — token counting (cl100k_base default, o200k_base configurable)
- **click** — CLI framework
- **hatchling** — build system
- **pytest** / **ruff** / **mypy** — testing, linting, type checking

## Development Workflow

```bash
pip install -e ".[dev]"       # Install with dev dependencies
pytest --cov=decoct -v        # Run tests with coverage
ruff check src/ tests/        # Lint
mypy src/                     # Type check
decoct --version              # Verify CLI entry point
```

## Project Layout

```
src/decoct/
├── __init__.py          # version
├── cli.py               # click CLI (entry point: decoct.cli:cli)
├── py.typed             # mypy marker
├── tokens.py            # tiktoken wrapper
├── pipeline.py          # pass orchestration
├── passes/              # compression passes (strip-secrets, strip-defaults, etc.)
├── schemas/             # schema models + loader
├── assertions/          # assertion models + loader + matcher
└── profiles/            # profile models + loader
tests/
├── test_cli.py
├── test_passes/         # one test file per pass
├── fixtures/            # YAML fixtures for schemas, assertions, test inputs
```

## Conventions

- **src layout** — all package code under `src/decoct/`
- **Dataclasses over Pydantic** — keep core dependency-light; Pydantic only if justified
- **Type annotations everywhere** — mypy strict mode is on
- **ruamel.yaml round-trip** — use CommentedMap/CommentedSeq, never plain dict for YAML processing
- **Pass ordering** — strip-secrets always first; passes declare `run_after`/`run_before`
- **Tests per module** — every module has corresponding tests with YAML fixtures
- **LLM deps are optional** — `pip install decoct` = deterministic pipeline only; `pip install decoct[llm]` adds anthropic SDK
- **Line length 120** — ruff enforced
- **Assertions not rules** — the structured standards are called "assertions" throughout the codebase

## Key Design Decisions

- **strip-secrets is non-negotiable** — runs before everything else, before any LLM contact. Entropy + regex + path patterns. Values replaced with `[REDACTED]`.
- **`match` is optional on assertions** — assertions without `match` are LLM context only, not machine-evaluated. No complex cross-field logic in match.
- **Classes for reconstitution** — stripped values recorded in class definitions for reconstruction. Class references appear as comments in output.
- **Diverse input, YAML output** — Phase 1 handles YAML and JSON input. XML and CLI normalisation comes later.

## Development Plan

The project is built incrementally in 9 steps (Phase 1). See `decoct-dev-plan.md` for the full breakdown. Current progress:

- [x] 1.1 Project Skeleton
- [x] 1.2 Internal Data Formats (schemas, assertions, profiles)
- [x] 1.3 Token Counting
- [x] 1.4 Strip-Secrets Pass
- [x] 1.5 Pipeline Framework
- [x] 1.6 Generic Passes (strip-comments, drop-fields, keep-fields)
- [x] 1.7 Schema-Aware Pass (strip-defaults)
- [x] 1.8 Assertion-Aware Passes (strip-conformant, annotate-deviations)
- [x] 1.9 CLI Integration

Each step is independently testable. Proceed in order — later steps depend on earlier ones.

## What NOT to Do

- Never bypass strip-secrets ordering — it must run first in every pipeline
- Never use plain `dict` where `CommentedMap` is needed — breaks round-trip YAML
- Never add required dependencies for LLM features — keep them in `[llm]` extra
- Never log or print secret values in strip-secrets audit trail
- Never commit fixture files containing real secrets or credentials
