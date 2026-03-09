"""Tests for JSON input support — TDD (initially failing until formats.py is implemented)."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from decoct.formats import detect_format, detect_platform, json_to_commented_map, load_input

FIXTURES = Path(__file__).parent / "fixtures"
JSON_FIXTURES = FIXTURES / "json"
YAML_FIXTURES = FIXTURES / "yaml"


class TestJsonToCommentedMap:
    def test_nested_objects_become_commented_map(self) -> None:
        data = {"services": {"web": {"image": "nginx:1.25.3"}}}
        result = json_to_commented_map(data)
        assert isinstance(result, CommentedMap)
        assert isinstance(result["services"], CommentedMap)
        assert isinstance(result["services"]["web"], CommentedMap)

    def test_arrays_become_commented_seq(self) -> None:
        data = {"ports": ["80:80", "443:443"]}
        result = json_to_commented_map(data)
        assert isinstance(result["ports"], CommentedSeq)
        assert result["ports"][0] == "80:80"
        assert result["ports"][1] == "443:443"

    def test_preserves_scalar_types(self) -> None:
        data = {"count": 42, "ratio": 3.14, "enabled": True, "value": None}
        result = json_to_commented_map(data)
        assert result["count"] == 42
        assert isinstance(result["count"], int)
        assert result["ratio"] == 3.14
        assert isinstance(result["ratio"], float)
        assert result["enabled"] is True
        assert result["value"] is None

    def test_roundtrips_to_yaml(self) -> None:
        data = {"services": {"web": {"image": "nginx:1.25.3", "ports": ["80:80"]}}}
        doc = json_to_commented_map(data)
        yaml = YAML(typ="rt")
        stream = StringIO()
        yaml.dump(doc, stream)
        output = stream.getvalue()
        assert "services:" in output
        assert "nginx:1.25.3" in output
        assert "80:80" in output

    def test_nested_arrays_of_objects(self) -> None:
        data = {"items": [{"name": "a"}, {"name": "b"}]}
        result = json_to_commented_map(data)
        assert isinstance(result["items"], CommentedSeq)
        assert isinstance(result["items"][0], CommentedMap)
        assert result["items"][0]["name"] == "a"


class TestDetectFormat:
    def test_json_extension(self) -> None:
        assert detect_format(Path("config.json")) == "json"

    def test_yaml_extension(self) -> None:
        assert detect_format(Path("config.yaml")) == "yaml"

    def test_yml_extension(self) -> None:
        assert detect_format(Path("config.yml")) == "yaml"

    def test_unknown_defaults_to_yaml(self) -> None:
        assert detect_format(Path("config.txt")) == "yaml"


class TestLoadInput:
    def test_loads_json_file(self) -> None:
        doc, raw = load_input(JSON_FIXTURES / "simple-config.json")
        assert isinstance(doc, CommentedMap)
        assert "services" in doc
        assert doc["services"]["web"]["image"] == "nginx:1.25.3"

    def test_loads_yaml_file(self) -> None:
        doc, raw = load_input(YAML_FIXTURES / "with-defaults.yaml")
        assert isinstance(doc, CommentedMap)
        assert "services" in doc

    def test_json_file_through_pipeline(self) -> None:
        """Verify that strip-secrets works on a JSON-loaded document."""
        import tempfile

        from decoct.passes.strip_secrets import StripSecretsPass
        data = {"db": {"password": "super_secret_123", "host": "localhost"}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            tmp_path = Path(f.name)

        try:
            doc, _raw = load_input(tmp_path)
            p = StripSecretsPass()
            result = p.run(doc)
            assert doc["db"]["password"] == "[REDACTED]"
            assert doc["db"]["host"] == "localhost"
            assert result.items_removed > 0
        finally:
            tmp_path.unlink()

    def test_cloud_init_detected(self) -> None:
        doc, _raw = load_input(YAML_FIXTURES / "cloud-init-config.yaml")
        assert detect_platform(doc) == "cloud-init"

    def test_kubernetes_detected(self) -> None:
        doc, _raw = load_input(YAML_FIXTURES / "kubernetes-deployment.yaml")
        assert detect_platform(doc) == "kubernetes"

    def test_ansible_detected(self) -> None:
        doc, _raw = load_input(YAML_FIXTURES / "ansible-playbook.yaml")
        assert detect_platform(doc) == "ansible-playbook"

    def test_tfstate_loads_as_commented_map(self) -> None:
        doc, raw = load_input(JSON_FIXTURES / "tfstate-sample.json")
        assert isinstance(doc, CommentedMap)
        assert doc["version"] == 4
        assert isinstance(doc["resources"], CommentedSeq)
        assert isinstance(doc["resources"][0], CommentedMap)
