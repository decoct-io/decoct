"""Tests for the keep-fields pass."""

from pathlib import Path

from ruamel.yaml import YAML

from decoct.passes.keep_fields import KeepFieldsPass, keep_fields

FIXTURES = Path(__file__).parent.parent / "fixtures" / "yaml"


def _load_yaml(path: Path) -> dict:
    yaml = YAML(typ="rt")
    return yaml.load(path)


class TestKeepFields:
    def test_keep_exact_path(self) -> None:
        doc = _load_yaml(FIXTURES / "deep-nested.yaml")
        count = keep_fields(doc, ["metadata.name"])
        assert doc["metadata"]["name"] == "my-app"
        assert "labels" not in doc.get("metadata", {})
        assert "spec" not in doc
        assert count > 0

    def test_keep_with_wildcard(self) -> None:
        yaml = YAML(typ="rt")
        content = "services:\n  web:\n    image: nginx\n    restart: always\n  db:\n    image: pg\n    restart: no\n"
        doc = yaml.load(content)
        keep_fields(doc, ["services.*.image"])
        assert doc["services"]["web"]["image"] == "nginx"
        assert doc["services"]["db"]["image"] == "pg"
        assert "restart" not in doc["services"]["web"]
        assert "restart" not in doc["services"]["db"]

    def test_keep_with_double_wildcard(self) -> None:
        doc = _load_yaml(FIXTURES / "deep-nested.yaml")
        keep_fields(doc, ["**.image"])
        # image exists deep in the tree
        assert doc["spec"]["template"]["spec"]["containers"][0]["image"] == "my-app:1.0"
        # top-level metadata should be pruned (no image there)
        assert "metadata" not in doc or len(doc.get("metadata", {})) == 0

    def test_keep_preserves_ancestors(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("a:\n  b:\n    c: 1\n    d: 2\n  e: 3\n")
        keep_fields(doc, ["a.b.c"])
        assert doc["a"]["b"]["c"] == 1
        assert "d" not in doc["a"]["b"]
        assert "e" not in doc["a"]

    def test_keep_preserves_descendants(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("a:\n  b:\n    c: 1\n    d: 2\n  e: 3\n")
        keep_fields(doc, ["a.b"])
        assert doc["a"]["b"]["c"] == 1
        assert doc["a"]["b"]["d"] == 2
        assert "e" not in doc["a"]

    def test_keep_multiple_patterns(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("a: 1\nb: 2\nc: 3\nd: 4\n")
        keep_fields(doc, ["a", "c"])
        assert doc["a"] == 1
        assert doc["c"] == 3
        assert "b" not in doc
        assert "d" not in doc

    def test_keep_nothing_drops_all(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("a: 1\nb: 2\n")
        count = keep_fields(doc, ["nonexistent"])
        assert len(doc) == 0
        assert count == 2


class TestKeepFieldsPass:
    def test_pass_with_constructor_patterns(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("a: 1\nb: 2\nc: 3\n")
        p = KeepFieldsPass(patterns=["a", "c"])
        result = p.run(doc)
        assert "b" not in doc
        assert result.items_removed == 1

    def test_pass_name(self) -> None:
        assert KeepFieldsPass.name == "keep-fields"
