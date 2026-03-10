"""Corpus-level tests for Entra ID / Intune adapter."""

from collections import Counter
from pathlib import Path

from decoct.adapters.entra_intune import EntraIntuneAdapter
from decoct.core.composite_value import CompositeValue
from decoct.core.entity_graph import EntityGraph

FIXTURES = Path("tests/fixtures/entra-intune/resources")


class TestEntraIntuneCorpus:
    """Corpus-level validation across all 88 fixture files."""

    def _parse_all(self) -> EntityGraph:
        adapter = EntraIntuneAdapter()
        graph = EntityGraph()
        for f in sorted(FIXTURES.glob("*.json")):
            adapter.parse_and_extract(str(f), graph)
        return graph

    def test_parse_all_88_files(self) -> None:
        graph = self._parse_all()
        assert len(graph) == 88

    def test_type_distribution(self) -> None:
        graph = self._parse_all()
        types = Counter(e.schema_type_hint for e in graph.entities)
        assert types["entra-conditional-access"] == 20
        assert types["entra-group"] == 25
        assert types["entra-application"] == 12
        assert types["intune-compliance"] == 10
        assert types["intune-device-config"] == 8
        assert types["intune-app-protection"] == 4
        assert types["entra-named-location"] == 6
        assert types["entra-cross-tenant"] == 3
        assert len(types) == 8

    def test_all_have_display_name(self) -> None:
        """Every entity has a displayName-derived ID (non-empty string)."""
        graph = self._parse_all()
        for entity in graph.entities:
            assert entity.id, "Entity has empty ID"
            assert isinstance(entity.id, str)

    def test_no_null_attribute_values(self) -> None:
        """No attribute has a None/null value after filtering."""
        graph = self._parse_all()
        for entity in graph.entities:
            for path, attr in entity.attributes.items():
                if isinstance(attr.value, CompositeValue):
                    continue
                assert attr.value is not None, (
                    f"Entity {entity.id} has None value at path {path}"
                )

    def test_all_have_type_hint(self) -> None:
        """Every entity has a schema_type_hint."""
        graph = self._parse_all()
        for entity in graph.entities:
            assert entity.schema_type_hint is not None, (
                f"Entity {entity.id} has no type hint"
            )

    def test_skip_fields_excluded(self) -> None:
        """Metadata fields (@odata.type, id, timestamps) are not in attributes."""
        graph = self._parse_all()
        skip = {"@odata.type", "id", "createdDateTime", "modifiedDateTime", "deletedDateTime", "renewedDateTime"}
        for entity in graph.entities:
            for field in skip:
                assert field not in entity.attributes, (
                    f"Entity {entity.id} has skip field {field} in attributes"
                )
