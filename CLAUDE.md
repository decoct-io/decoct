# CLAUDE.md — decoct

## What This Project Is

decoct is an open source Python library and CLI that compresses fleets of infrastructure
configs (YAML, JSON, INI/config files) for LLM context windows — extracting shared classes,
computing per-entity deltas, and producing a three-tier compressed representation.

**Repository:** `decoct-io/decoct` on GitHub
**Package:** `decoct` on PyPI (v0.1.0)
**Licence:** MIT
**Python:** 3.10+

## Pipeline

decoct uses the entity-graph pipeline for fleet-scale compression across many files into shared classes + per-entity deltas. See `.claude/rules/entity-graph.md` for detailed guidance. Architecture doc: `docs/entity-graph-architecture.md`.

## Tech Stack

- **ruamel.yaml** — round-trip YAML (CommentedMap/CommentedSeq throughout)
- **tiktoken** — token counting (cl100k_base default, o200k_base configurable)
- **click** — CLI framework
- **hatchling** — build system
- **pytest** / **ruff** / **mypy** — testing, linting, type checking

## Development Workflow

```bash
pip install -e ".[dev]"       # Install with dev dependencies
pip install -e ".[dev,llm]"   # Also enables LLM features (learn, QA evaluation)
pytest --cov=decoct -v        # Run all tests with coverage
ruff check src/ tests/        # Lint
mypy src/                     # Type check
decoct --version              # Verify CLI entry point
```

## Conventions

- **src layout** — all package code under `src/decoct/`
- **Dataclasses over Pydantic** — keep core dependency-light
- **Type annotations everywhere** — mypy strict mode
- **ruamel.yaml round-trip** — use CommentedMap/CommentedSeq, never plain dict for YAML processing
- **Tests per module** — every module has corresponding tests
- **LLM deps are optional** — `pip install decoct` = deterministic pipeline only; `[llm]` adds anthropic SDK
- **Line length 120** — ruff enforced

## What NOT to Do

- Never use plain `dict` where `CommentedMap` is needed — breaks round-trip YAML
- Never add required dependencies for LLM features — keep them in `[llm]` extra
- Never commit fixture files containing real secrets or credentials
