# CLAUDE.md — decoct

## What This Project Is

decoct is an open source Python library and CLI that compresses infrastructure data
(YAML, JSON, INI/config files) for LLM context windows — stripping platform defaults,
removing noise, and highlighting deviations from design standards. Saves 20-80%
of tokens depending on input verbosity, while making output more informative, not less.

**Repository:** `decoct-io/decoct` on GitHub
**Package:** `decoct` on PyPI (v0.1.0)
**Licence:** MIT
**Python:** 3.10+

## Architecture

Three-phase compression pipeline:

1. **Assertion Preparation** — design standards → structured, machine-evaluable assertions
2. **Schema Preparation** — platform defaults extracted from vendor schemas or LLM-learned
3. **Deterministic Processing** — pipeline applies assertions and schemas as tree transformations

Three compression tiers: generic cleanup (~15%), platform defaults (~20-55%), standards conformance (~30-80%).

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
├── formats.py           # input format detection + conversion (JSON, INI → CommentedMap)
├── learn.py             # LLM-assisted schema/assertion learning (requires [llm])
├── passes/              # 10 passes: strip-secrets, strip-comments, strip-defaults,
│                        #   strip-conformant, annotate-deviations, deviation-summary,
│                        #   emit-classes, drop-fields, keep-fields, prune-empty
├── schemas/             # models + loader + resolver + bundled/ (30 schemas)
├── assertions/          # models + loader + matcher + bundled/ (1 assertion set)
└── profiles/            # models + loader + resolver + bundled/ (1 profile)
tests/                   # 21 test files
├── test_cli.py, test_pipeline.py, test_tokens.py, test_schemas.py, ...
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
- **Diverse input, YAML output** — YAML, JSON, and INI/config file input supported. XML and CLI normalisation planned for Phase 3.
- **Bundled schemas by short name** — 30 bundled schemas accessible via `--schema docker-compose` (short name) or `--schema path/to/file.yaml`.

## Development Plan

- **Phase 1: Foundation + Core Pipeline** — COMPLETE. All 9 steps (skeleton through CLI integration).
- **Phase 2: Real-World Validation** — Mostly complete. 30 bundled schemas, JSON/INI input, schema/assertion learning, platform auto-detection, emit-classes, directory mode, comprehensive docs. Remaining: additional platform schemas, more bundled assertion sets.
- **Phase 3-7:** XML/CLI input, LLM-direct mode, scaffolding packs, class reconstitution, benchmarks, docs site.

See `decoct-dev-plan.md` for step-by-step breakdown, `docs/roadmap.md` for Phase 3-7 roadmap, `docs/steering.md` for detailed research.

## What NOT to Do

- Never bypass strip-secrets ordering — it must run first in every pipeline
- Never use plain `dict` where `CommentedMap` is needed — breaks round-trip YAML
- Never add required dependencies for LLM features — keep them in `[llm]` extra
- Never log or print secret values in strip-secrets audit trail
- Never commit fixture files containing real secrets or credentials
