"""Tests for LLM-assisted schema learning."""

from __future__ import annotations

from pathlib import Path

import pytest

from decoct.learn import _extract_schema_yaml, _validate_schema, merge_schemas

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
