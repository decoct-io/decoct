---
globs: tests/**
---
# Testing Conventions

- Every module in `src/decoct/` has corresponding tests in `tests/`
- Use `click.testing.CliRunner` for CLI tests
- Test names describe the behaviour being tested, not the method name
- Entity-graph fixtures in `tests/fixtures/` organised by dataset: `iosxr/`, `entra-intune/`, `hybrid-infra/`, `projections/`
- Run the full suite with `pytest --cov=decoct -v` before considering work complete
- The gate test (`test_entity_graph_e2e.py`) must pass with 0 reconstruction mismatches before any PR
