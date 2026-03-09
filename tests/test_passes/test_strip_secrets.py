"""Tests for the strip-secrets pass."""

from pathlib import Path

from ruamel.yaml import YAML

from decoct.passes.strip_secrets import (
    REDACTED,
    shannon_entropy,
    strip_secrets,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "yaml"


def _load_yaml(path: Path) -> dict:
    yaml = YAML(typ="rt")
    return yaml.load(path)


class TestShannonEntropy:
    def test_empty_string(self) -> None:
        assert shannon_entropy("") == 0.0

    def test_single_char_repeated(self) -> None:
        assert shannon_entropy("aaaaaaa") == 0.0

    def test_two_chars_equal(self) -> None:
        # "ab" repeated = equal distribution of 2 chars → entropy = 1.0
        assert abs(shannon_entropy("abababab") - 1.0) < 0.01

    def test_high_entropy_string(self) -> None:
        # Random-looking string should have high entropy
        assert shannon_entropy("xK9mP2vL5nR8qW1tY4uI7oA3sD6fG0hJ") > 4.0

    def test_low_entropy_string(self) -> None:
        # Repetitive string should have low entropy
        assert shannon_entropy("hello world") < 4.0

    def test_ip_address_low_entropy(self) -> None:
        assert shannon_entropy("172.30.10.12") < 4.0


class TestStripSecretsFixture:
    """Test against the full fixture file with various secret types."""

    def setup_method(self) -> None:
        self.doc = _load_yaml(FIXTURES / "with-secrets.yaml")
        self.audit = strip_secrets(self.doc)
        self.audit_paths = {e.path for e in self.audit}
        self.audit_methods = {e.path: e.detection_method for e in self.audit}

    # --- Secrets that MUST be caught ---

    def test_password_redacted(self) -> None:
        assert self.doc["database"]["password"] == REDACTED
        assert "database.password" in self.audit_paths
        assert self.audit_methods["database.password"] == "path_pattern"

    def test_connection_string_redacted(self) -> None:
        assert self.doc["database"]["connection_string"] == REDACTED
        assert "database.connection_string" in self.audit_paths

    def test_aws_key_redacted(self) -> None:
        assert self.doc["credentials"]["aws_key"] == REDACTED
        assert self.audit_methods["credentials.aws_key"] == "regex:aws_access_key"

    def test_private_key_redacted(self) -> None:
        assert self.doc["credentials"]["private_key"] == REDACTED
        assert "credentials.private_key" in self.audit_paths

    def test_api_key_redacted(self) -> None:
        assert self.doc["credentials"]["api_key"] == REDACTED
        assert "credentials.api_key" in self.audit_paths

    def test_github_token_redacted(self) -> None:
        assert self.doc["tokens"]["github"] == REDACTED
        assert self.audit_methods["tokens.github"] == "regex:github_token"

    def test_bearer_token_redacted(self) -> None:
        assert self.doc["tokens"]["bearer_header"] == REDACTED
        assert self.audit_methods["tokens.bearer_header"] == "regex:bearer_token"

    def test_embedded_credential_redacted(self) -> None:
        assert self.doc["embedded"]["conn"] == REDACTED
        assert self.audit_methods["embedded.conn"] == "regex:generic_credential_pair"

    def test_env_secret_key_redacted_by_entropy(self) -> None:
        # High-entropy string caught by entropy detection
        assert self.doc["env"]["SECRET_KEY"] == REDACTED
        assert self.audit_methods["env.SECRET_KEY"] == "entropy"

    def test_env_normal_var_preserved(self) -> None:
        # Low-entropy, non-secret path — not redacted
        assert self.doc["env"]["NORMAL_VAR"] == "hello world"

    # --- Non-secrets that MUST be preserved ---

    def test_hostname_preserved(self) -> None:
        assert self.doc["safe"]["hostname"] == "db-01.mgmt.internal"

    def test_ip_address_preserved(self) -> None:
        assert self.doc["safe"]["ip_address"] == "172.30.10.12"

    def test_description_preserved(self) -> None:
        assert self.doc["safe"]["description"] == "A normal configuration value"

    def test_version_preserved(self) -> None:
        assert self.doc["safe"]["version"] == "1.25.3"

    def test_image_preserved(self) -> None:
        assert self.doc["safe"]["image"] == "nginx:1.25.3"

    def test_uuid_preserved(self) -> None:
        assert self.doc["safe"]["uuid"] == "550e8400-e29b-41d4-a716-446655440000"

    def test_port_list_preserved(self) -> None:
        assert self.doc["safe"]["port_list"][0] == "8080:80"
        assert self.doc["safe"]["port_list"][1] == "443:443"

    def test_db_host_preserved(self) -> None:
        assert self.doc["database"]["host"] == "db-01.internal"

    def test_db_port_preserved(self) -> None:
        assert self.doc["database"]["port"] == 5432

    def test_db_username_preserved(self) -> None:
        assert self.doc["database"]["username"] == "appuser"

    # --- Audit log correctness ---

    def test_audit_never_contains_secret_values(self) -> None:
        for entry in self.audit:
            assert "SuperS3cret" not in entry.path
            assert "SuperS3cret" not in entry.detection_method
            assert "AKIA" not in entry.detection_method

    def test_audit_entry_has_path_and_method(self) -> None:
        for entry in self.audit:
            assert entry.path
            assert entry.detection_method


class TestStripSecretsOptions:
    def test_custom_secret_paths(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("custom:\n  my_field: sensitive_data\n")
        audit = strip_secrets(doc, secret_paths=["*.my_field"])
        assert doc["custom"]["my_field"] == REDACTED
        assert len(audit) == 1

    def test_custom_entropy_threshold(self) -> None:
        yaml = YAML(typ="rt")
        # Low threshold catches more strings
        doc = yaml.load("data:\n  value: abcdefghijklmnop\n")
        audit = strip_secrets(doc, entropy_threshold=3.0, secret_paths=[])
        assert doc["data"]["value"] == REDACTED
        assert len(audit) == 1

    def test_high_entropy_threshold_preserves_more(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("data:\n  value: abcdefghijklmnop\n")
        audit = strip_secrets(doc, entropy_threshold=5.0, secret_paths=[])
        assert doc["data"]["value"] == "abcdefghijklmnop"
        assert len(audit) == 0

    def test_min_entropy_length(self) -> None:
        yaml = YAML(typ="rt")
        # Short high-entropy string below min length threshold
        doc = yaml.load("data:\n  value: xK9mP2v\n")
        audit = strip_secrets(doc, min_entropy_length=16, secret_paths=[])
        assert doc["data"]["value"] == "xK9mP2v"
        assert len(audit) == 0

    def test_empty_document(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("{}\n")
        audit = strip_secrets(doc)
        assert len(audit) == 0

    def test_nested_lists_with_secrets(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("items:\n  - password: secret123\n  - name: safe\n")
        strip_secrets(doc)
        assert doc["items"][0]["password"] == REDACTED
        assert doc["items"][1]["name"] == "safe"

    def test_secrets_in_list_values(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("env:\n  keys:\n    - AKIAIOSFODNN7EXAMPLE\n    - normal_value\n")
        strip_secrets(doc)
        assert doc["env"]["keys"][0] == REDACTED
        assert doc["env"]["keys"][1] == "normal_value"


class TestHealthcheckExemption:
    """Healthcheck commands should not trigger entropy-based detection."""

    def test_healthcheck_test_preserved(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load(
            "services:\n  web:\n    healthcheck:\n"
            "      test:\n        - CMD-SHELL\n        - curl -f http://localhost:8080/health\n"
        )
        audit = strip_secrets(doc)
        test_list = doc["services"]["web"]["healthcheck"]["test"]
        assert test_list[0] == "CMD-SHELL"
        assert "curl" in test_list[1]
        # No entries for healthcheck paths
        assert not any("healthcheck" in e.path for e in audit)

    def test_healthcheck_string_command_preserved(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load(
            "services:\n  web:\n    healthcheck:\n"
            "      test: curl -sf http://localhost:8080/health || exit 1\n"
        )
        strip_secrets(doc)
        assert "curl" in doc["services"]["web"]["healthcheck"]["test"]

    def test_command_preserved(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load(
            "services:\n  worker:\n    command: celery -A config worker -l info --concurrency=4\n"
        )
        strip_secrets(doc)
        assert "celery" in doc["services"]["worker"]["command"]

    def test_entrypoint_preserved(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load(
            "services:\n  proxy:\n    entrypoint: /bin/sh -c 'ip route add default via 172.30.100.1'\n"
        )
        strip_secrets(doc)
        assert "/bin/sh" in doc["services"]["proxy"]["entrypoint"]

    def test_real_secret_in_env_still_redacted(self) -> None:
        """Ensure exemptions don't leak actual secrets at non-exempt paths."""
        yaml = YAML(typ="rt")
        doc = yaml.load(
            "services:\n  web:\n    healthcheck:\n"
            "      test: curl http://localhost\n"
            "    environment:\n      SECRET_KEY: xK9mP2vQ8rT5wZ3yB6nC4hL7jF1dA0eS\n"
        )
        strip_secrets(doc)
        assert doc["services"]["web"]["environment"]["SECRET_KEY"] == REDACTED
