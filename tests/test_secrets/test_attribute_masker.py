"""Tests for entity attribute-level secrets masking."""

from __future__ import annotations

import re

from decoct.core.composite_value import CompositeValue
from decoct.core.types import Attribute, Entity
from decoct.secrets.attribute_masker import mask_entity_attributes
from decoct.secrets.detection import REDACTED


def _make_entity(entity_id: str, attrs: dict[str, tuple[str, str]]) -> Entity:
    """Helper: create Entity with string attributes. attrs = {path: (value, type)}."""
    entity = Entity(id=entity_id)
    for path, (value, atype) in attrs.items():
        entity.attributes[path] = Attribute(path=path, value=value, type=atype)
    return entity


class TestStringAttributes:
    def test_path_pattern_detection(self) -> None:
        entity = _make_entity("router-1", {
            "auth.password": ("secret123", "string"),
            "hostname": ("router-1.lab", "string"),
        })
        audit = mask_entity_attributes(entity)
        assert entity.attributes["auth.password"].value == REDACTED
        assert entity.attributes["hostname"].value == "router-1.lab"
        assert len(audit) == 1
        assert audit[0].path == "router-1.auth.password"
        assert audit[0].detection_method == "path_pattern"

    def test_regex_detection(self) -> None:
        entity = _make_entity("server-1", {
            "tls.key": ("-----BEGIN PRIVATE KEY-----\nMIIEv...", "string"),
        })
        audit = mask_entity_attributes(entity, secret_paths=[])
        assert entity.attributes["tls.key"].value == REDACTED
        assert "regex:private_key_block" in audit[0].detection_method

    def test_entropy_detection(self) -> None:
        entity = _make_entity("app-1", {
            "config.api_token_val": ("xK9mP2vL5nR8qW1tY4uI7oA3sD6fG0hJ", "string"),
        })
        audit = mask_entity_attributes(entity, secret_paths=[])
        assert entity.attributes["config.api_token_val"].value == REDACTED
        assert audit[0].detection_method == "entropy"

    def test_non_secret_preserved(self) -> None:
        entity = _make_entity("switch-1", {
            "interface.name": ("GigabitEthernet0/0/0", "string"),
            "interface.mtu": ("9216", "string"),
            "mgmt.ip": ("10.0.0.1", "string"),
        })
        audit = mask_entity_attributes(entity, secret_paths=[])
        assert entity.attributes["interface.name"].value == "GigabitEthernet0/0/0"
        assert entity.attributes["interface.mtu"].value == "9216"
        assert entity.attributes["mgmt.ip"].value == "10.0.0.1"
        assert len(audit) == 0


class TestCompositeValueMap:
    def test_secrets_in_inner_dict(self) -> None:
        entity = Entity(id="app-1")
        entity.attributes["config"] = Attribute(
            path="config",
            value=CompositeValue.from_map({
                "db": {"host": "localhost", "password": "s3cret"},
                "cache": {"host": "redis.local", "auth": "normal"},
            }),
            type="composite_template_ref",
        )
        audit = mask_entity_attributes(entity)
        data = entity.attributes["config"].value.data
        assert data["db"]["password"] == REDACTED
        assert data["db"]["host"] == "localhost"
        assert len(audit) == 1

    def test_nested_composite_map(self) -> None:
        entity = Entity(id="svc-1")
        entity.attributes["nested"] = Attribute(
            path="nested",
            value=CompositeValue.from_map({
                "level1": {"level2": {"api_key": "secret_val"}},
            }),
            type="composite_template_ref",
        )
        mask_entity_attributes(entity)
        data = entity.attributes["nested"].value.data
        assert data["level1"]["level2"]["api_key"] == REDACTED


class TestCompositeValueList:
    def test_secrets_in_list_items(self) -> None:
        entity = Entity(id="fw-1")
        entity.attributes["rules"] = Attribute(
            path="rules",
            value=CompositeValue.from_list([
                {"name": "allow-web", "password": "rule_secret"},
                {"name": "deny-all"},
            ]),
            type="composite_template_ref",
        )
        mask_entity_attributes(entity)
        data = entity.attributes["rules"].value.data
        assert data[0]["password"] == REDACTED
        assert data[0]["name"] == "allow-web"
        assert data[1]["name"] == "deny-all"

    def test_string_items_in_list(self) -> None:
        entity = Entity(id="app-1")
        entity.attributes["env"] = Attribute(
            path="env",
            value=CompositeValue.from_list([
                "AKIAIOSFODNN7EXAMPLE",
                "normal_value",
            ]),
            type="composite_template_ref",
        )
        mask_entity_attributes(entity, secret_paths=[])
        data = entity.attributes["env"].value.data
        assert data[0] == REDACTED
        assert data[1] == "normal_value"


class TestExtraValuePatterns:
    def test_iosxr_key_7(self) -> None:
        patterns = [("iosxr_key_7", re.compile(r"\bkey\s+7\s+\S+"))]
        entity = _make_entity("rtr-1", {
            "tacacs.line": ("key 7 094F471A1A0A", "string"),
        })
        audit = mask_entity_attributes(entity, secret_paths=[], extra_value_patterns=patterns)
        assert entity.attributes["tacacs.line"].value == REDACTED
        # May be caught by core regex (cisco_type7) or extra pattern — either is correct
        assert len(audit) == 1

    def test_extra_pattern_when_core_misses(self) -> None:
        """Extra value patterns catch things core detection misses."""
        patterns = [("iosxr_key_string", re.compile(r"\bkey-string\s+\S+"))]
        entity = _make_entity("rtr-1", {
            "auth.line": ("key-string MyPlainKey", "string"),
        })
        audit = mask_entity_attributes(entity, secret_paths=[], extra_value_patterns=patterns)
        assert entity.attributes["auth.line"].value == REDACTED
        assert "value_pattern:iosxr_key_string" in audit[0].detection_method

    def test_iosxr_secret_encrypted(self) -> None:
        patterns = [("iosxr_secret_encrypted", re.compile(r"\bsecret\s+[057]\s+\S+"))]
        entity = _make_entity("rtr-2", {
            "radius.config": ("secret 5 $1$abc$def", "string"),
        })
        mask_entity_attributes(entity, secret_paths=[], extra_value_patterns=patterns)
        assert entity.attributes["radius.config"].value == REDACTED

    def test_no_extra_patterns(self) -> None:
        entity = _make_entity("rtr-3", {
            "tacacs.line": ("key 7 094F471A1A0A", "string"),
        })
        # Without extra patterns, the value might still be caught by other methods
        # but not by value_pattern
        audit = mask_entity_attributes(entity, secret_paths=[])
        methods = [e.detection_method for e in audit]
        assert not any("value_pattern" in m for m in methods)


class TestAuditPaths:
    def test_audit_paths_prefixed_with_entity_id(self) -> None:
        entity = _make_entity("my-device", {
            "auth.password": ("s3cret", "string"),
        })
        audit = mask_entity_attributes(entity)
        assert audit[0].path == "my-device.auth.password"

    def test_audit_never_contains_values(self) -> None:
        entity = _make_entity("dev-1", {
            "auth.password": ("SuperS3cretValue", "string"),
        })
        audit = mask_entity_attributes(entity)
        for entry in audit:
            assert "SuperS3cret" not in entry.path
            assert "SuperS3cret" not in entry.detection_method
