"""Tests for XML format detection and conversion in formats.py."""

from pathlib import Path

from ruamel.yaml.comments import CommentedMap, CommentedSeq

from decoct.formats import detect_format, load_input, xml_to_commented_map


class TestDetectFormatXml:
    """XML extension detection."""

    def test_xml(self, tmp_path: Path) -> None:
        assert detect_format(tmp_path / "config.xml") == "xml"

    def test_xsl(self, tmp_path: Path) -> None:
        assert detect_format(tmp_path / "style.xsl") == "xml"

    def test_xslt(self, tmp_path: Path) -> None:
        assert detect_format(tmp_path / "transform.xslt") == "xml"

    def test_plist(self, tmp_path: Path) -> None:
        assert detect_format(tmp_path / "info.plist") == "xml"

    def test_xhtml(self, tmp_path: Path) -> None:
        assert detect_format(tmp_path / "page.xhtml") == "xml"

    def test_yaml_unchanged(self, tmp_path: Path) -> None:
        assert detect_format(tmp_path / "config.yaml") == "yaml"


class TestXmlToCommentedMap:
    """xml_to_commented_map conversion."""

    def test_simple_element(self) -> None:
        xml = "<root><child>text</child></root>"
        cm = xml_to_commented_map(xml)
        assert isinstance(cm, CommentedMap)
        assert "root" in cm
        assert isinstance(cm["root"], CommentedMap)
        assert cm["root"]["child"] == "text"

    def test_attributes(self) -> None:
        xml = '<server host="localhost" port="8080"/>'
        cm = xml_to_commented_map(xml)
        assert cm["server"]["@host"] == "localhost"
        assert cm["server"]["@port"] == "8080"

    def test_attributes_sorted(self) -> None:
        xml = '<server port="8080" host="localhost"/>'
        cm = xml_to_commented_map(xml)
        keys = list(cm["server"].keys())
        assert keys[0] == "@host"
        assert keys[1] == "@port"

    def test_nested_elements(self) -> None:
        xml = "<root><parent><child>val</child></parent></root>"
        cm = xml_to_commented_map(xml)
        assert cm["root"]["parent"]["child"] == "val"

    def test_repeated_elements(self) -> None:
        xml = "<root><item>a</item><item>b</item><item>c</item></root>"
        cm = xml_to_commented_map(xml)
        items = cm["root"]["item"]
        assert isinstance(items, CommentedSeq)
        assert list(items) == ["a", "b", "c"]

    def test_namespace_stripping(self) -> None:
        xml = '<root xmlns="http://example.com"><child>val</child></root>'
        cm = xml_to_commented_map(xml)
        assert "root" in cm
        assert cm["root"]["child"] == "val"

    def test_text_only_leaf(self) -> None:
        xml = "<config><name>myapp</name></config>"
        cm = xml_to_commented_map(xml)
        assert cm["config"]["name"] == "myapp"

    def test_mixed_content(self) -> None:
        xml = "<root>hello<child>world</child></root>"
        cm = xml_to_commented_map(xml)
        assert cm["root"]["_text"] == "hello"
        assert cm["root"]["child"] == "world"

    def test_empty_element(self) -> None:
        xml = "<root><empty/></root>"
        cm = xml_to_commented_map(xml)
        assert cm["root"]["empty"] == ""

    def test_attributes_with_children(self) -> None:
        xml = '<server name="web"><port>80</port></server>'
        cm = xml_to_commented_map(xml)
        assert cm["server"]["@name"] == "web"
        assert cm["server"]["port"] == "80"

    def test_complex_structure(self) -> None:
        xml = """<config>
            <database host="db.example.com" port="5432">
                <name>mydb</name>
                <pool>10</pool>
            </database>
            <server>
                <listen>0.0.0.0</listen>
                <port>8080</port>
            </server>
        </config>"""
        cm = xml_to_commented_map(xml)
        db = cm["config"]["database"]
        assert db["@host"] == "db.example.com"
        assert db["@port"] == "5432"
        assert db["name"] == "mydb"
        assert db["pool"] == "10"
        assert cm["config"]["server"]["listen"] == "0.0.0.0"

    def test_repeated_objects(self) -> None:
        xml = """<servers>
            <server><host>a</host><port>80</port></server>
            <server><host>b</host><port>81</port></server>
        </servers>"""
        cm = xml_to_commented_map(xml)
        servers = cm["servers"]["server"]
        assert isinstance(servers, CommentedSeq)
        assert len(servers) == 2
        assert servers[0]["host"] == "a"
        assert servers[1]["host"] == "b"


class TestLoadInputXml:
    """load_input for XML files."""

    def test_load_xml_file(self, tmp_path: Path) -> None:
        xml_file = tmp_path / "config.xml"
        xml_file.write_text("<config><name>test</name></config>")
        doc, raw = load_input(xml_file)
        assert isinstance(doc, CommentedMap)
        assert doc["config"]["name"] == "test"
        assert "<config>" in raw
