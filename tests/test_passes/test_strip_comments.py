"""Tests for the strip-comments pass."""

from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML

from decoct.passes.strip_comments import StripCommentsPass

FIXTURES = Path(__file__).parent.parent / "fixtures" / "yaml"


def _load_yaml(path: Path) -> dict:
    yaml = YAML(typ="rt")
    return yaml.load(path)


def _dump_yaml(doc: dict) -> str:
    yaml = YAML(typ="rt")
    stream = StringIO()
    yaml.dump(doc, stream)
    return stream.getvalue()


class TestStripComments:
    def test_removes_comments_from_fixture(self) -> None:
        doc = _load_yaml(FIXTURES / "commented.yaml")
        result = StripCommentsPass().run(doc)
        output = _dump_yaml(doc)
        assert "#" not in output
        assert result.items_removed > 0

    def test_preserves_data(self) -> None:
        doc = _load_yaml(FIXTURES / "commented.yaml")
        StripCommentsPass().run(doc)
        assert doc["services"]["web"]["image"] == "nginx:1.25.3"
        assert doc["services"]["web"]["restart"] == "always"
        assert doc["services"]["web"]["ports"][0] == "8080:80"
        assert doc["services"]["db"]["environment"]["POSTGRES_DB"] == "myapp"

    def test_no_comments_is_noop(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("key: value\nnested:\n  child: 1\n")
        result = StripCommentsPass().run(doc)
        assert doc["key"] == "value"
        assert doc["nested"]["child"] == 1
        assert result.items_removed == 0

    def test_inline_comments_removed(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("key: value  # inline comment\n")
        StripCommentsPass().run(doc)
        output = _dump_yaml(doc)
        assert "#" not in output
        assert "value" in output

    def test_pass_name(self) -> None:
        assert StripCommentsPass.name == "strip-comments"
