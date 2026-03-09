# Testing Guide

This guide covers the testing conventions, patterns, and tooling used in the
decoct codebase. Every module in `src/decoct/` has corresponding tests in
`tests/`. The test suite is run with pytest and targets >90% line coverage.

## Test Organisation

```
tests/
├── test_cli.py              # CLI commands via CliRunner
├── test_e2e.py              # End-to-end against realistic fixtures
├── test_integration.py      # Full pipeline integration
├── test_schemas.py          # Schema model and loader
├── test_assertions.py       # Assertion model and loader
├── test_profiles.py         # Profile loading and resolution
├── test_pipeline.py         # Pipeline sort and execution
├── test_tokens.py           # Token counting
├── test_learn.py            # LLM learning (mocked)
├── test_json_input.py       # JSON format handling
├── test_ini_input.py        # INI format handling
├── test_schema_bundling.py  # Bundled schema validation
├── test_passes/             # One file per pass
│   ├── test_strip_secrets.py
│   ├── test_strip_defaults.py
│   ├── test_strip_comments.py
│   ├── test_drop_fields.py
│   ├── test_keep_fields.py
│   ├── test_assertion_passes.py
│   └── test_emit_classes.py
└── fixtures/                # Test data
    ├── yaml/                # YAML input fixtures
    ├── json/                # JSON input fixtures
    ├── ini/                 # INI input fixtures
    ├── schemas/             # Schema fixtures
    ├── assertions/          # Assertion fixtures
    └── profiles/            # Profile fixtures
```

Each pass has its own test file under `test_passes/`. Higher-level tests
(`test_integration.py`, `test_e2e.py`) exercise the full pipeline and CLI
end-to-end.

## Fixture System

Fixtures are real YAML, JSON, and INI files stored in `tests/fixtures/`,
organised by type:

- `yaml/` -- input documents (e.g. `with-secrets.yaml`, `realistic-compose.yaml`,
  `with-defaults.yaml`, `with-assertions.yaml`, `realistic-with-deviations.yaml`)
- `json/` -- JSON input documents (e.g. `simple-config.json`, `tfstate-sample.json`)
- `ini/` -- INI/key-value input documents
- `schemas/` -- schema definition files (e.g. `docker-compose.yaml`, `docker-compose-full.yaml`)
- `assertions/` -- assertion definition files (e.g. `test-must-assertions.yaml`,
  `deployment-standards.yaml`)
- `profiles/` -- profile definition files (e.g. `docker.yaml`, `docker-full.yaml`)

Fixtures are loaded with `ruamel.yaml` in round-trip mode. Most test files
define a helper at the top:

```python
from pathlib import Path
from ruamel.yaml import YAML

FIXTURES = Path(__file__).parent.parent / "fixtures" / "yaml"

def _load_yaml(path: Path) -> dict:
    yaml = YAML(typ="rt")
    return yaml.load(path)
```

Naming convention: fixture names are descriptive rather than numbered.
`with-secrets.yaml` contains synthetic secrets, `realistic-compose.yaml`
contains a representative docker-compose file, and
`realistic-with-deviations.yaml` contains deliberate standard violations.

**Important:** test fixtures must use synthetic secrets only -- never real
credentials.

## Writing Pass Tests

Every compression pass follows the same test pattern. Here is a concrete
example from `test_strip_secrets.py`:

### 1. Load the fixture

```python
from pathlib import Path
from ruamel.yaml import YAML
from decoct.passes.strip_secrets import strip_secrets, REDACTED

FIXTURES = Path(__file__).parent.parent / "fixtures" / "yaml"

def _load_yaml(path: Path) -> dict:
    yaml = YAML(typ="rt")
    return yaml.load(path)
```

### 2. Create the pass instance and run it

For simple function-based passes (strip-secrets):

```python
class TestStripSecretsFixture:
    def setup_method(self) -> None:
        self.doc = _load_yaml(FIXTURES / "with-secrets.yaml")
        self.audit = strip_secrets(self.doc)
        self.audit_paths = {e.path for e in self.audit}
        self.audit_methods = {e.path: e.detection_method for e in self.audit}
```

For schema-aware passes (strip-defaults), load the schema first:

```python
from decoct.schemas import load_schema
from decoct.passes.strip_defaults import strip_defaults

SCHEMA_FIXTURES = Path(__file__).parent.parent / "fixtures" / "schemas"

class TestStripDefaults:
    def setup_method(self) -> None:
        self.schema = load_schema(SCHEMA_FIXTURES / "docker-compose.yaml")

    def test_strips_matching_defaults(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "with-defaults.yaml")
        count = strip_defaults(doc, self.schema)
        assert "restart" not in doc["services"]["web"]
        assert doc["services"]["db"]["restart"] == "always"
        assert count > 0
```

For assertion-aware passes (strip-conformant, annotate-deviations), load
assertions:

```python
from decoct.assertions import load_assertions
from decoct.passes.strip_conformant import strip_conformant

ASSERTION_FIXTURES = Path(__file__).parent.parent / "fixtures" / "assertions"

class TestStripConformant:
    def setup_method(self) -> None:
        self.assertions = load_assertions(
            ASSERTION_FIXTURES / "test-must-assertions.yaml"
        )

    def test_strips_conformant_values(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "with-assertions.yaml")
        count = strip_conformant(doc, self.assertions)
        assert "image" not in doc["services"]["web"]
        assert "restart" not in doc["services"]["web"]
        assert count == 3
```

### 3. Assert results

The standard assertions to check on every pass:

- **items_removed count** -- the pass returns how many items it removed
- **specific keys absent** -- stripped values should be gone from the document
- **specific keys present** -- non-matching values must be preserved
- **detail messages** -- audit trail entries, deviation messages, or annotation
  comments contain the expected information

```python
def test_password_redacted(self) -> None:
    assert self.doc["database"]["password"] == REDACTED
    assert "database.password" in self.audit_paths
    assert self.audit_methods["database.password"] == "path_pattern"

def test_hostname_preserved(self) -> None:
    assert self.doc["safe"]["hostname"] == "db-01.mgmt.internal"
```

### 4. Test the Pass class wrapper

Each pass also has a class wrapper (e.g. `StripDefaultsPass`) that integrates
with the pipeline. Test its metadata and behaviour:

```python
from decoct.passes.strip_defaults import StripDefaultsPass

class TestStripDefaultsPass:
    def test_pass_ordering(self) -> None:
        assert "strip-secrets" in StripDefaultsPass.run_after
        assert "strip-comments" in StripDefaultsPass.run_after

    def test_pass_name(self) -> None:
        assert StripDefaultsPass.name == "strip-defaults"

    def test_pass_with_no_schema(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("key: value\n")
        p = StripDefaultsPass()
        result = p.run(doc)
        assert doc["key"] == "value"
        assert result.items_removed == 0
```

### 5. Edge cases

Always cover:

- **Empty document** -- pass should handle `{}` without error
- **Already-stripped document** -- running the pass on output that has already
  been processed should be a no-op
- **Missing keys** -- document lacks the paths the pass targets
- **Nested structures** -- secrets inside lists, defaults in deeply nested maps

```python
def test_empty_document(self) -> None:
    yaml = YAML(typ="rt")
    doc = yaml.load("{}\n")
    audit = strip_secrets(doc)
    assert len(audit) == 0

def test_nested_lists_with_secrets(self) -> None:
    yaml = YAML(typ="rt")
    doc = yaml.load("items:\n  - password: secret123\n  - name: safe\n")
    strip_secrets(doc)
    assert doc["items"][0]["password"] == REDACTED
    assert doc["items"][1]["name"] == "safe"
```

## CLI Testing with CliRunner

CLI tests use Click's `CliRunner` to invoke the `cli` entry point without
spawning a subprocess. The pattern from `test_cli.py`:

```python
from pathlib import Path
from click.testing import CliRunner
from decoct.cli import cli

FIXTURES = Path(__file__).parent / "fixtures"
YAML_FIXTURES = FIXTURES / "yaml"
SCHEMA_FIXTURES = FIXTURES / "schemas"
ASSERTION_FIXTURES = FIXTURES / "assertions"

def test_compress_with_schema() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [
        "compress",
        str(YAML_FIXTURES / "with-defaults.yaml"),
        "--schema", str(SCHEMA_FIXTURES / "docker-compose.yaml"),
    ])
    assert result.exit_code == 0
    assert result.output  # produces output

def test_compress_with_assertions() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [
        "compress",
        str(YAML_FIXTURES / "with-assertions.yaml"),
        "--assertions", str(ASSERTION_FIXTURES / "test-must-assertions.yaml"),
    ])
    assert result.exit_code == 0
    assert "postgres:latest" in result.output
    assert "deviations from standards" in result.output
```

Key patterns in CLI tests:

- **stdin support** -- pass `input=` to `runner.invoke()`:
  ```python
  def test_compress_stdin() -> None:
      runner = CliRunner()
      input_yaml = "db:\n  password: hunter2\n  host: localhost\n"
      result = runner.invoke(cli, ["compress"], input=input_yaml)
      assert result.exit_code == 0
      assert "[REDACTED]" in result.output
  ```
- **output file** -- use pytest's `tmp_path` fixture:
  ```python
  def test_compress_output_file(tmp_path: Path) -> None:
      runner = CliRunner()
      out_file = tmp_path / "output.yaml"
      result = runner.invoke(cli, [
          "compress",
          str(YAML_FIXTURES / "with-defaults.yaml"),
          "--output", str(out_file),
      ])
      assert result.exit_code == 0
      assert out_file.exists()
      content = out_file.read_text()
      assert "services" in content
  ```
- **error handling** -- assert non-zero exit codes for bad input:
  ```python
  def test_compress_nonexistent_file() -> None:
      runner = CliRunner()
      result = runner.invoke(cli, ["compress", "/nonexistent/file.yaml"])
      assert result.exit_code != 0
  ```
- **flags and options** -- test `--stats`, `--stats-only`, `--show-removed`,
  `--profile`, `--recursive`, and bundled schema names

## Integration Tests

Integration tests in `test_integration.py` exercise the full pipeline with
realistic inputs. They verify that passes compose correctly and that ordering
constraints are respected.

### Full pipeline with all passes

```python
from decoct.pipeline import Pipeline
from decoct.passes.strip_secrets import StripSecretsPass
from decoct.passes.strip_comments import StripCommentsPass
from decoct.passes.strip_defaults import StripDefaultsPass
from decoct.passes.strip_conformant import StripConformantPass
from decoct.passes.annotate_deviations import AnnotateDeviationsPass
from decoct.passes.deviation_summary import DeviationSummaryPass
from decoct.tokens import create_report

class TestFullPipelineRealisticCompose:
    def setup_method(self) -> None:
        self.schema = load_schema(SCHEMA_FIXTURES / "docker-compose-full.yaml")
        self.assertions = load_assertions(
            ASSERTION_FIXTURES / "deployment-standards.yaml"
        )

    def test_full_pipeline_realistic_compose(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "realistic-compose.yaml")
        input_text = (YAML_FIXTURES / "realistic-compose.yaml").read_text()

        passes = [
            StripSecretsPass(),
            StripCommentsPass(),
            StripDefaultsPass(schema=self.schema),
            StripConformantPass(assertions=self.assertions),
            AnnotateDeviationsPass(assertions=self.assertions),
            DeviationSummaryPass(assertions=self.assertions),
        ]
        pipeline = Pipeline(passes)
        stats = pipeline.run(doc)

        output_text = _dump_yaml(doc)

        # strip-defaults did work
        assert stats.pass_results[2].items_removed > 0
        # strip-conformant did work
        assert stats.pass_results[3].items_removed > 0
        # Output should be smaller than input
        report = create_report(input_text, output_text)
        assert report.savings_pct > 0
```

### Three-tier compression validation

The integration tests also verify the compression tiers stack correctly --
each additional tier (generic, +schema, +assertions) should produce greater
savings:

```python
def test_three_tier_compression(self) -> None:
    input_text = (YAML_FIXTURES / "realistic-compose.yaml").read_text()

    # Tier 1: Generic only
    doc1 = _load_yaml(YAML_FIXTURES / "realistic-compose.yaml")
    pipeline1 = Pipeline([StripSecretsPass(), StripCommentsPass()])
    pipeline1.run(doc1)
    tier1_report = create_report(input_text, _dump_yaml(doc1))

    # Tier 2: Generic + schema
    doc2 = _load_yaml(YAML_FIXTURES / "realistic-compose.yaml")
    pipeline2 = Pipeline([
        StripSecretsPass(), StripCommentsPass(),
        StripDefaultsPass(schema=self.schema),
    ])
    pipeline2.run(doc2)
    tier2_report = create_report(input_text, _dump_yaml(doc2))

    # Tier 3: Generic + schema + assertions
    doc3 = _load_yaml(YAML_FIXTURES / "realistic-compose.yaml")
    pipeline3 = Pipeline([
        StripSecretsPass(), StripCommentsPass(),
        StripDefaultsPass(schema=self.schema),
        StripConformantPass(assertions=self.assertions),
        AnnotateDeviationsPass(assertions=self.assertions),
        DeviationSummaryPass(assertions=self.assertions),
    ])
    pipeline3.run(doc3)
    tier3_report = create_report(input_text, _dump_yaml(doc3))

    assert tier2_report.savings_pct > tier1_report.savings_pct
    assert tier3_report.savings_pct > tier2_report.savings_pct
```

### Pass ordering verification

```python
def test_secrets_before_defaults(self) -> None:
    passes = [
        StripSecretsPass(),
        StripDefaultsPass(schema=self.schema),
    ]
    pipeline = Pipeline(passes)
    assert pipeline.pass_names.index("strip-secrets") < \
        pipeline.pass_names.index("strip-defaults")
```

## End-to-End Tests

End-to-end tests in `test_e2e.py` invoke the CLI against realistic fixtures
and bundled schemas. They verify the complete user-facing workflow.

### Bundled schema tests

Each bundled schema has e2e tests verifying it loads, processes, and strips
correctly via the CLI:

```python
class TestCompressKubernetes:
    def test_compress_kubernetes_bundled(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "kubernetes-deployment.yaml"),
            "--schema", "kubernetes",
        ])
        assert result.exit_code == 0
        assert "web-app" in result.output
        # Defaults should be stripped from YAML body
        yaml_body = "\n".join(
            line for line in result.output.splitlines()
            if not line.startswith("#")
        )
        assert "schedulerName" not in yaml_body
        assert "enableServiceLinks" not in yaml_body
```

### Platform auto-detection

```python
class TestCompressAutoDetect:
    def test_auto_detect_docker_compose(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "realistic-compose.yaml"),
            "--stats",
        ])
        assert result.exit_code == 0
        assert "saved" in result.output or "Tokens:" in result.output
```

### Directory and batch processing

```python
class TestCompressDirectory:
    def test_compress_directory(self, tmp_path: Path) -> None:
        import shutil
        shutil.copy(YAML_FIXTURES / "realistic-compose.yaml", tmp_path / "a.yaml")
        shutil.copy(
            YAML_FIXTURES / "realistic-with-deviations.yaml", tmp_path / "b.yml"
        )
        runner = CliRunner()
        result = runner.invoke(cli, ["compress", str(tmp_path)])
        assert result.exit_code == 0
        assert "services" in result.output
```

The e2e tests cover Docker Compose, Kubernetes, Cloud-init, Ansible, GitHub
Actions, Traefik, Prometheus, and SSH config schemas, as well as JSON input,
bundled profiles, and directory mode.

## Mocking LLM Calls

The `test_learn.py` file tests LLM-assisted schema and assertion learning
without making real API calls. The approach uses Python's import error
boundary rather than `unittest.mock`:

### Testing the import guard

LLM features require `pip install decoct[llm]`. When the `anthropic` SDK is
not installed, `learn_schema()` and `learn_assertions()` raise `ImportError`
with a helpful message:

```python
class TestLearnSchemaRequiresAnthropicSdk:
    def test_import_error_without_sdk(self) -> None:
        from decoct.learn import learn_schema

        try:
            learn_schema(
                examples=[FIXTURES / "yaml" / "realistic-compose.yaml"]
            )
        except ImportError as e:
            assert "pip install decoct[llm]" in str(e)
        except Exception:
            # anthropic IS installed but no API key -- that's fine too
            pass
```

### Testing validation without the API

Most of the learn module logic (YAML extraction, schema validation, assertion
validation, merging) is tested through pure functions that do not require
the Anthropic client:

```python
class TestExtractSchemaYaml:
    def test_extracts_from_yaml_code_block(self) -> None:
        response = (
            "Here is the schema:\n"
            "```yaml\nplatform: test\ndefaults:\n  foo: bar\n```\n"
            "Done."
        )
        result = _extract_schema_yaml(response)
        assert "platform: test" in result
        assert "foo: bar" in result

class TestValidateSchema:
    def test_valid_schema(self) -> None:
        yaml_str = (
            "platform: test\nsource: test\nconfidence: high\n"
            "defaults:\n  foo: bar\ndrop_patterns: []\nsystem_managed: []"
        )
        result = _validate_schema(yaml_str)
        assert result["platform"] == "test"
        assert result["defaults"]["foo"] == "bar"

    def test_missing_platform_raises(self) -> None:
        with pytest.raises(ValueError, match="missing required keys"):
            _validate_schema("defaults:\n  foo: bar")
```

### Testing merge logic

Merge functions (schema merging, assertion merging) use `tmp_path` to write
base files and verify merge behaviour without any LLM involvement:

```python
class TestMergeSchemas:
    def test_merge_adds_new_defaults(self, tmp_path: Path) -> None:
        base = tmp_path / "base.yaml"
        base.write_text(
            "platform: test\ndefaults:\n  foo: bar\n"
            "drop_patterns: []\nsystem_managed: []\n"
        )
        additions = (
            "platform: test\ndefaults:\n  baz: qux\n"
            "drop_patterns: []\nsystem_managed: []\n"
        )
        result = merge_schemas(base, additions)
        assert "foo: bar" in result
        assert "baz: qux" in result

    def test_merge_does_not_overwrite_existing(self, tmp_path: Path) -> None:
        base = tmp_path / "base.yaml"
        base.write_text(
            "platform: test\ndefaults:\n  foo: original\n"
            "drop_patterns: []\nsystem_managed: []\n"
        )
        additions = (
            "platform: test\ndefaults:\n  foo: replaced\n  new: value\n"
            "drop_patterns: []\nsystem_managed: []\n"
        )
        result = merge_schemas(base, additions)
        assert "original" in result
        assert "new: value" in result
```

### Testing CLI learn commands

CLI-level learn tests verify argument validation and help text without
triggering API calls:

```python
class TestCliSchemaLearn:
    def test_learn_no_inputs_fails(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["schema", "learn"])
        assert result.exit_code != 0
        assert "at least one" in result.output

class TestCliAssertionLearnCorpus:
    def test_corpus_and_example_mutually_exclusive(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.yaml"
        f1.write_text("foo: bar\n")
        runner = CliRunner()
        result = runner.invoke(cli, [
            "assertion", "learn", "-c", str(f1), "-e", str(f1),
        ])
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output
```

## Test Naming Conventions

- **Describe the behaviour**, not the method name: `test_redacts_aws_access_key`,
  not `test_check_regex`
- **Group by feature** within the same file using test classes:
  `TestStripSecretsFixture`, `TestStripSecretsOptions`, `TestHealthcheckExemption`
- **Use `pytest.mark.parametrize`** for similar cases with different inputs:
  ```python
  @pytest.mark.parametrize("value,expected", [
      ("unless-stopped", True),
      ("always", True),
      ("no", False),
      ("on-failure", False),
  ])
  def test_restart_policy_match(self, value: str, expected: bool) -> None:
      assert evaluate_match(self.restart_assertion.match, value) is expected
  ```
- **Positive and negative pairs** -- always test what should be preserved
  alongside what should be removed:
  ```python
  def test_password_redacted(self) -> None:
      assert self.doc["database"]["password"] == REDACTED

  def test_hostname_preserved(self) -> None:
      assert self.doc["safe"]["hostname"] == "db-01.mgmt.internal"
  ```

## Running Tests

```bash
pytest                        # All tests
pytest --cov=decoct -v       # With coverage and verbose output
pytest tests/test_passes/    # Just pass tests
pytest tests/test_e2e.py     # Just end-to-end tests
pytest -k "test_strip"       # Filter by name pattern
pytest -x                    # Stop on first failure
pytest -x --pdb              # Debug on first failure
```

The pytest configuration in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

All tests run from the repository root. Fixture paths are resolved relative
to the test file using `Path(__file__).parent`.

## Coverage Expectations

- **Target:** >90% line coverage overall
- **Critical paths:** 100% coverage required
  - `strip-secrets` -- the security boundary of the pipeline
  - Pipeline ordering logic -- `run_after`/`run_before` constraints must always
    be verified
  - Assertion matching -- every match type (`value`, `pattern`, `range`,
    `contains`, `not_value`, `exists`) has dedicated tests
- **LLM learn module:** tested via validation/merge functions and import guards
  only -- no real API calls in the test suite
- **Edge cases:** empty documents, already-processed documents, missing keys,
  and nested structures are covered for every pass

Run coverage and check for gaps:

```bash
pytest --cov=decoct --cov-report=term-missing -v
```
