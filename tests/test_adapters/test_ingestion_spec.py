"""Unit tests for ingestion spec loader and matcher."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from decoct.adapters.ingestion_models import (
    CompositePathSpec,
    IngestionEntry,
    IngestionSpec,
    RelationshipHintSpec,
)
from decoct.adapters.ingestion_spec import load_ingestion_spec, match_entry


def _write_spec(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "spec.yaml"
    p.write_text(textwrap.dedent(content))
    return p


class TestLoadIngestionSpec:
    def test_load_valid_spec(self, tmp_path: Path) -> None:
        p = _write_spec(tmp_path, """\
            version: 1
            adapter: hybrid-infra
            generated_by: test
            entries:
            - file_pattern: "pg-*"
              platform: postgresql
              description: "PostgreSQL config"
            - file_pattern: "package-json-*"
              platform: package-json
              composite_paths:
              - path: dependencies
                kind: map
                reason: "Package deps"
              relationship_hints:
              - source_field: name
                target_field: name
                label: depends-on
        """)
        spec = load_ingestion_spec(p)
        assert spec.version == 1
        assert spec.adapter == "hybrid-infra"
        assert spec.generated_by == "test"
        assert len(spec.entries) == 2

        e0 = spec.entries[0]
        assert e0.file_pattern == "pg-*"
        assert e0.platform == "postgresql"
        assert e0.description == "PostgreSQL config"
        assert e0.composite_paths == []
        assert e0.relationship_hints == []

        e1 = spec.entries[1]
        assert len(e1.composite_paths) == 1
        assert e1.composite_paths[0] == CompositePathSpec(
            path="dependencies", kind="map", reason="Package deps",
        )
        assert len(e1.relationship_hints) == 1
        assert e1.relationship_hints[0] == RelationshipHintSpec(
            source_field="name", target_field="name", label="depends-on",
        )

    def test_load_invalid_version(self, tmp_path: Path) -> None:
        p = _write_spec(tmp_path, """\
            version: 2
            adapter: hybrid-infra
            entries: []
        """)
        with pytest.raises(ValueError, match="Unsupported ingestion spec version"):
            load_ingestion_spec(p)

    def test_load_missing_required_fields(self, tmp_path: Path) -> None:
        # Missing platform
        p = _write_spec(tmp_path, """\
            version: 1
            adapter: hybrid-infra
            entries:
            - file_pattern: "pg-*"
        """)
        with pytest.raises(ValueError, match="must have a non-empty 'platform'"):
            load_ingestion_spec(p)

    def test_load_missing_file_pattern(self, tmp_path: Path) -> None:
        p = _write_spec(tmp_path, """\
            version: 1
            adapter: hybrid-infra
            entries:
            - platform: postgresql
        """)
        with pytest.raises(ValueError, match="must have a non-empty 'file_pattern'"):
            load_ingestion_spec(p)

    def test_load_invalid_composite_kind(self, tmp_path: Path) -> None:
        p = _write_spec(tmp_path, """\
            version: 1
            adapter: hybrid-infra
            entries:
            - file_pattern: "pg-*"
              platform: postgresql
              composite_paths:
              - path: foo
                kind: invalid
        """)
        with pytest.raises(ValueError, match="kind must be 'map' or 'list'"):
            load_ingestion_spec(p)

    def test_load_missing_adapter(self, tmp_path: Path) -> None:
        p = _write_spec(tmp_path, """\
            version: 1
            entries: []
        """)
        with pytest.raises(ValueError, match="non-empty 'adapter'"):
            load_ingestion_spec(p)


class TestMatchEntry:
    @pytest.fixture()
    def spec(self) -> list[IngestionEntry]:
        return [
            IngestionEntry(file_pattern="pg-*", platform="postgresql"),
            IngestionEntry(file_pattern="maria-*", platform="mariadb"),
            IngestionEntry(
                file_pattern="package-json-*",
                platform="package-json",
                composite_paths=[
                    CompositePathSpec(path="dependencies", kind="map"),
                ],
            ),
            IngestionEntry(
                file_pattern="related-*",
                platform="related",
                relationship_hints=[
                    RelationshipHintSpec(
                        source_field="ref", target_field="id", label="refers-to",
                    ),
                ],
            ),
        ]

    def _make_spec(self, entries: list[IngestionEntry]) -> IngestionSpec:
        return IngestionSpec(version=1, adapter="test", entries=entries)

    def test_match_entry_exact(self, spec: list[IngestionEntry]) -> None:
        s = self._make_spec(spec)
        result = match_entry(s, "pg-prod-primary")
        assert result is not None
        assert result.platform == "postgresql"

    def test_match_entry_no_match(self, spec: list[IngestionEntry]) -> None:
        s = self._make_spec(spec)
        result = match_entry(s, "compose-prod")
        assert result is None

    def test_match_entry_first_wins(self) -> None:
        entries = [
            IngestionEntry(file_pattern="pg-*", platform="first"),
            IngestionEntry(file_pattern="pg-*", platform="second"),
        ]
        s = self._make_spec(entries)
        result = match_entry(s, "pg-dev")
        assert result is not None
        assert result.platform == "first"

    def test_match_with_composite_paths(self, spec: list[IngestionEntry]) -> None:
        s = self._make_spec(spec)
        result = match_entry(s, "package-json-web-app")
        assert result is not None
        assert result.platform == "package-json"
        assert len(result.composite_paths) == 1
        assert result.composite_paths[0].kind == "map"

    def test_match_with_relationship_hints(self, spec: list[IngestionEntry]) -> None:
        s = self._make_spec(spec)
        result = match_entry(s, "related-foo")
        assert result is not None
        assert len(result.relationship_hints) == 1
        assert result.relationship_hints[0].label == "refers-to"
