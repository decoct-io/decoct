"""Tests for IOS-XR, Entra, and network-specific secret patterns."""

from __future__ import annotations

import re

import pytest

from decoct.secrets.detection import detect_secret
from decoct.secrets.iosxr_patterns import (
    ENTRA_SECRET_PATHS,
    IOSXR_SECRET_PATHS,
    IOSXR_SECRET_VALUE_PATTERNS,
    NETWORK_SECRET_PATHS,
)


class TestIosxrValuePatterns:
    """Each IOS-XR regex matches its target value."""

    @pytest.fixture()
    def patterns(self) -> dict[str, re.Pattern[str]]:
        return {name: pat for name, pat in IOSXR_SECRET_VALUE_PATTERNS}

    def test_key_7(self, patterns: dict[str, re.Pattern[str]]) -> None:
        assert patterns["iosxr_key_7"].search("key 7 094F471A1A0A")

    def test_secret_encrypted_5(self, patterns: dict[str, re.Pattern[str]]) -> None:
        assert patterns["iosxr_secret_encrypted"].search("secret 5 $1$abc$def")

    def test_secret_encrypted_0(self, patterns: dict[str, re.Pattern[str]]) -> None:
        assert patterns["iosxr_secret_encrypted"].search("secret 0 cleartext")

    def test_secret_encrypted_7(self, patterns: dict[str, re.Pattern[str]]) -> None:
        assert patterns["iosxr_secret_encrypted"].search("secret 7 02050D480809")

    def test_community_string_ro(self, patterns: dict[str, re.Pattern[str]]) -> None:
        assert patterns["iosxr_community_string"].search("community S3cr3tRO RO")

    def test_community_string_rw(self, patterns: dict[str, re.Pattern[str]]) -> None:
        assert patterns["iosxr_community_string"].search("community Pr1v4teRW RW")

    def test_community_inline(self, patterns: dict[str, re.Pattern[str]]) -> None:
        assert patterns["iosxr_community_inline"].search("version 2c MyCommStr")

    def test_key_string(self, patterns: dict[str, re.Pattern[str]]) -> None:
        assert patterns["iosxr_key_string"].search("key-string T4c4csK3y")


class TestIosxrNonSecrets:
    """Normal IOS-XR values should NOT be flagged by the value patterns."""

    @pytest.fixture()
    def patterns(self) -> list[tuple[str, re.Pattern[str]]]:
        return IOSXR_SECRET_VALUE_PATTERNS

    def test_interface_name(self, patterns: list[tuple[str, re.Pattern[str]]]) -> None:
        value = "GigabitEthernet0/0/0/0"
        for name, pat in patterns:
            assert not pat.search(value), f"{name} should not match interface name"

    def test_isis_area(self, patterns: list[tuple[str, re.Pattern[str]]]) -> None:
        value = "49.0001.0000.0000.0001.00"
        for name, pat in patterns:
            assert not pat.search(value), f"{name} should not match IS-IS area"

    def test_bgp_as_number(self, patterns: list[tuple[str, re.Pattern[str]]]) -> None:
        value = "65001"
        for name, pat in patterns:
            assert not pat.search(value), f"{name} should not match AS number"

    def test_description(self, patterns: list[tuple[str, re.Pattern[str]]]) -> None:
        value = "Link to PE-Router-2 via GE0/0/0/1"
        for name, pat in patterns:
            assert not pat.search(value), f"{name} should not match description"


class TestIosxrSecretPaths:
    """IOS-XR path patterns detect TACACS/RADIUS keys."""

    def test_tacacs_server_path(self) -> None:
        paths = IOSXR_SECRET_PATHS + NETWORK_SECRET_PATHS
        result = detect_secret("anyvalue", "tacacs-server", paths)
        assert result == "path_pattern"

    def test_tacacs_key_path(self) -> None:
        paths = IOSXR_SECRET_PATHS + NETWORK_SECRET_PATHS
        result = detect_secret("anyvalue", "tacacs-server.key", paths)
        assert result == "path_pattern"

    def test_radius_server_path(self) -> None:
        paths = IOSXR_SECRET_PATHS + NETWORK_SECRET_PATHS
        result = detect_secret("anyvalue", "radius-server", paths)
        assert result == "path_pattern"


class TestNetworkSecretPaths:
    """Generic network device secret paths."""

    def test_community_path(self) -> None:
        result = detect_secret("S3cr3tRO", "snmp.community", NETWORK_SECRET_PATHS)
        assert result == "path_pattern"

    def test_pre_shared_key(self) -> None:
        result = detect_secret("key123", "vpn.pre-shared-key", NETWORK_SECRET_PATHS)
        assert result == "path_pattern"

    def test_enable_password(self) -> None:
        result = detect_secret("en4bl3", "device.enable-password", NETWORK_SECRET_PATHS)
        assert result == "path_pattern"


class TestEntraSecretPaths:
    def test_client_secret(self) -> None:
        result = detect_secret("abc123", "app.clientSecret", ENTRA_SECRET_PATHS)
        assert result == "path_pattern"

    def test_secret_text(self) -> None:
        result = detect_secret("xyz789", "credential.secretText", ENTRA_SECRET_PATHS)
        assert result == "path_pattern"
