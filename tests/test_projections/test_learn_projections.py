"""Unit tests for LLM-assisted projection spec inference (mocked)."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from decoct.learn_projections import (
    _build_spec,
    _extract_path_prefixes,
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
    def test_infer_success(self, mock_call: MagicMock, tmp_path: Path) -> None:
        # Write a minimal Tier B file
        from ruamel.yaml import YAML

        yaml = YAML(typ="rt")
        tier_b = {
            "meta": {"entity_type": "test-type", "total_instances": 2},
            "base_class": {"router.bgp.65002": "value", "hostname": "test"},
            "classes": {},
        }
        classes_file = tmp_path / "test-type_classes.yaml"
        with classes_file.open("w") as f:
            yaml.dump(tier_b, f)

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
