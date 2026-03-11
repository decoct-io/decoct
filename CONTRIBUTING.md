# Contributing to decoct

Thank you for your interest in contributing to decoct. This guide covers
development setup, code conventions, and the process for submitting changes.

## Development Setup

```bash
git clone https://github.com/decoct-io/decoct.git
cd decoct
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pip install -e ".[dev,llm]"  # Also enables LLM features
decoct --version  # verify
```

Python 3.10 or later is required.

## Project Structure

All package code lives under `src/decoct/`:

- `cli.py` — click CLI entry point (`decoct entity-graph` commands)
- `entity_pipeline.py` — top-level orchestrator (chains all 8 pipeline phases)
- `tokens.py` — tiktoken wrapper for token counting
- `formats.py` — input format detection and normalisation
- `core/` — Entity, Attribute, CompositeValue, EntityGraph, canonical functions, config
- `adapters/` — BaseAdapter + IOS-XR, Hybrid-Infra, Entra-Intune adapters
- `analysis/` — attribute profiling, Shannon entropy, tier/role classification
- `discovery/` — type seeding (Jaccard), bootstrap loop, anti-unification, composite decomposition
- `compression/` — class extraction, delta compression, normalisation, phone book
- `assembly/` — Tier A/B/C YAML builders, ID range compression, token estimation
- `reconstruction/` — entity reconstitution + validation (100% fidelity gate test)
- `qa/` — question generation + LLM evaluation harness
- `projections/` — subject projections: models, path matcher, spec loader, generator
- `secrets/` — secret masking (pre-flatten + post-flatten)
- `learn_ingestion.py` — LLM-assisted ingestion spec inference
- `learn_projections.py` — LLM-assisted projection spec inference
- `learn_tier_a.py` — LLM-assisted Tier A spec inference

Tests mirror the source structure under `tests/`, with fixtures in `tests/fixtures/`.

## Running Tests

```bash
pytest --cov=decoct -v              # Full suite with coverage
pytest -k entity -v                 # All entity-graph tests
pytest tests/test_entity_graph_e2e.py -v  # Gate test (must pass with 0 mismatches)
```

## Linting and Type Checking

```bash
ruff check src/ tests/     # Lint
mypy src/                  # Type check
```

Both must pass cleanly before submitting a pull request.

## Code Style

- Line length: 120 (ruff enforced)
- Type annotations everywhere (mypy strict mode)
- Dataclasses over Pydantic — keep core dependencies light
- ruamel.yaml round-trip types (`CommentedMap`/`CommentedSeq`, never plain `dict`)
- Import style: absolute imports from `decoct`

## Writing Tests

- Every module has corresponding tests
- Test names describe behaviour: `test_redacts_aws_access_key`, not `test_check_regex`
- Use `click.testing.CliRunner` for CLI tests
- Fixtures go in `tests/fixtures/` organized by dataset: `iosxr/`, `entra-intune/`, `hybrid-infra/`
- Test fixtures must use synthetic data, never real credentials
- The gate test (`test_entity_graph_e2e.py`) must pass with 0 reconstruction mismatches

## Adding an Adapter

1. Create `src/decoct/adapters/my_adapter.py`
2. Extend `BaseAdapter`, implement `parse_directory()` → `EntityGraph`
3. Add adapter option to relevant CLI commands in `cli.py`
4. Add test fixtures under `tests/fixtures/my-dataset/`
5. Create corresponding test files

## Important Conventions

- Never use plain `dict` where `CommentedMap` is needed — it breaks round-trip YAML
- Never log or store actual secret values
- LLM dependencies are optional (in `[llm]` extra, not core)
- Entity-graph code uses `UPPER_CASE` function names for canonical functions — suppressed via ruff per-file overrides
- CompositeValue wrapping is critical — without it, per-device structures shatter type discovery

## Pull Request Process

1. Fork and create a feature branch
2. Make changes with tests
3. Run full test suite, linter, and type checker
4. Ensure the gate test passes with 0 reconstruction mismatches
5. Submit PR with clear description
6. Respond to review feedback

## Licence

By contributing, you agree that your contributions will be licensed under the
[MIT licence](https://opensource.org/licenses/MIT).
