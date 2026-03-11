"""Tests for core secret detection logic."""

from __future__ import annotations

from decoct.secrets.detection import (
    DEFAULT_SECRET_PATHS,
    REDACTED,
    AuditEntry,
    detect_secret,
    is_likely_false_positive,
    shannon_entropy,
)


class TestShannonEntropy:
    def test_empty_string(self) -> None:
        assert shannon_entropy("") == 0.0

    def test_single_char_repeated(self) -> None:
        assert shannon_entropy("aaaaaaa") == 0.0

    def test_two_chars_equal(self) -> None:
        assert abs(shannon_entropy("abababab") - 1.0) < 0.01

    def test_high_entropy_string(self) -> None:
        assert shannon_entropy("xK9mP2vL5nR8qW1tY4uI7oA3sD6fG0hJ") > 4.0

    def test_low_entropy_string(self) -> None:
        assert shannon_entropy("hello world") < 4.0

    def test_ip_address_low_entropy(self) -> None:
        assert shannon_entropy("172.30.10.12") < 4.0


class TestFalsePositiveFilter:
    def test_uuid(self) -> None:
        assert is_likely_false_positive("550e8400-e29b-41d4-a716-446655440000")

    def test_ipv4(self) -> None:
        assert is_likely_false_positive("192.168.1.1")

    def test_ipv4_cidr(self) -> None:
        assert is_likely_false_positive("10.0.0.0/8")

    def test_ipv6(self) -> None:
        assert is_likely_false_positive("2001:db8::1")

    def test_mac_colon(self) -> None:
        assert is_likely_false_positive("00:1A:2B:3C:4D:5E")

    def test_mac_dot(self) -> None:
        assert is_likely_false_positive("001A.2B3C.4D5E")

    def test_file_path_absolute(self) -> None:
        assert is_likely_false_positive("/etc/ssl/certs/ca-certificates.crt")

    def test_file_path_relative(self) -> None:
        assert is_likely_false_positive("./config/app.yaml")

    def test_file_path_pem(self) -> None:
        assert is_likely_false_positive("server.pem")

    def test_template_var_double_brace(self) -> None:
        assert is_likely_false_positive("{{SECRET_KEY}}")

    def test_template_var_dollar(self) -> None:
        assert is_likely_false_positive("${DB_PASSWORD}")

    def test_placeholder_word(self) -> None:
        assert is_likely_false_positive("changeme")

    def test_placeholder_example(self) -> None:
        assert is_likely_false_positive("example")

    def test_angle_bracket(self) -> None:
        assert is_likely_false_positive("<your-api-key>")

    def test_vault_ref(self) -> None:
        assert is_likely_false_positive("vault:secret/data/myapp")

    def test_ssm_ref(self) -> None:
        assert is_likely_false_positive("ssm:/prod/db/password")

    def test_arn_ref(self) -> None:
        assert is_likely_false_positive("arn:aws:secretsmanager:us-east-1:123456:secret:my-secret")

    def test_url_without_auth(self) -> None:
        assert is_likely_false_positive("https://example.com/api/v1")

    def test_url_with_auth_not_false_positive(self) -> None:
        assert not is_likely_false_positive("https://user:pass@host.com")

    def test_pure_numeric(self) -> None:
        assert is_likely_false_positive("65001")

    def test_pure_numeric_large(self) -> None:
        assert is_likely_false_positive("1234567890123456")

    def test_real_secret_not_false_positive(self) -> None:
        assert not is_likely_false_positive("xK9mP2vL5nR8qW1tY4uI7oA3sD6fG0hJ")


class TestHexAllDigitDiscount:
    """Pure numeric hex strings should not be flagged by entropy — AS numbers, VLANs, MTUs."""

    def test_as_number_not_flagged(self) -> None:
        result = detect_secret("65001", "router.bgp.as-number", [], min_entropy_length=4)
        assert result is None

    def test_vlan_id_not_flagged(self) -> None:
        result = detect_secret("4094", "interface.vlan-id", [], min_entropy_length=4)
        assert result is None

    def test_mtu_not_flagged(self) -> None:
        result = detect_secret("9216", "interface.mtu", [], min_entropy_length=4)
        assert result is None

    def test_long_numeric_not_flagged(self) -> None:
        result = detect_secret("1234567890123456", "data.serial", [])
        assert result is None


class TestDetectSecret:
    """Test detect_secret() with all detection methods."""

    def test_path_pattern(self) -> None:
        result = detect_secret("anything", "db.password", DEFAULT_SECRET_PATHS)
        assert result == "path_pattern"

    def test_path_pattern_api_key(self) -> None:
        result = detect_secret("anything", "service.api_key", DEFAULT_SECRET_PATHS)
        assert result == "path_pattern"

    def test_path_pattern_extended_token(self) -> None:
        result = detect_secret("anything", "auth.token", DEFAULT_SECRET_PATHS)
        assert result == "path_pattern"

    def test_path_pattern_client_secret(self) -> None:
        result = detect_secret("anything", "oauth.client_secret", DEFAULT_SECRET_PATHS)
        assert result == "path_pattern"

    def test_regex_aws_access_key(self) -> None:
        result = detect_secret("AKIAIOSFODNN7EXAMPLE", "creds.key_id", [])
        assert result == "regex:aws_access_key"

    def test_regex_private_key(self) -> None:
        result = detect_secret(
            "-----BEGIN PRIVATE KEY-----\nMIIEv...", "tls.key", [],
        )
        assert result == "regex:private_key_block"

    def test_regex_github_token(self) -> None:
        result = detect_secret("ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh", "ci.token", [])
        assert result == "regex:github_token"

    def test_regex_bearer_token(self) -> None:
        result = detect_secret(
            "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", "auth.header", [],
        )
        assert result == "regex:bearer_token"

    def test_regex_jwt(self) -> None:
        result = detect_secret(
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jV",
            "data.jwt",
            [],
        )
        # Could match bearer_token or jwt — both are regex matches
        assert result is not None and result.startswith("regex:")

    def test_regex_basic_auth_url(self) -> None:
        result = detect_secret("https://admin:s3cret@db.internal:5432", "config.url", [])
        assert result == "regex:basic_auth_url"

    def test_regex_gitlab_pat(self) -> None:
        result = detect_secret("glpat-abcdefghijklmnopqrstuvwxyz", "ci.token", [])
        assert result == "regex:gitlab_pat"

    def test_regex_slack_token(self) -> None:
        result = detect_secret("xoxb-123456789012-1234567890123-abc", "slack.token", [])
        assert result == "regex:slack_token"

    def test_regex_stripe(self) -> None:
        result = detect_secret("sk_live_" + "A" * 32, "pay.key", [])
        assert result == "regex:stripe"

    def test_regex_generic_credential_pair(self) -> None:
        result = detect_secret("password=mysecret;host=db01", "conn.string", [])
        assert result == "regex:generic_credential_pair"

    def test_entropy_high_entropy_string(self) -> None:
        result = detect_secret("xK9mP2vL5nR8qW1tY4uI7oA3sD6fG0hJ", "env.KEY", [])
        assert result == "entropy"

    def test_entropy_exempt_healthcheck(self) -> None:
        result = detect_secret(
            "curl -sf http://localhost:8080/health", "svc.healthcheck.test", [],
        )
        assert result is None

    def test_entropy_exempt_command(self) -> None:
        result = detect_secret(
            "celery -A config worker -l info --concurrency=4", "svc.command", [],
        )
        assert result is None

    def test_entropy_exempt_description(self) -> None:
        result = detect_secret(
            "xK9mP2vL5nR8qW1tY4uI7oA3sD6fG0hJ", "interface.description", [],
        )
        assert result is None

    def test_uuid_not_detected(self) -> None:
        result = detect_secret("550e8400-e29b-41d4-a716-446655440000", "safe.uuid", [])
        assert result is None

    def test_ip_not_detected(self) -> None:
        result = detect_secret("172.30.10.12", "server.ip", [])
        assert result is None

    def test_short_string_not_detected(self) -> None:
        result = detect_secret("xK9mP2v", "data.short", [], min_entropy_length=16)
        assert result is None

    def test_normal_value_not_detected(self) -> None:
        result = detect_secret("hello world", "greeting.text", [])
        assert result is None


class TestAuditEntry:
    def test_audit_entry_has_path_and_method(self) -> None:
        entry = AuditEntry(path="db.password", detection_method="path_pattern")
        assert entry.path == "db.password"
        assert entry.detection_method == "path_pattern"

    def test_redacted_constant(self) -> None:
        assert REDACTED == "[REDACTED]"
