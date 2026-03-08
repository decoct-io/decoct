"""Tests for the drop-fields pass."""

from pathlib import Path

from ruamel.yaml import YAML

from decoct.passes.drop_fields import DropFieldsPass, _path_matches, drop_fields

FIXTURES = Path(__file__).parent.parent / "fixtures" / "yaml"


def _load_yaml(path: Path) -> dict:
    yaml = YAML(typ="rt")
    return yaml.load(path)


class TestPathMatches:
    def test_exact_match(self) -> None:
        assert _path_matches("metadata.name", "metadata.name")

    def test_single_wildcard(self) -> None:
        assert _path_matches("services.web.restart", "services.*.restart")

    def test_single_wildcard_no_match(self) -> None:
        assert not _path_matches("services.web.ports.http", "services.*.restart")

    def test_double_wildcard_any_depth(self) -> None:
        assert _path_matches("metadata.uid", "**.uid")
        assert _path_matches("spec.template.metadata.labels.app", "**.labels.app")

    def test_double_wildcard_prefix(self) -> None:
        assert _path_matches("a.b.c.uuid", "**.uuid")

    def test_double_wildcard_middle(self) -> None:
        assert _path_matches("metadata.labels.app", "metadata.**.app")

    def test_no_match(self) -> None:
        assert not _path_matches("metadata.name", "spec.name")

    def test_double_wildcard_matches_zero_segments(self) -> None:
        assert _path_matches("metadata.uid", "metadata.**.uid")

    def test_combined_wildcards(self) -> None:
        assert _path_matches("services.web.labels.app", "services.*.**.app")


class TestDropFields:
    def test_drop_by_exact_path(self) -> None:
        doc = _load_yaml(FIXTURES / "deep-nested.yaml")
        count = drop_fields(doc, ["metadata.managedFields"])
        assert "managedFields" not in doc["metadata"]
        assert count == 1

    def test_drop_by_double_wildcard(self) -> None:
        doc = _load_yaml(FIXTURES / "deep-nested.yaml")
        count = drop_fields(doc, ["**.uuid"])
        assert "uid" in doc["metadata"]  # uid != uuid
        assert "uuid" not in doc["spec"]["template"]["spec"]["containers"][0]
        assert count == 1

    def test_drop_multiple_patterns(self) -> None:
        doc = _load_yaml(FIXTURES / "deep-nested.yaml")
        count = drop_fields(doc, ["metadata.managedFields", "**.uuid", "metadata.resourceVersion"])
        assert "managedFields" not in doc["metadata"]
        assert "resourceVersion" not in doc["metadata"]
        assert count == 3

    def test_drop_preserves_non_matching(self) -> None:
        doc = _load_yaml(FIXTURES / "deep-nested.yaml")
        drop_fields(doc, ["metadata.managedFields"])
        assert doc["metadata"]["name"] == "my-app"
        assert doc["spec"]["replicas"] == 3

    def test_drop_nothing_when_no_match(self) -> None:
        doc = _load_yaml(FIXTURES / "deep-nested.yaml")
        count = drop_fields(doc, ["nonexistent.path"])
        assert count == 0

    def test_drop_with_single_wildcard(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("services:\n  web:\n    restart: always\n  db:\n    restart: unless-stopped\n")
        count = drop_fields(doc, ["services.*.restart"])
        assert "restart" not in doc["services"]["web"]
        assert "restart" not in doc["services"]["db"]
        assert count == 2


class TestDropFieldsPass:
    def test_pass_with_constructor_patterns(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("a: 1\nb: 2\nc: 3\n")
        p = DropFieldsPass(patterns=["b"])
        result = p.run(doc)
        assert "b" not in doc
        assert doc["a"] == 1
        assert result.items_removed == 1

    def test_pass_with_kwargs_patterns(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("a: 1\nb: 2\n")
        p = DropFieldsPass()
        result = p.run(doc, drop_patterns=["b"])
        assert "b" not in doc
        assert result.items_removed == 1

    def test_pass_name(self) -> None:
        assert DropFieldsPass.name == "drop-fields"
