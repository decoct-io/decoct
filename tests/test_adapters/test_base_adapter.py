"""Tests for BaseAdapter concrete implementation (YAML, JSON, INI, XML)."""

from pathlib import Path

from decoct.adapters.base import BaseAdapter, ParseResult
from decoct.core.entity_graph import EntityGraph


class TestBaseAdapterSourceType:
    """BaseAdapter.source_type() returns 'standard'."""

    def test_source_type(self) -> None:
        adapter = BaseAdapter()
        assert adapter.source_type() == "standard"


class TestBaseAdapterParseYaml:
    """BaseAdapter.parse() for YAML files."""

    def test_parse_yaml(self, tmp_path: Path) -> None:
        f = tmp_path / "config.yaml"
        f.write_text("name: test\nport: 8080\n")
        adapter = BaseAdapter()
        result = adapter.parse(str(f))
        assert isinstance(result, ParseResult)
        assert result.format == "yaml"
        assert result.doc["name"] == "test"
        assert result.doc["port"] == 8080

    def test_parse_yml(self, tmp_path: Path) -> None:
        f = tmp_path / "config.yml"
        f.write_text("key: value\n")
        adapter = BaseAdapter()
        result = adapter.parse(str(f))
        assert result.format == "yaml"
        assert result.doc["key"] == "value"


class TestBaseAdapterParseJson:
    """BaseAdapter.parse() for JSON files."""

    def test_parse_json(self, tmp_path: Path) -> None:
        f = tmp_path / "config.json"
        f.write_text('{"name": "test", "port": 8080}')
        adapter = BaseAdapter()
        result = adapter.parse(str(f))
        assert isinstance(result, ParseResult)
        assert result.format == "json"
        assert result.doc["name"] == "test"
        assert result.doc["port"] == 8080


class TestBaseAdapterParseIni:
    """BaseAdapter.parse() for INI files."""

    def test_parse_ini(self, tmp_path: Path) -> None:
        f = tmp_path / "config.ini"
        f.write_text("[database]\nhost = localhost\nport = 5432\n")
        adapter = BaseAdapter()
        result = adapter.parse(str(f))
        assert isinstance(result, ParseResult)
        assert result.format == "ini"
        assert result.doc["database"]["host"] == "localhost"

    def test_parse_space_separated_fallback(self, tmp_path: Path) -> None:
        f = tmp_path / "sshd.conf"
        f.write_text("Port 22\nPermitRootLogin no\n")
        adapter = BaseAdapter()
        result = adapter.parse(str(f))
        assert result.format == "ini"
        assert result.doc["Port"] == 22
        assert result.doc["PermitRootLogin"] is False


class TestBaseAdapterParseXml:
    """BaseAdapter.parse() for XML files."""

    def test_parse_xml(self, tmp_path: Path) -> None:
        f = tmp_path / "config.xml"
        f.write_text("<config><name>test</name><port>8080</port></config>")
        adapter = BaseAdapter()
        result = adapter.parse(str(f))
        assert isinstance(result, ParseResult)
        assert result.format == "xml"
        assert result.doc["config"]["name"] == "test"
        assert result.doc["config"]["port"] == "8080"


class TestBaseAdapterExtractEntities:
    """BaseAdapter.extract_entities() creates proper entities."""

    def test_extract_yaml_entity(self, tmp_path: Path) -> None:
        f = tmp_path / "myserver.yaml"
        f.write_text("hostname: srv01\nport: 443\n")
        adapter = BaseAdapter()
        graph = EntityGraph()
        parsed = adapter.parse(str(f))
        adapter.extract_entities(parsed, graph)
        assert len(graph.entities) == 1
        entity = graph.entities[0]
        assert entity.id == "myserver"
        assert entity.attributes["hostname"].value == "srv01"
        assert entity.attributes["port"].value == "443"

    def test_extract_json_entity(self, tmp_path: Path) -> None:
        f = tmp_path / "app.json"
        f.write_text('{"name": "myapp", "version": "1.0"}')
        adapter = BaseAdapter()
        graph = EntityGraph()
        parsed = adapter.parse(str(f))
        adapter.extract_entities(parsed, graph)
        assert len(graph.entities) == 1
        assert graph.entities[0].attributes["name"].value == "myapp"

    def test_extract_xml_entity(self, tmp_path: Path) -> None:
        f = tmp_path / "service.xml"
        f.write_text("<config><host>web01</host><port>80</port></config>")
        adapter = BaseAdapter()
        graph = EntityGraph()
        parsed = adapter.parse(str(f))
        adapter.extract_entities(parsed, graph)
        assert len(graph.entities) == 1
        entity = graph.entities[0]
        assert entity.id == "service"
        assert entity.attributes["config.host"].value == "web01"


class TestBaseAdapterCollectSourceLeaves:
    """BaseAdapter.collect_source_leaves() walks documents."""

    def test_collect_yaml_leaves(self, tmp_path: Path) -> None:
        f = tmp_path / "test.yaml"
        f.write_text("a: 1\nb: hello\n")
        adapter = BaseAdapter()
        parsed = adapter.parse(str(f))
        result = adapter.collect_source_leaves(parsed)
        assert "test" in result
        leaves = result["test"]
        paths = {p for p, _ in leaves}
        assert "a" in paths
        assert "b" in paths

    def test_collect_xml_leaves(self, tmp_path: Path) -> None:
        f = tmp_path / "test.xml"
        f.write_text("<root><a>1</a><b>hello</b></root>")
        adapter = BaseAdapter()
        parsed = adapter.parse(str(f))
        result = adapter.collect_source_leaves(parsed)
        assert "test" in result
        leaves = result["test"]
        paths = {p for p, _ in leaves}
        assert "root.a" in paths
        assert "root.b" in paths


class TestBaseAdapterIsSubclassable:
    """Verify BaseAdapter can be subclassed by custom adapters."""

    def test_hybrid_infra_is_subclass(self) -> None:
        from decoct.adapters.hybrid_infra import HybridInfraAdapter
        adapter = HybridInfraAdapter()
        assert isinstance(adapter, BaseAdapter)
        assert adapter.source_type() == "hybrid-infra"
