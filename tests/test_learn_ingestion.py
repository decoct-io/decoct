"""Tests for LLM-assisted ingestion spec inference."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from decoct.adapters.ingestion_models import (
    CompositePathSpec,
    IngestionEntry,
    IngestionSpec,
)
from decoct.adapters.ingestion_spec import load_ingestion_spec
from decoct.cli import cli
from decoct.learn_ingestion import (
    _build_stem_map,
    _infer_file_pattern,
    _select_samples,
    _validate_llm_response,
    dump_ingestion_spec,
    infer_ingestion_spec,
)


# ---------------------------------------------------------------------------
# TestInferFilePattern — pure logic
# ---------------------------------------------------------------------------


class TestInferFilePattern:
    def test_common_prefix_with_dash(self) -> None:
        assert _infer_file_pattern(["pg-prod", "pg-dev", "pg-staging"]) == "pg-*"

    def test_common_prefix_with_longer_stem(self) -> None:
        assert _infer_file_pattern(["systemd-core-api", "systemd-billing-api"]) == "systemd-*"

    def test_no_common_prefix(self) -> None:
        assert _infer_file_pattern(["alpha", "beta"]) == "*"

    def test_single_entity(self) -> None:
        assert _infer_file_pattern(["single-file"]) == "single-file"

    def test_empty_list(self) -> None:
        assert _infer_file_pattern([]) == "*"

    def test_common_prefix_underscore(self) -> None:
        assert _infer_file_pattern(["app_config_prod", "app_config_dev"]) == "app_config_*"


# ---------------------------------------------------------------------------
# TestValidateLlmResponse — parsing/validation
# ---------------------------------------------------------------------------


class TestValidateLlmResponse:
    def test_valid_with_composites(self) -> None:
        yaml_str = (
            "platform: docker-compose\n"
            "description: Docker Compose configuration\n"
            "composite_paths:\n"
            "- path: services\n"
            "  kind: map\n"
            "  reason: Service definitions\n"
        )
        result = _validate_llm_response(yaml_str)
        assert result["platform"] == "docker-compose"
        assert len(result["composite_paths"]) == 1
        assert result["composite_paths"][0]["kind"] == "map"

    def test_valid_without_composites(self) -> None:
        yaml_str = "platform: sysctl\ndescription: Kernel params\n"
        result = _validate_llm_response(yaml_str)
        assert result["platform"] == "sysctl"

    def test_missing_platform_raises(self) -> None:
        yaml_str = "description: Something\n"
        with pytest.raises(ValueError, match="platform"):
            _validate_llm_response(yaml_str)

    def test_not_mapping_raises(self) -> None:
        yaml_str = "- item1\n- item2\n"
        with pytest.raises(ValueError, match="not a YAML mapping"):
            _validate_llm_response(yaml_str)

    def test_invalid_composite_kind_raises(self) -> None:
        yaml_str = (
            "platform: test\n"
            "composite_paths:\n"
            "- path: foo\n"
            "  kind: tuple\n"
        )
        with pytest.raises(ValueError, match="'map' or 'list'"):
            _validate_llm_response(yaml_str)

    def test_null_composite_paths_accepted(self) -> None:
        yaml_str = "platform: test\ncomposite_paths: null\n"
        result = _validate_llm_response(yaml_str)
        assert result["platform"] == "test"


# ---------------------------------------------------------------------------
# TestSelectSamples — with tmp_path
# ---------------------------------------------------------------------------


class TestSelectSamples:
    def _make_entity(self, entity_id: str, n_attrs: int) -> Any:
        """Create a minimal Entity-like object with n attributes."""
        from decoct.core.types import Attribute, Entity

        entity = Entity(id=entity_id)
        for i in range(n_attrs):
            entity.attributes[f"attr{i}"] = Attribute(
                path=f"attr{i}", value=str(i), type="string", source=entity_id,
            )
        return entity

    def test_selects_largest_entities_first(self, tmp_path: Path) -> None:
        (tmp_path / "small.yaml").write_text("a: 1")
        (tmp_path / "large.yaml").write_text("a: 1\nb: 2\nc: 3")

        entities = [
            self._make_entity("small", 1),
            self._make_entity("large", 5),
        ]
        stem_map = _build_stem_map(tmp_path)
        samples = _select_samples(entities, stem_map, max_samples=1)
        assert len(samples) == 1
        assert samples[0][0] == "large"

    def test_respects_max_chars(self, tmp_path: Path) -> None:
        (tmp_path / "a.yaml").write_text("x" * 1000)
        (tmp_path / "b.yaml").write_text("y" * 1000)

        entities = [
            self._make_entity("a", 5),
            self._make_entity("b", 3),
        ]
        stem_map = _build_stem_map(tmp_path)
        samples = _select_samples(entities, stem_map, max_samples=2, max_chars=500)

        total_chars = sum(len(c) for _, c in samples)
        assert total_chars <= 500 + 200  # 200 for min(100) per file

    def test_handles_missing_files(self, tmp_path: Path) -> None:
        # Only create one file, entity references two
        (tmp_path / "exists.yaml").write_text("a: 1")

        entities = [
            self._make_entity("exists", 3),
            self._make_entity("missing", 5),
        ]
        stem_map = _build_stem_map(tmp_path)
        samples = _select_samples(entities, stem_map, max_samples=2)
        assert len(samples) == 1
        assert samples[0][0] == "exists"


# ---------------------------------------------------------------------------
# TestDumpIngestionSpec — round-trip
# ---------------------------------------------------------------------------


class TestDumpIngestionSpec:
    def test_round_trip(self, tmp_path: Path) -> None:
        spec = IngestionSpec(
            version=1,
            adapter="hybrid-infra",
            generated_by="decoct-infer",
            entries=[
                IngestionEntry(
                    file_pattern="pg-*",
                    platform="postgresql",
                    description="PostgreSQL config",
                    composite_paths=[
                        CompositePathSpec(path="settings", kind="map", reason="Key-value settings"),
                    ],
                ),
                IngestionEntry(
                    file_pattern="sysctl-*",
                    platform="sysctl",
                    description="Kernel params",
                ),
            ],
        )

        yaml_str = dump_ingestion_spec(spec)
        assert "postgresql" in yaml_str
        assert "sysctl" in yaml_str

        # Write and reload
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml_str)
        reloaded = load_ingestion_spec(spec_file)

        assert reloaded.version == 1
        assert reloaded.adapter == "hybrid-infra"
        assert len(reloaded.entries) == 2
        assert reloaded.entries[0].platform == "postgresql"
        assert reloaded.entries[0].file_pattern == "pg-*"
        assert len(reloaded.entries[0].composite_paths) == 1
        assert reloaded.entries[0].composite_paths[0].kind == "map"
        assert reloaded.entries[1].platform == "sysctl"


# ---------------------------------------------------------------------------
# TestInferIngestionSpec — mocked openai client
# ---------------------------------------------------------------------------


class TestInferIngestionSpec:
    @staticmethod
    def _create_fixtures(tmp_path: Path) -> Path:
        """Create a small fixture directory with a mix of auto-detected and unknown files."""
        configs = tmp_path / "configs"
        configs.mkdir()

        # Docker compose files (auto-detected by detect_platform)
        for name in ["docker-compose-prod", "docker-compose-staging"]:
            (configs / f"{name}.yaml").write_text(
                "version: '3'\nservices:\n  web:\n    image: nginx\n"
            )

        # Unknown platform files (no schema_type_hint)
        for name in ["myapp-prod", "myapp-staging", "myapp-dev"]:
            (configs / f"{name}.yaml").write_text(
                f"app_name: {name}\ndatabase:\n  host: db.example.com\n  port: 5432\n"
            )

        return configs

    def test_infer_spec_mocked_llm(self, tmp_path: Path) -> None:
        configs = self._create_fixtures(tmp_path)

        canned_response = MagicMock()
        canned_response.choices = [MagicMock()]
        canned_response.choices[0].message.content = (
            "```yaml\n"
            "platform: custom-app\n"
            "description: Custom application config\n"
            "composite_paths:\n"
            "- path: database\n"
            "  kind: map\n"
            "  reason: Database settings\n"
            "```"
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = canned_response

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}), \
             patch("openai.OpenAI", return_value=mock_client):

            progress_messages: list[str] = []
            spec = infer_ingestion_spec(
                input_dir=configs,
                on_progress=progress_messages.append,
            )

        # Only unknown clusters get LLM calls
        assert mock_client.chat.completions.create.call_count >= 1

        # Check spec structure
        assert spec.version == 1
        assert spec.adapter == "hybrid-infra"
        assert len(spec.entries) >= 1

        # Find the custom-app entry
        platforms = [e.platform for e in spec.entries]
        assert "custom-app" in platforms

    def test_graceful_skip_on_llm_error(self, tmp_path: Path) -> None:
        configs = self._create_fixtures(tmp_path)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("API error")

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}), \
             patch("openai.OpenAI", return_value=mock_client), \
             pytest.warns(UserWarning, match="LLM call failed"):

            spec = infer_ingestion_spec(input_dir=configs)

        # Spec should still be created, just with no entries for the failed cluster
        assert spec.version == 1
        assert isinstance(spec.entries, list)

    def test_no_llm_calls_when_all_detected(self, tmp_path: Path) -> None:
        configs = tmp_path / "configs"
        configs.mkdir()

        # All files are auto-detectable docker-compose
        for name in ["dc-prod", "dc-staging"]:
            (configs / f"{name}.yaml").write_text(
                "version: '3'\nservices:\n  web:\n    image: nginx\n"
            )

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}), \
             patch("openai.OpenAI") as mock_openai:

            spec = infer_ingestion_spec(input_dir=configs)

        # No LLM calls should have been made
        mock_openai.return_value.chat.completions.create.assert_not_called()
        assert len(spec.entries) == 0


# ---------------------------------------------------------------------------
# TestCliInferSpec — CLI integration
# ---------------------------------------------------------------------------


class TestCliInferSpec:
    def test_help_shows_options(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["entity-graph", "infer-spec", "--help"])
        assert result.exit_code == 0
        assert "--input-dir" in result.output
        assert "--model" in result.output
        assert "--base-url" in result.output
        assert "--api-key-env" in result.output
        assert "--adapter" in result.output

    def test_missing_input_dir_fails(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["entity-graph", "infer-spec"])
        assert result.exit_code != 0

    def test_appears_in_entity_graph_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["entity-graph", "--help"])
        assert result.exit_code == 0
        assert "infer-spec" in result.output
