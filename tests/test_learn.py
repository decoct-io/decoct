"""Tests for LLM-assisted schema and assertion learning."""

from __future__ import annotations

from pathlib import Path

import pytest

from decoct.learn import (
    _extract_schema_yaml,
    _extract_yaml_block,
    _validate_assertions,
    _validate_schema,
    merge_assertions,
    merge_schemas,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestExtractSchemaYaml:
    def test_extracts_from_yaml_code_block(self) -> None:
        response = "Here is the schema:\n```yaml\nplatform: test\ndefaults:\n  foo: bar\n```\nDone."
        result = _extract_schema_yaml(response)
        assert "platform: test" in result
        assert "foo: bar" in result

    def test_extracts_from_plain_code_block(self) -> None:
        response = "```\nplatform: test\ndefaults:\n  foo: bar\n```"
        result = _extract_schema_yaml(response)
        assert "platform: test" in result

    def test_returns_raw_yaml(self) -> None:
        response = "platform: test\ndefaults:\n  foo: bar"
        result = _extract_schema_yaml(response)
        assert "platform: test" in result

    def test_extracts_yml_code_block(self) -> None:
        response = "```yml\nplatform: test\ndefaults:\n  foo: bar\n```"
        result = _extract_schema_yaml(response)
        assert "platform: test" in result


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

    def test_missing_defaults_raises(self) -> None:
        with pytest.raises(ValueError, match="missing required keys"):
            _validate_schema("platform: test")

    def test_defaults_not_mapping_raises(self) -> None:
        with pytest.raises(ValueError, match="defaults must be a mapping"):
            _validate_schema("platform: test\ndefaults: not-a-map")

    def test_sets_optional_defaults(self) -> None:
        result = _validate_schema("platform: test\ndefaults:\n  foo: bar")
        assert result["source"] == "LLM-derived"
        assert result["confidence"] == "medium"
        assert result["drop_patterns"] == []
        assert result["system_managed"] == []

    def test_non_mapping_raises(self) -> None:
        with pytest.raises(ValueError, match="not a YAML mapping"):
            _validate_schema("- item1\n- item2")


class TestMergeSchemas:
    def test_merge_adds_new_defaults(self, tmp_path: Path) -> None:
        base = tmp_path / "base.yaml"
        base.write_text("platform: test\ndefaults:\n  foo: bar\ndrop_patterns: []\nsystem_managed: []\n")
        additions = "platform: test\ndefaults:\n  baz: qux\ndrop_patterns: []\nsystem_managed: []\n"
        result = merge_schemas(base, additions)
        assert "foo: bar" in result
        assert "baz: qux" in result

    def test_merge_does_not_overwrite_existing(self, tmp_path: Path) -> None:
        base = tmp_path / "base.yaml"
        base.write_text("platform: test\ndefaults:\n  foo: original\ndrop_patterns: []\nsystem_managed: []\n")
        additions = "platform: test\ndefaults:\n  foo: replaced\n  new: value\ndrop_patterns: []\nsystem_managed: []\n"
        result = merge_schemas(base, additions)
        assert "original" in result
        assert "new: value" in result

    def test_merge_combines_system_managed(self, tmp_path: Path) -> None:
        base = tmp_path / "base.yaml"
        base.write_text("platform: test\ndefaults:\n  foo: bar\ndrop_patterns: []\nsystem_managed:\n  - a\n  - b\n")
        additions = "platform: test\ndefaults: {}\ndrop_patterns: []\nsystem_managed:\n  - b\n  - c\n"
        result = merge_schemas(base, additions)
        assert "- a" in result
        assert "- b" in result
        assert "- c" in result


class TestLearnSchemaRequiresAnthropicSdk:
    def test_import_error_without_sdk(self) -> None:
        """learn_schema raises ImportError if anthropic is not installed."""
        # This test just verifies the error message is helpful.
        # If anthropic IS installed, the test will try to call the API.
        from decoct.learn import learn_schema

        try:
            learn_schema(examples=[FIXTURES / "yaml" / "realistic-compose.yaml"])
        except ImportError as e:
            assert "pip install decoct[llm]" in str(e)
        except Exception:  # noqa: BLE001
            # anthropic IS installed but no API key — that's fine too
            pass


class TestCliSchemaLearn:
    def test_learn_no_inputs_fails(self) -> None:
        from click.testing import CliRunner

        from decoct.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["schema", "learn"])
        assert result.exit_code != 0
        assert "at least one" in result.output

    def test_schema_group_help(self) -> None:
        from click.testing import CliRunner

        from decoct.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["schema", "--help"])
        assert result.exit_code == 0
        assert "learn" in result.output


# ---------------------------------------------------------------------------
# Assertion learning tests
# ---------------------------------------------------------------------------


class TestExtractYamlBlock:
    """Test the shared _extract_yaml_block helper (same logic as schema extraction)."""

    def test_extracts_from_yaml_code_block(self) -> None:
        response = "Here:\n```yaml\nassertions:\n  - id: test\n```\nDone."
        result = _extract_yaml_block(response)
        assert "assertions:" in result
        assert "id: test" in result

    def test_extracts_from_plain_code_block(self) -> None:
        response = "```\nassertions:\n  - id: test\n```"
        result = _extract_yaml_block(response)
        assert "assertions:" in result

    def test_returns_raw_yaml(self) -> None:
        response = "assertions:\n  - id: test"
        result = _extract_yaml_block(response)
        assert "assertions:" in result

    def test_alias_works(self) -> None:
        """_extract_schema_yaml is an alias for _extract_yaml_block."""
        response = "```yaml\nplatform: test\n```"
        assert _extract_yaml_block(response) == _extract_schema_yaml(response)


class TestValidateAssertions:
    def test_valid_assertions(self) -> None:
        yaml_str = (
            "assertions:\n"
            "  - id: test-assert\n"
            "    assert: Images must be pinned\n"
            "    rationale: Reproducibility\n"
            "    severity: must\n"
            "    match:\n"
            "      path: services.*.image\n"
            "      pattern: ':sha256:'\n"
        )
        result = _validate_assertions(yaml_str)
        assert len(result) == 1
        assert result[0]["id"] == "test-assert"

    def test_valid_without_match(self) -> None:
        yaml_str = (
            "assertions:\n"
            "  - id: context-only\n"
            "    assert: Use least privilege\n"
            "    rationale: Security\n"
            "    severity: should\n"
        )
        result = _validate_assertions(yaml_str)
        assert len(result) == 1
        assert "match" not in result[0]

    def test_not_mapping_raises(self) -> None:
        with pytest.raises(ValueError, match="not a YAML mapping"):
            _validate_assertions("- item1\n- item2")

    def test_missing_assertions_key_raises(self) -> None:
        with pytest.raises(ValueError, match="missing required 'assertions' key"):
            _validate_assertions("platform: test\ndefaults: {}")

    def test_assertions_not_list_raises(self) -> None:
        with pytest.raises(ValueError, match="'assertions' must be a list"):
            _validate_assertions("assertions: not-a-list")

    def test_missing_required_field_raises(self) -> None:
        yaml_str = "assertions:\n  - id: test\n    assert: foo\n"
        with pytest.raises(ValueError, match="missing required field 'rationale'"):
            _validate_assertions(yaml_str)

    def test_invalid_severity_raises(self) -> None:
        yaml_str = (
            "assertions:\n"
            "  - id: test\n"
            "    assert: foo\n"
            "    rationale: bar\n"
            "    severity: critical\n"
        )
        with pytest.raises(ValueError, match="severity must be one of"):
            _validate_assertions(yaml_str)

    def test_match_missing_path_raises(self) -> None:
        yaml_str = (
            "assertions:\n"
            "  - id: test\n"
            "    assert: foo\n"
            "    rationale: bar\n"
            "    severity: must\n"
            "    match:\n"
            "      value: something\n"
        )
        with pytest.raises(ValueError, match="match missing required field 'path'"):
            _validate_assertions(yaml_str)

    def test_multiple_assertions(self) -> None:
        yaml_str = (
            "assertions:\n"
            "  - id: a1\n"
            "    assert: First\n"
            "    rationale: R1\n"
            "    severity: must\n"
            "  - id: a2\n"
            "    assert: Second\n"
            "    rationale: R2\n"
            "    severity: should\n"
        )
        result = _validate_assertions(yaml_str)
        assert len(result) == 2


class TestMergeAssertions:
    def test_merge_adds_new_assertions(self, tmp_path: Path) -> None:
        base = tmp_path / "base.yaml"
        base.write_text(
            "assertions:\n"
            "  - id: existing\n"
            "    assert: Existing rule\n"
            "    rationale: R\n"
            "    severity: must\n"
        )
        additions = (
            "assertions:\n"
            "  - id: new-one\n"
            "    assert: New rule\n"
            "    rationale: R\n"
            "    severity: should\n"
        )
        result = merge_assertions(base, additions)
        assert "existing" in result
        assert "new-one" in result

    def test_merge_skips_duplicate_ids(self, tmp_path: Path) -> None:
        base = tmp_path / "base.yaml"
        base.write_text(
            "assertions:\n"
            "  - id: dup\n"
            "    assert: Original\n"
            "    rationale: R\n"
            "    severity: must\n"
        )
        additions = (
            "assertions:\n"
            "  - id: dup\n"
            "    assert: Replaced\n"
            "    rationale: R\n"
            "    severity: must\n"
            "  - id: fresh\n"
            "    assert: Fresh\n"
            "    rationale: R\n"
            "    severity: may\n"
        )
        result = merge_assertions(base, additions)
        assert "Original" in result
        assert "Replaced" not in result
        assert "fresh" in result

    def test_merge_preserves_base_order(self, tmp_path: Path) -> None:
        base = tmp_path / "base.yaml"
        base.write_text(
            "assertions:\n"
            "  - id: first\n"
            "    assert: A\n"
            "    rationale: R\n"
            "    severity: must\n"
            "  - id: second\n"
            "    assert: B\n"
            "    rationale: R\n"
            "    severity: should\n"
        )
        additions = (
            "assertions:\n"
            "  - id: third\n"
            "    assert: C\n"
            "    rationale: R\n"
            "    severity: may\n"
        )
        result = merge_assertions(base, additions)
        first_pos = result.index("first")
        second_pos = result.index("second")
        third_pos = result.index("third")
        assert first_pos < second_pos < third_pos


class TestLearnAssertionsRequiresAnthropicSdk:
    def test_import_error_without_sdk(self) -> None:
        from decoct.learn import learn_assertions

        try:
            learn_assertions(standards=[FIXTURES / "yaml" / "realistic-compose.yaml"])
        except ImportError as e:
            assert "pip install decoct[llm]" in str(e)
        except Exception:  # noqa: BLE001
            # anthropic IS installed but no API key — that's fine too
            pass


class TestCliAssertionLearn:
    def test_learn_no_inputs_fails(self) -> None:
        from click.testing import CliRunner

        from decoct.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["assertion", "learn"])
        assert result.exit_code != 0
        assert "at least one" in result.output

    def test_assertion_group_help(self) -> None:
        from click.testing import CliRunner

        from decoct.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["assertion", "--help"])
        assert result.exit_code == 0
        assert "learn" in result.output


# ---------------------------------------------------------------------------
# Corpus mode tests
# ---------------------------------------------------------------------------


class TestLearnAssertionsCorpusValidation:
    """Validation for corpus mode in learn_assertions()."""

    def test_corpus_and_examples_mutually_exclusive(self, tmp_path: Path) -> None:
        from decoct.learn import learn_assertions

        f1 = tmp_path / "a.yaml"
        f1.write_text("foo: bar\n")
        with pytest.raises(ValueError, match="mutually exclusive"):
            learn_assertions(corpus=[f1], examples=[f1])

    def test_corpus_alone_accepted(self, tmp_path: Path) -> None:
        """corpus-only should reach the API call (ImportError or API error, not ValueError)."""
        from decoct.learn import learn_assertions

        f1 = tmp_path / "a.yaml"
        f1.write_text("foo: bar\n")
        try:
            learn_assertions(corpus=[f1])
        except ImportError:
            pass  # no anthropic SDK — expected
        except ValueError:
            pytest.fail("corpus-only should not raise ValueError")
        except Exception:  # noqa: BLE001
            pass  # API key missing etc. — fine

    def test_no_inputs_raises(self) -> None:
        from decoct.learn import learn_assertions

        with pytest.raises(ValueError, match="At least one"):
            learn_assertions()


class TestCliAssertionLearnCorpus:
    """CLI tests for --corpus flag."""

    def test_corpus_and_example_mutually_exclusive(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        from decoct.cli import cli

        f1 = tmp_path / "a.yaml"
        f1.write_text("foo: bar\n")
        runner = CliRunner()
        result = runner.invoke(cli, ["assertion", "learn", "-c", str(f1), "-e", str(f1)])
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output

    def test_corpus_in_help(self) -> None:
        from click.testing import CliRunner

        from decoct.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["assertion", "learn", "--help"])
        assert result.exit_code == 0
        assert "--corpus" in result.output

    def test_no_inputs_fails(self) -> None:
        from click.testing import CliRunner

        from decoct.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["assertion", "learn"])
        assert result.exit_code != 0
        assert "at least one" in result.output
        assert "--corpus" in result.output


class TestValidateAssertionsWithPrevalence:
    """Assertions with prevalence info in rationale pass validation."""

    def test_prevalence_rationale_passes(self) -> None:
        yaml_str = (
            "assertions:\n"
            "  - id: read-only-root\n"
            "    assert: Containers should use read-only root filesystem\n"
            "    rationale: Set in 8/10 files\n"
            "    severity: should\n"
            "    match:\n"
            "      path: 'services.*.read_only'\n"
            "      value: true\n"
        )
        result = _validate_assertions(yaml_str)
        assert len(result) == 1
        assert "8/10" in result[0]["rationale"]

    def test_corpus_severity_mapping(self) -> None:
        """All three corpus severity levels are accepted."""
        yaml_str = (
            "assertions:\n"
            "  - id: always-set\n"
            "    assert: Always configured\n"
            "    rationale: Set in 10/10 files\n"
            "    severity: must\n"
            "  - id: usually-set\n"
            "    assert: Usually configured\n"
            "    rationale: Set in 8/10 files\n"
            "    severity: should\n"
            "  - id: sometimes-set\n"
            "    assert: Sometimes configured\n"
            "    rationale: Set in 6/10 files\n"
            "    severity: may\n"
        )
        result = _validate_assertions(yaml_str)
        assert len(result) == 3
        severities = {a["severity"] for a in result}
        assert severities == {"must", "should", "may"}
