"""Unit tests for LLM-assisted Tier A spec inference (mocked)."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ruamel.yaml import YAML

from decoct.assembly.tier_a_models import TierASpec
from decoct.learn_tier_a import (
    _build_spec,
    _validate_llm_response,
    infer_tier_a_spec,
)


def _write_tier_a(tmp_path: Path) -> None:
    """Write a minimal Tier A file."""
    yaml = YAML(typ="rt")
    tier_a = {
        "types": {
            "test-type": {
                "count": 10,
                "classes": 2,
                "subclasses": 1,
                "tier_b_ref": "test-type_classes.yaml",
                "tier_c_ref": "test-type_instances.yaml",
            },
        },
        "assertions": {
            "test-type": {"base_only_ratio": 0.1, "max_inheritance_depth": 2},
        },
        "topology": {},
    }
    with (tmp_path / "tier_a.yaml").open("w") as f:
        yaml.dump(tier_a, f)


def _write_tier_b(tmp_path: Path) -> None:
    """Write a minimal Tier B file."""
    yaml = YAML(typ="rt")
    tier_b = {
        "meta": {"entity_type": "test-type", "total_instances": 10},
        "base_class": {"hostname": "test", "router.bgp.65002": "value"},
        "classes": {
            "cls1": {
                "inherits": "_base",
                "own_attrs": {"mpls.ldp": "true"},
                "instance_count_inclusive": 5,
            },
        },
    }
    with (tmp_path / "test-type_classes.yaml").open("w") as f:
        yaml.dump(tier_b, f)


class TestValidateLlmResponse:
    def test_valid_response(self) -> None:
        yaml_str = textwrap.dedent("""\
            corpus_description: "A fleet of test routers"
            how_to_use:
            - "Start with Tier A"
            type_descriptions:
              test-type:
                summary: "Test devices"
                key_differentiators:
                - "Has BGP"
        """)
        result = _validate_llm_response(yaml_str)
        assert "corpus_description" in result
        assert result["corpus_description"] == "A fleet of test routers"

    def test_missing_corpus_description(self) -> None:
        yaml_str = textwrap.dedent("""\
            how_to_use:
            - "Start with Tier A"
        """)
        with pytest.raises(ValueError, match="missing required 'corpus_description'"):
            _validate_llm_response(yaml_str)

    def test_not_a_mapping(self) -> None:
        with pytest.raises(ValueError, match="not a YAML mapping"):
            _validate_llm_response("- list item\n")

    def test_type_descriptions_not_mapping(self) -> None:
        yaml_str = textwrap.dedent("""\
            corpus_description: "Test"
            type_descriptions:
            - "not a mapping"
        """)
        with pytest.raises(ValueError, match="'type_descriptions' must be a mapping"):
            _validate_llm_response(yaml_str)

    def test_type_missing_summary(self) -> None:
        yaml_str = textwrap.dedent("""\
            corpus_description: "Test"
            type_descriptions:
              some-type:
                key_differentiators:
                - "something"
        """)
        with pytest.raises(ValueError, match="must have a 'summary'"):
            _validate_llm_response(yaml_str)


class TestBuildSpec:
    def test_builds_spec(self) -> None:
        llm_result = {
            "corpus_description": "A fleet of test routers",
            "how_to_use": ["Start with Tier A", "Load Tier B next"],
            "type_descriptions": {
                "test-type": {
                    "summary": "Test devices at the edge",
                    "key_differentiators": ["Has BGP", "Has MPLS"],
                },
            },
        }
        spec = _build_spec(llm_result)
        assert isinstance(spec, TierASpec)
        assert spec.version == 1
        assert spec.generated_by == "decoct-infer"
        assert spec.corpus_description == "A fleet of test routers"
        assert len(spec.how_to_use) == 2
        assert "test-type" in spec.type_descriptions
        td = spec.type_descriptions["test-type"]
        assert td.summary == "Test devices at the edge"
        assert td.key_differentiators == ["Has BGP", "Has MPLS"]

    def test_handles_minimal_result(self) -> None:
        llm_result = {
            "corpus_description": "Minimal",
            "type_descriptions": {},
        }
        spec = _build_spec(llm_result)
        assert spec.corpus_description == "Minimal"
        assert spec.how_to_use == []
        assert spec.type_descriptions == {}


class TestInferTierASpec:
    def test_infer_missing_tier_a(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Tier A file not found"):
            infer_tier_a_spec(tmp_path)

    @patch("decoct.learn_tier_a._call_llm")
    def test_infer_success(self, mock_call: MagicMock, tmp_path: Path) -> None:
        _write_tier_a(tmp_path)
        _write_tier_b(tmp_path)

        mock_call.return_value = {
            "corpus_description": "A fleet of 10 test routers",
            "how_to_use": ["Start with Tier A for orientation"],
            "type_descriptions": {
                "test-type": {
                    "summary": "Test devices",
                    "key_differentiators": ["Has BGP"],
                },
            },
        }

        progress_msgs: list[str] = []
        spec = infer_tier_a_spec(
            tmp_path,
            on_progress=progress_msgs.append,
        )

        assert isinstance(spec, TierASpec)
        assert spec.corpus_description == "A fleet of 10 test routers"
        assert len(spec.type_descriptions) == 1
        assert spec.type_descriptions["test-type"].summary == "Test devices"
        assert len(progress_msgs) > 0

    @patch("decoct.learn_tier_a._call_llm")
    def test_infer_without_tier_b(self, mock_call: MagicMock, tmp_path: Path) -> None:
        """Should still work even if Tier B files are missing."""
        _write_tier_a(tmp_path)
        # No Tier B file written

        mock_call.return_value = {
            "corpus_description": "A fleet of test routers",
            "type_descriptions": {},
        }

        spec = infer_tier_a_spec(tmp_path)
        assert isinstance(spec, TierASpec)
        assert spec.corpus_description == "A fleet of test routers"
