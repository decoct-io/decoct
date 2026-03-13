"""Unit tests for LLM-assisted projection spec inference (mocked)."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from decoct.learn_projections import (
    _build_spec,
    _extract_path_prefixes,
    _extract_tier_c_context,
    _validate_llm_response,
    infer_projection_spec,
)
from decoct.projections.models import ProjectionSpec


class TestExtractPathPrefixes:
    def test_extracts_prefixes_from_base_class(self) -> None:
        tier_b = {
            "base_class": {
                "router.bgp.65002": "value",
                "interface.Loopback0.ipv4": "value",
                "hostname": "value",
            },
        }
        prefixes = _extract_path_prefixes(tier_b)
        assert "router" in prefixes
        assert "interface" in prefixes
        assert "hostname" in prefixes

    def test_extracts_from_classes(self) -> None:
        tier_b = {
            "base_class": {},
            "classes": {
                "cls1": {
                    "own_attrs": {"mpls.ldp": "true"},
                },
            },
        }
        prefixes = _extract_path_prefixes(tier_b)
        assert "mpls" in prefixes

    def test_extracts_from_subclasses(self) -> None:
        tier_b = {
            "base_class": {},
            "subclasses": {
                "sub1": {
                    "own_attrs": {"evpn.enable": "true"},
                },
            },
        }
        prefixes = _extract_path_prefixes(tier_b)
        assert "evpn" in prefixes


class TestExtractTierCContext:
    def test_extracts_phone_book_schema(self) -> None:
        tier_c = {
            "instance_data": {
                "schema": ["hostname", "interface.Loopback0.ipv4", "router.isis.prefix-sid"],
                "records": {
                    "device-01": ["device-01", "10.0.0.1", "index 16001"],
                    "device-02": ["device-02", "10.0.0.2", "index 16002"],
                },
            },
        }
        context = _extract_tier_c_context(tier_c)
        assert "3 per-entity variable attributes" in context
        assert "``hostname``" in context
        assert "``interface.Loopback0.ipv4``" in context
        assert "``router.isis.prefix-sid``" in context
        assert "2 entities" in context

    def test_extracts_override_keys(self) -> None:
        tier_c = {
            "instance_data": {"schema": [], "records": {}},
            "overrides": {
                "device-01": {"delta": {"mysqld.innodb_buffer_pool_size": "2G"}},
                "device-02": {"delta": {"mysqld.server_id": "2", "mysqld.innodb_buffer_pool_size": "4G"}},
            },
        }
        context = _extract_tier_c_context(tier_c)
        assert "2 attributes with per-entity exceptions" in context
        assert "``mysqld.innodb_buffer_pool_size``" in context
        assert "``mysqld.server_id``" in context

    def test_extracts_instance_attrs(self) -> None:
        tier_c = {
            "instance_data": {"schema": [], "records": {}},
            "instance_attrs": {
                "policy-1": {"conditions.locations.includeLocations": ["NL-Blocked"]},
            },
        }
        context = _extract_tier_c_context(tier_c)
        assert "Instance-specific complex attributes" in context
        assert "``conditions.locations.includeLocations``" in context

    def test_extracts_class_assignments(self) -> None:
        tier_c = {
            "instance_data": {"schema": [], "records": {}},
            "class_assignments": {
                "_base_only": {"instances": ["a", "b", "c"]},
                "special": {"instances": ["d"]},
            },
        }
        context = _extract_tier_c_context(tier_c)
        assert "2 classes" in context
        assert "``_base_only``: 3 instances" in context
        assert "``special``: 1 instances" in context

    def test_empty_tier_c(self) -> None:
        context = _extract_tier_c_context({})
        assert "no per-entity scalar variance" in context

    def test_no_phone_book_schema(self) -> None:
        tier_c = {"instance_data": {"schema": [], "records": {}}}
        context = _extract_tier_c_context(tier_c)
        assert "no per-entity scalar variance" in context


class TestValidateLlmResponse:
    def test_valid_response(self) -> None:
        yaml_str = textwrap.dedent("""\
            subjects:
            - name: bgp
              include_paths:
              - "router.bgp.**"
        """)
        result = _validate_llm_response(yaml_str)
        assert "subjects" in result
        assert result["subjects"][0]["name"] == "bgp"

    def test_missing_subjects(self) -> None:
        with pytest.raises(ValueError, match="missing required 'subjects'"):
            _validate_llm_response("version: 1\n")

    def test_missing_name(self) -> None:
        yaml_str = textwrap.dedent("""\
            subjects:
            - include_paths:
              - "**"
        """)
        with pytest.raises(ValueError, match="must have a 'name'"):
            _validate_llm_response(yaml_str)

    def test_empty_include_paths(self) -> None:
        yaml_str = textwrap.dedent("""\
            subjects:
            - name: bgp
              include_paths: []
        """)
        with pytest.raises(ValueError, match="non-empty 'include_paths'"):
            _validate_llm_response(yaml_str)


class TestBuildSpec:
    def test_builds_spec_with_related_paths(self) -> None:
        llm_result = {
            "subjects": [
                {
                    "name": "bgp",
                    "description": "BGP config",
                    "include_paths": ["router.bgp.**"],
                    "related_paths": [
                        {"path": "hostname", "reason": "identity"},
                    ],
                    "example_questions": ["What AS?"],
                },
            ],
        }
        spec = _build_spec("test-type", llm_result)
        assert isinstance(spec, ProjectionSpec)
        assert spec.source_type == "test-type"
        assert spec.generated_by == "decoct-infer"
        assert len(spec.subjects) == 1
        assert spec.subjects[0].name == "bgp"
        assert spec.subjects[0].related_paths[0].path == "hostname"

    def test_handles_string_related_paths(self) -> None:
        llm_result = {
            "subjects": [
                {
                    "name": "bgp",
                    "include_paths": ["router.bgp.**"],
                    "related_paths": ["hostname"],
                },
            ],
        }
        spec = _build_spec("test-type", llm_result)
        assert spec.subjects[0].related_paths[0].path == "hostname"


class TestInferProjectionSpec:
    def test_infer_missing_tier_b(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Tier B file not found"):
            infer_projection_spec(tmp_path, "nonexistent")

    @patch("decoct.learn_projections._call_llm")
    def test_infer_success_with_tier_c(self, mock_call: MagicMock, tmp_path: Path) -> None:
        """Tier B + Tier C both present — LLM receives both."""
        from ruamel.yaml import YAML

        yaml = YAML(typ="rt")

        # Write Tier B
        tier_b = {
            "meta": {"entity_type": "test-type", "total_instances": 2},
            "base_class": {"router.bgp.65002": "value", "hostname": "test"},
            "classes": {},
        }
        classes_file = tmp_path / "test-type_classes.yaml"
        with classes_file.open("w") as f:
            yaml.dump(tier_b, f)

        # Write Tier C
        tier_c = {
            "instance_data": {
                "schema": ["hostname", "router.bgp.router-id"],
                "records": {
                    "device-01": ["device-01", "10.0.0.1"],
                    "device-02": ["device-02", "10.0.0.2"],
                },
            },
            "class_assignments": {"_base_only": {"instances": ["device-01", "device-02"]}},
        }
        instances_file = tmp_path / "test-type_instances.yaml"
        with instances_file.open("w") as f:
            yaml.dump(tier_c, f)

        mock_call.return_value = {
            "subjects": [
                {
                    "name": "bgp",
                    "description": "BGP",
                    "include_paths": ["router.bgp.**"],
                    "related_paths": [{"path": "hostname", "reason": "id"}],
                    "example_questions": ["What AS?"],
                },
            ],
        }

        progress_msgs: list[str] = []
        spec = infer_projection_spec(
            tmp_path, "test-type",
            on_progress=progress_msgs.append,
        )

        assert isinstance(spec, ProjectionSpec)
        assert spec.source_type == "test-type"
        assert len(spec.subjects) == 1
        assert spec.subjects[0].name == "bgp"
        assert len(progress_msgs) > 0

        # Verify _call_llm received tier_c_context
        call_args = mock_call.call_args
        tier_c_context_arg = call_args[0][1]  # second positional arg
        assert "router.bgp.router-id" in tier_c_context_arg
        assert "2 per-entity variable attributes" in tier_c_context_arg

    @patch("decoct.learn_projections._call_llm")
    def test_infer_without_tier_c(self, mock_call: MagicMock, tmp_path: Path) -> None:
        """Tier B only — degrades gracefully without Tier C."""
        from ruamel.yaml import YAML

        yaml = YAML(typ="rt")
        tier_b = {
            "meta": {"entity_type": "test-type", "total_instances": 2},
            "base_class": {"router.bgp.65002": "value"},
            "classes": {},
        }
        classes_file = tmp_path / "test-type_classes.yaml"
        with classes_file.open("w") as f:
            yaml.dump(tier_b, f)

        mock_call.return_value = {
            "subjects": [
                {
                    "name": "bgp",
                    "include_paths": ["router.bgp.**"],
                },
            ],
        }

        spec = infer_projection_spec(tmp_path, "test-type")

        assert isinstance(spec, ProjectionSpec)
        assert len(spec.subjects) == 1

        # Verify _call_llm received fallback context
        call_args = mock_call.call_args
        tier_c_context_arg = call_args[0][1]
        assert "No Tier C data available" in tier_c_context_arg
