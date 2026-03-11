"""Adapter-specific secret patterns for IOS-XR, Entra-Intune, and network devices."""

from __future__ import annotations

import re

# ── IOS-XR value-level patterns ──
# These match secret content inside attribute *values* (not paths).
# Used as extra_value_patterns in mask_entity_attributes().

IOSXR_SECRET_VALUE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("iosxr_key_7", re.compile(r"\bkey\s+7\s+\S+")),
    ("iosxr_secret_encrypted", re.compile(r"\bsecret\s+[057]\s+\S+")),
    ("iosxr_community_string", re.compile(r"\bcommunity\s+\S+\s+(?:RO|RW)\b")),
    ("iosxr_community_inline", re.compile(r"\bversion\s+2c\s+\S+")),
    ("iosxr_key_string", re.compile(r"\bkey-string\s+\S+")),
]

# ── IOS-XR path patterns ──

IOSXR_SECRET_PATHS: list[str] = [
    "tacacs-server",
    "tacacs-server.key",
    "radius-server",
    "radius-server.key",
]

# ── Entra / Intune path patterns ──

ENTRA_SECRET_PATHS: list[str] = [
    "*.secretText",
    "*.clientSecret",
]

# ── Generic network device path patterns ──

NETWORK_SECRET_PATHS: list[str] = [
    "*.community",
    "*.snmp-community",
    "*.shared-secret",
    "*.shared_secret",
    "*.pre-shared-key",
    "*.psk",
    "*.md5-key",
    "*.authentication-key",
    "*.tacacs-key",
    "*.radius-key",
    "*.enable-secret",
    "*.enable-password",
]
