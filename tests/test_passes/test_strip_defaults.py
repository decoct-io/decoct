"""Tests for the strip-defaults pass."""

from pathlib import Path

from ruamel.yaml import YAML

from decoct.passes.strip_defaults import StripDefaultsPass, strip_defaults
from decoct.schemas import Schema, load_schema

YAML_FIXTURES = Path(__file__).parent.parent / "fixtures" / "yaml"
SCHEMA_FIXTURES = Path(__file__).parent.parent / "fixtures" / "schemas"


def _load_yaml(path: Path) -> dict:
    yaml = YAML(typ="rt")
    return yaml.load(path)


class TestStripDefaults:
    def setup_method(self) -> None:
        self.schema = load_schema(SCHEMA_FIXTURES / "docker-compose.yaml")

    def test_strips_matching_defaults(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "with-defaults.yaml")
        count = strip_defaults(doc, self.schema)
        # restart: "no" is the default — should be stripped from web
        assert "restart" not in doc["services"]["web"]
        # restart: always is NOT the default — should be preserved
        assert doc["services"]["db"]["restart"] == "always"
        assert count > 0

    def test_strips_network_mode_default(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "with-defaults.yaml")
        strip_defaults(doc, self.schema)
        assert "network_mode" not in doc["services"]["web"]
        assert "network_mode" not in doc["services"]["db"]

    def test_strips_boolean_defaults(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "with-defaults.yaml")
        strip_defaults(doc, self.schema)
        # privileged: false is default — stripped
        assert "privileged" not in doc["services"]["web"]
        # read_only: true is NOT default (default is false) — preserved
        assert doc["services"]["web"]["read_only"] is True

    def test_preserves_non_default_values(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "with-defaults.yaml")
        strip_defaults(doc, self.schema)
        assert doc["services"]["web"]["image"] == "nginx:1.25.3"
        assert doc["services"]["web"]["ports"][0] == "8080:80"
        assert doc["services"]["db"]["image"] == "postgres:16"

    def test_applies_drop_patterns(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "with-defaults.yaml")
        strip_defaults(doc, self.schema)
        # Schema has drop_patterns: ["**.uuid", "**.managedFields"]
        assert "managedFields" not in doc.get("metadata", {})

    def test_applies_system_managed(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "with-defaults.yaml")
        strip_defaults(doc, self.schema)
        # Schema has system_managed: ["**.creationTimestamp", "**.resourceVersion"]
        assert "creationTimestamp" not in doc.get("metadata", {})
        assert "resourceVersion" not in doc.get("metadata", {})

    def test_preserves_metadata_name(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "with-defaults.yaml")
        strip_defaults(doc, self.schema)
        assert doc["metadata"]["name"] == "my-app"


class TestStripDefaultsConfidence:
    def test_skip_low_confidence(self) -> None:
        schema = Schema(
            platform="test",
            source="test",
            confidence="low",
            defaults={"key": "value"},
        )
        yaml = YAML(typ="rt")
        doc = yaml.load("key: value\n")
        count = strip_defaults(doc, schema, skip_low_confidence=True)
        assert doc["key"] == "value"
        assert count == 0

    def test_skip_medium_confidence(self) -> None:
        schema = Schema(
            platform="test",
            source="test",
            confidence="medium",
            defaults={"key": "value"},
        )
        yaml = YAML(typ="rt")
        doc = yaml.load("key: value\n")
        count = strip_defaults(doc, schema, skip_low_confidence=True)
        assert doc["key"] == "value"
        assert count == 0

    def test_strips_high_confidence(self) -> None:
        schema = Schema(
            platform="test",
            source="test",
            confidence="high",
            defaults={"key": "value"},
        )
        yaml = YAML(typ="rt")
        doc = yaml.load("key: value\n")
        count = strip_defaults(doc, schema, skip_low_confidence=True)
        assert "key" not in doc
        assert count == 1

    def test_strips_low_when_not_skipping(self) -> None:
        schema = Schema(
            platform="test",
            source="test",
            confidence="low",
            defaults={"key": "value"},
        )
        yaml = YAML(typ="rt")
        doc = yaml.load("key: value\n")
        count = strip_defaults(doc, schema, skip_low_confidence=False)
        assert "key" not in doc
        assert count == 1


class TestStripDefaultsPass:
    def test_pass_ordering(self) -> None:
        assert "strip-secrets" in StripDefaultsPass.run_after
        assert "strip-comments" in StripDefaultsPass.run_after

    def test_pass_with_no_schema(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("key: value\n")
        p = StripDefaultsPass()
        result = p.run(doc)
        assert doc["key"] == "value"
        assert result.items_removed == 0

    def test_pass_with_schema(self) -> None:
        schema = Schema(
            platform="test",
            source="test",
            confidence="authoritative",
            defaults={"key": "default_val"},
        )
        yaml = YAML(typ="rt")
        doc = yaml.load("key: default_val\nother: keep\n")
        p = StripDefaultsPass(schema=schema)
        result = p.run(doc)
        assert "key" not in doc
        assert doc["other"] == "keep"
        assert result.items_removed == 1

    def test_pass_name(self) -> None:
        assert StripDefaultsPass.name == "strip-defaults"


class TestStripDefaultsComprehensive:
    """Tests against the comprehensive docker-compose-full schema and realistic fixtures."""

    def setup_method(self) -> None:
        self.schema = load_schema(SCHEMA_FIXTURES / "docker-compose-full.yaml")

    def test_strips_healthcheck_interval_default(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("services:\n  web:\n    healthcheck:\n      test: curl http://localhost\n      interval: 30s\n")
        strip_defaults(doc, self.schema)
        assert "interval" not in doc["services"]["web"]["healthcheck"]

    def test_strips_logging_driver_default(self) -> None:
        yaml = YAML(typ="rt")
        yaml_str = (
            "services:\n  web:\n    logging:\n"
            "      driver: json-file\n      options:\n        max-size: 10m\n"
        )
        doc = yaml.load(yaml_str)
        strip_defaults(doc, self.schema)
        assert "driver" not in doc["services"]["web"]["logging"]
        # Non-default options preserved
        assert doc["services"]["web"]["logging"]["options"]["max-size"] == "10m"

    def test_strips_deploy_replicas_default(self) -> None:
        yaml = YAML(typ="rt")
        yaml_str = (
            "services:\n  web:\n    deploy:\n"
            "      replicas: 1\n      resources:\n        limits:\n          memory: 512M\n"
        )
        doc = yaml.load(yaml_str)
        strip_defaults(doc, self.schema)
        assert "replicas" not in doc["services"]["web"]["deploy"]
        assert doc["services"]["web"]["deploy"]["resources"]["limits"]["memory"] == "512M"

    def test_preserves_non_default_healthcheck(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("services:\n  web:\n    healthcheck:\n      timeout: 10s\n      interval: 15s\n")
        strip_defaults(doc, self.schema)
        # timeout: 10s is NOT the default (30s) — preserved
        assert doc["services"]["web"]["healthcheck"]["timeout"] == "10s"
        # interval: 15s is NOT the default (30s) — preserved
        assert doc["services"]["web"]["healthcheck"]["interval"] == "15s"

    def test_realistic_compose_default_strip_count(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "realistic-compose.yaml")
        count = strip_defaults(doc, self.schema)
        # At least some defaults should be found (retries: 3, driver: bridge on networks, etc.)
        assert count >= 5

    def test_strips_network_driver_default(self) -> None:
        yaml = YAML(typ="rt")
        yaml_str = (
            "networks:\n  app-net:\n    driver: bridge\n"
            "    ipam:\n      config:\n        - subnet: 10.0.0.0/24\n"
        )
        doc = yaml.load(yaml_str)
        strip_defaults(doc, self.schema)
        assert "driver" not in doc["networks"]["app-net"]

    def test_strips_init_false_default(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("services:\n  web:\n    init: false\n    image: nginx\n")
        strip_defaults(doc, self.schema)
        assert "init" not in doc["services"]["web"]
        assert doc["services"]["web"]["image"] == "nginx"
