"""Tests for document-level secrets masking."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from decoct.secrets.detection import REDACTED
from decoct.secrets.document_masker import mask_document

FIXTURES = Path(__file__).parent.parent / "fixtures" / "yaml"


def _load_yaml(path: Path) -> dict:
    yaml = YAML(typ="rt")
    return yaml.load(path)


class TestDocumentMaskerFixture:
    """Verify mask_document redacts secrets correctly in document trees."""

    def setup_method(self) -> None:
        self.doc = _load_yaml(FIXTURES / "with-secrets.yaml")
        self.audit = mask_document(self.doc)
        self.audit_paths = {e.path for e in self.audit}

    def test_password_redacted(self) -> None:
        assert self.doc["database"]["password"] == REDACTED

    def test_connection_string_redacted(self) -> None:
        assert self.doc["database"]["connection_string"] == REDACTED

    def test_aws_key_redacted(self) -> None:
        assert self.doc["credentials"]["aws_key"] == REDACTED

    def test_private_key_redacted(self) -> None:
        assert self.doc["credentials"]["private_key"] == REDACTED

    def test_github_token_redacted(self) -> None:
        assert self.doc["tokens"]["github"] == REDACTED

    def test_bearer_token_redacted(self) -> None:
        assert self.doc["tokens"]["bearer_header"] == REDACTED

    def test_env_secret_key_redacted(self) -> None:
        assert self.doc["env"]["SECRET_KEY"] == REDACTED

    def test_hostname_preserved(self) -> None:
        assert self.doc["safe"]["hostname"] == "db-01.mgmt.internal"

    def test_ip_preserved(self) -> None:
        assert self.doc["safe"]["ip_address"] == "172.30.10.12"

    def test_uuid_preserved(self) -> None:
        assert self.doc["safe"]["uuid"] == "550e8400-e29b-41d4-a716-446655440000"

    def test_port_list_preserved(self) -> None:
        assert self.doc["safe"]["port_list"][0] == "8080:80"


class TestDocumentMaskerPlainDict:
    """Test on plain dict (Entra-Intune style)."""

    def test_plain_dict_secrets(self) -> None:
        doc = {
            "app": {
                "clientSecret": "s3cret-val",
                "displayName": "My App",
            },
        }
        audit = mask_document(doc, secret_paths=["*.clientSecret"])
        assert doc["app"]["clientSecret"] == REDACTED
        assert doc["app"]["displayName"] == "My App"
        assert len(audit) == 1

    def test_nested_lists_in_dict(self) -> None:
        doc = {
            "config": {
                "env": [
                    {"password": "secret123"},
                    {"name": "safe"},
                ],
            },
        }
        mask_document(doc)
        assert doc["config"]["env"][0]["password"] == REDACTED
        assert doc["config"]["env"][1]["name"] == "safe"

    def test_deep_nested(self) -> None:
        doc = {
            "level1": {
                "level2": {
                    "level3": {
                        "password": "deep_secret",
                    },
                },
            },
        }
        mask_document(doc)
        assert doc["level1"]["level2"]["level3"]["password"] == REDACTED


class TestDocumentMaskerCommentedMap:
    """Test CommentedMap preservation."""

    def test_commented_map_preserved(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("db:\n  password: secret123\n  host: localhost\n")
        mask_document(doc)
        assert doc["db"]["password"] == REDACTED
        assert doc["db"]["host"] == "localhost"
        # CommentedMap type preserved
        from ruamel.yaml.comments import CommentedMap
        assert isinstance(doc, CommentedMap)


class TestDocumentMaskerCustomOptions:
    def test_custom_entropy_thresholds(self) -> None:
        doc = {"data": {"value": "abcdefghijklmnop"}}
        mask_document(
            doc,
            secret_paths=[],
            entropy_threshold_b64=3.0,
            entropy_threshold_hex=2.0,
        )
        assert doc["data"]["value"] == REDACTED

    def test_empty_document(self) -> None:
        doc = {}
        audit = mask_document(doc)
        assert len(audit) == 0
