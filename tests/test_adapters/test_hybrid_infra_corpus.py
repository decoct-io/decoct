"""Corpus-level tests: parse all 100 hybrid-infra configs and validate invariants."""

from pathlib import Path

import pytest

from decoct.adapters.hybrid_infra import HybridInfraAdapter
from decoct.core.composite_value import CompositeValue
from decoct.core.entity_graph import EntityGraph
from decoct.formats import detect_format

FIXTURES = Path("tests/fixtures/hybrid-infra/configs")


class TestHybridInfraCorpus:
    """Corpus-level validation across all 100 files."""

    @pytest.fixture(scope="class")
    def corpus(self) -> tuple[EntityGraph, list[Path]]:
        """Parse all 100 files into a single graph."""
        adapter = HybridInfraAdapter()
        graph = EntityGraph()
        files = sorted(FIXTURES.iterdir())
        for f in files:
            parsed = adapter.parse(str(f))
            adapter.extract_entities(parsed, graph)
        return graph, files

    def test_parse_all_100_files(self, corpus: tuple[EntityGraph, list[Path]]) -> None:
        """All 100 files parse without error and produce entities."""
        graph, files = corpus
        assert len(files) == 100
        assert len(graph) == 100

    def test_all_entities_have_attributes(self, corpus: tuple[EntityGraph, list[Path]]) -> None:
        """Every entity has at least one attribute."""
        graph, _ = corpus
        for entity in graph.entities:
            assert len(entity.attributes) >= 1, f"{entity.id}: no attributes"

    def test_no_none_attribute_values(self, corpus: tuple[EntityGraph, list[Path]]) -> None:
        """No attribute has a None value."""
        graph, _ = corpus
        for entity in graph.entities:
            for path, attr in entity.attributes.items():
                if isinstance(attr.value, CompositeValue):
                    continue
                assert attr.value is not None, f"{entity.id}.{path}: None value"

    def test_detect_platform_coverage(self, corpus: tuple[EntityGraph, list[Path]]) -> None:
        """Expected platforms are detected."""
        graph, _ = corpus
        detected_hints: set[str] = set()
        for entity in graph.entities:
            if entity.schema_type_hint:
                detected_hints.add(entity.schema_type_hint)
        expected = {"docker-compose", "ansible-playbook", "cloud-init", "traefik", "prometheus"}
        assert expected <= detected_hints

    def test_yaml_json_ini_distribution(self, corpus: tuple[EntityGraph, list[Path]]) -> None:
        """Verify 54 YAML + 15 JSON + 31 INI format mix."""
        _, files = corpus
        counts: dict[str, int] = {"yaml": 0, "json": 0, "ini": 0}
        for f in files:
            fmt = detect_format(f)
            counts[fmt] += 1
        assert counts["yaml"] == 54
        assert counts["json"] == 15
        assert counts["ini"] == 31
