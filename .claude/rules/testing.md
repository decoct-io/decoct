---
globs: tests/**
---
# Testing Conventions

- Every module in `src/decoct/` has corresponding tests in `tests/`
- Pass tests use YAML fixture files in `tests/fixtures/` — input YAML in, expected YAML out
- Use `click.testing.CliRunner` for CLI tests
- Test names describe the behaviour being tested, not the method name
- Fixtures go in `tests/fixtures/` organised by type: `schemas/`, `assertions/`, `yaml/`
- Run the full suite with `pytest --cov=decoct -v` before considering work complete
