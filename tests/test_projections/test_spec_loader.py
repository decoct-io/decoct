"""Unit tests for projection spec loader and dumper."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from decoct.projections.models import (
    ProjectionSpec,
    RelatedPath,
    SubjectSpec,
)
from decoct.projections.spec_loader import dump_projection_spec, load_projection_spec


def _write_spec(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "spec.yaml"
    p.write_text(textwrap.dedent(content))
    return p


class TestLoadProjectionSpec:
    def test_load_valid_spec(self, tmp_path: Path) -> None:
        p = _write_spec(tmp_path, """\
            version: 1
            source_type: iosxr-access-pe
            generated_by: test
            subjects:
            - name: bgp
              description: "BGP routing"
              include_paths:
              - "router.bgp.**"
              related_paths:
              - path: hostname
                reason: "Device identity"
              example_questions:
              - "What BGP AS is used?"
        """)
        spec = load_projection_spec(p)
        assert spec.version == 1
        assert spec.source_type == "iosxr-access-pe"
        assert spec.generated_by == "test"
        assert len(spec.subjects) == 1

        s0 = spec.subjects[0]
        assert s0.name == "bgp"
        assert s0.description == "BGP routing"
        assert s0.include_paths == ["router.bgp.**"]
        assert len(s0.related_paths) == 1
        assert s0.related_paths[0] == RelatedPath(path="hostname", reason="Device identity")
        assert s0.example_questions == ["What BGP AS is used?"]

    def test_load_minimal_spec(self, tmp_path: Path) -> None:
        p = _write_spec(tmp_path, """\
            version: 1
            source_type: test-type
            subjects:
            - name: all
              include_paths:
              - "**"
        """)
        spec = load_projection_spec(p)
        assert spec.generated_by == "claude-code"
        assert spec.subjects[0].related_paths == []
        assert spec.subjects[0].example_questions == []

    def test_load_invalid_version(self, tmp_path: Path) -> None:
        p = _write_spec(tmp_path, """\
            version: 2
            source_type: test
            subjects: []
        """)
        with pytest.raises(ValueError, match="Unsupported projection spec version"):
            load_projection_spec(p)

    def test_load_missing_source_type(self, tmp_path: Path) -> None:
        p = _write_spec(tmp_path, """\
            version: 1
            subjects: []
        """)
        with pytest.raises(ValueError, match="non-empty 'source_type'"):
            load_projection_spec(p)

    def test_load_missing_include_paths(self, tmp_path: Path) -> None:
        p = _write_spec(tmp_path, """\
            version: 1
            source_type: test
            subjects:
            - name: empty
        """)
        with pytest.raises(ValueError, match="at least one include_path"):
            load_projection_spec(p)

    def test_load_missing_subject_name(self, tmp_path: Path) -> None:
        p = _write_spec(tmp_path, """\
            version: 1
            source_type: test
            subjects:
            - include_paths:
              - "**"
        """)
        with pytest.raises(ValueError, match="non-empty 'name'"):
            load_projection_spec(p)

    def test_load_not_a_mapping(self, tmp_path: Path) -> None:
        p = _write_spec(tmp_path, "- not a mapping\n")
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            load_projection_spec(p)

    def test_load_multiple_subjects(self, tmp_path: Path) -> None:
        p = _write_spec(tmp_path, """\
            version: 1
            source_type: test
            subjects:
            - name: bgp
              include_paths:
              - "router.bgp.**"
            - name: interfaces
              include_paths:
              - "interface.**"
        """)
        spec = load_projection_spec(p)
        assert len(spec.subjects) == 2
        assert spec.subjects[0].name == "bgp"
        assert spec.subjects[1].name == "interfaces"


class TestDumpProjectionSpec:
    def test_round_trip(self, tmp_path: Path) -> None:
        spec = ProjectionSpec(
            version=1,
            source_type="iosxr-access-pe",
            generated_by="test",
            subjects=[
                SubjectSpec(
                    name="bgp",
                    description="BGP routing",
                    include_paths=["router.bgp.**"],
                    related_paths=[RelatedPath(path="hostname", reason="Device identity")],
                    example_questions=["What BGP AS is used?"],
                ),
            ],
        )
        yaml_str = dump_projection_spec(spec)

        # Write and reload
        p = tmp_path / "roundtrip.yaml"
        p.write_text(yaml_str)
        reloaded = load_projection_spec(p)

        assert reloaded.version == spec.version
        assert reloaded.source_type == spec.source_type
        assert reloaded.generated_by == spec.generated_by
        assert len(reloaded.subjects) == 1
        assert reloaded.subjects[0].name == "bgp"
        assert reloaded.subjects[0].include_paths == ["router.bgp.**"]
        assert reloaded.subjects[0].related_paths[0].path == "hostname"

    def test_dump_minimal(self) -> None:
        spec = ProjectionSpec(
            version=1,
            source_type="test",
            subjects=[
                SubjectSpec(name="all", include_paths=["**"]),
            ],
        )
        yaml_str = dump_projection_spec(spec)
        assert "source_type: test" in yaml_str
        assert "name: all" in yaml_str
