"""Unit tests for Tier A spec loader and dumper."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from decoct.assembly.tier_a_models import (
    TierASpec,
    TierATypeDescription,
)
from decoct.assembly.tier_a_spec import dump_tier_a_spec, load_tier_a_spec


def _write_spec(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "tier_a_spec.yaml"
    p.write_text(textwrap.dedent(content))
    return p


class TestLoadTierASpec:
    def test_load_valid_spec(self, tmp_path: Path) -> None:
        p = _write_spec(tmp_path, """\
            version: 1
            generated_by: test
            corpus_description: "A fleet of IOS-XR routers"
            how_to_use:
            - "Start with tier_a.yaml for orientation"
            - "Load Tier B for class definitions"
            type_descriptions:
              iosxr-access-pe:
                summary: "Access PE routers at network edge"
                key_differentiators:
                - "Has EVPN configuration"
                - "Multiple customer-facing interfaces"
        """)
        spec = load_tier_a_spec(p)
        assert spec.version == 1
        assert spec.generated_by == "test"
        assert spec.corpus_description == "A fleet of IOS-XR routers"
        assert len(spec.how_to_use) == 2
        assert "iosxr-access-pe" in spec.type_descriptions

        td = spec.type_descriptions["iosxr-access-pe"]
        assert td.summary == "Access PE routers at network edge"
        assert len(td.key_differentiators) == 2

    def test_load_minimal_spec(self, tmp_path: Path) -> None:
        p = _write_spec(tmp_path, """\
            version: 1
            corpus_description: "Test corpus"
        """)
        spec = load_tier_a_spec(p)
        assert spec.generated_by == "claude-code"
        assert spec.how_to_use == []
        assert spec.type_descriptions == {}

    def test_load_invalid_version(self, tmp_path: Path) -> None:
        p = _write_spec(tmp_path, """\
            version: 2
            corpus_description: "Test"
        """)
        with pytest.raises(ValueError, match="Unsupported Tier A spec version"):
            load_tier_a_spec(p)

    def test_load_missing_corpus_description(self, tmp_path: Path) -> None:
        p = _write_spec(tmp_path, """\
            version: 1
        """)
        with pytest.raises(ValueError, match="non-empty 'corpus_description'"):
            load_tier_a_spec(p)

    def test_load_missing_type_summary(self, tmp_path: Path) -> None:
        p = _write_spec(tmp_path, """\
            version: 1
            corpus_description: "Test"
            type_descriptions:
              some-type:
                key_differentiators:
                - "something"
        """)
        with pytest.raises(ValueError, match="non-empty 'summary'"):
            load_tier_a_spec(p)

    def test_load_not_a_mapping(self, tmp_path: Path) -> None:
        p = _write_spec(tmp_path, "- not a mapping\n")
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            load_tier_a_spec(p)

    def test_load_type_descriptions_not_mapping(self, tmp_path: Path) -> None:
        p = _write_spec(tmp_path, """\
            version: 1
            corpus_description: "Test"
            type_descriptions:
            - "not a mapping"
        """)
        with pytest.raises(ValueError, match="'type_descriptions' must be a mapping"):
            load_tier_a_spec(p)


class TestDumpTierASpec:
    def test_round_trip(self, tmp_path: Path) -> None:
        spec = TierASpec(
            version=1,
            generated_by="test",
            corpus_description="A fleet of IOS-XR routers",
            how_to_use=["Start with tier_a.yaml", "Load Tier B next"],
            type_descriptions={
                "iosxr-access-pe": TierATypeDescription(
                    summary="Access PE routers",
                    key_differentiators=["EVPN config", "Customer-facing"],
                ),
            },
        )
        yaml_str = dump_tier_a_spec(spec)

        # Write and reload
        p = tmp_path / "roundtrip.yaml"
        p.write_text(yaml_str)
        reloaded = load_tier_a_spec(p)

        assert reloaded.version == spec.version
        assert reloaded.generated_by == spec.generated_by
        assert reloaded.corpus_description == spec.corpus_description
        assert reloaded.how_to_use == spec.how_to_use
        assert "iosxr-access-pe" in reloaded.type_descriptions
        td = reloaded.type_descriptions["iosxr-access-pe"]
        assert td.summary == "Access PE routers"
        assert td.key_differentiators == ["EVPN config", "Customer-facing"]

    def test_dump_minimal(self) -> None:
        spec = TierASpec(
            version=1,
            corpus_description="Minimal test",
        )
        yaml_str = dump_tier_a_spec(spec)
        assert "corpus_description: Minimal test" in yaml_str
        assert "version: 1" in yaml_str
