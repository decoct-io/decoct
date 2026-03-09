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
decoct --version  # verify
```

Python 3.10 or later is required.

## Project Structure

All package code lives under `src/decoct/`:

- `cli.py` — click CLI entry point
- `pipeline.py` — pass orchestration
- `tokens.py` — tiktoken wrapper for token counting
- `formats.py` — input format detection and normalisation
- `learn.py` — corpus inference for assertion learning
- `passes/` — one module per compression pass (strip-secrets, strip-defaults, etc.)
- `schemas/` — schema models, loader, resolver, and `bundled/` vendor schemas
- `assertions/` — assertion models, loader, matcher, and `bundled/` standard assertions
- `profiles/` — profile loader, resolver, and `bundled/` profiles
- `tests/` — mirrors src structure, with YAML fixtures in `tests/fixtures/`

## Running Tests

```bash
pytest --cov=decoct -v    # Full suite with coverage
pytest tests/test_passes/ # Just pass tests
pytest -k "strip_secrets" # Filter by name
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
- Pass tests use YAML fixtures in `tests/fixtures/`
- Test names describe behaviour: `test_redacts_aws_access_key`, not `test_check_regex`
- Use `click.testing.CliRunner` for CLI tests
- Fixtures go in `tests/fixtures/` organized by type (`schemas/`, `assertions/`, `yaml/`)
- Test fixtures must use synthetic data, never real credentials

## Adding a New Pass

1. Create `src/decoct/passes/my_pass.py`
2. Extend `BasePass`, implement `run()`, set `name`, `run_after`, `run_before`
3. Use the `@register_pass` decorator
4. Add import in `cli.py` (for auto-registration)
5. Create `tests/test_passes/test_my_pass.py`
6. Add fixture files if needed

## Adding a Bundled Schema

1. Create `src/decoct/schemas/bundled/my-platform.yaml`
2. Add entry to `BUNDLED_SCHEMAS` in `src/decoct/schemas/resolver.py`
3. Add platform detection rule in `src/decoct/formats.py` (optional)
4. Add test fixture and schema bundling test
5. Requirements: authoritative/high confidence, documented source

## Adding Bundled Assertions

1. Create `src/decoct/assertions/bundled/my-standards.yaml`
2. Follow the assertion file format (`id`, `assert`, `rationale`, `severity` required)
3. Add tests

## Adding a Bundled Profile

1. Create `src/decoct/profiles/bundled/my-profile.yaml`
2. Add entry to `BUNDLED_PROFILES` in `src/decoct/profiles/resolver.py`
3. Use relative paths for schema/assertion refs

## Adding Input Format Support

1. Add format detection in `src/decoct/formats.py`
2. Add converter function (output must be `CommentedMap`)
3. Add extension to `_INI_EXTENSIONS` or equivalent set
4. Add extension to `_INPUT_EXTENSIONS` in `cli.py`
5. Add tests and fixtures

## Important Conventions

- `strip-secrets` MUST run first in every pipeline — this is the security boundary
- Never use plain `dict` where `CommentedMap` is needed — it breaks round-trip YAML
- Never log or store actual secret values
- LLM dependencies are optional (in `[llm]` extra, not core)
- Test fixtures use synthetic data, never real credentials

## Pull Request Process

1. Fork and create a feature branch
2. Make changes with tests
3. Run full test suite, linter, and type checker
4. Submit PR with clear description
5. Respond to review feedback

## Licence

By contributing, you agree that your contributions will be licensed under the
[MIT licence](https://opensource.org/licenses/MIT).
