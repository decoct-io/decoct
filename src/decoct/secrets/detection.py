"""Core secret detection logic for the entity-graph pipeline.

Detection order (first match wins):
1. Path pattern — dotted path matches a known secret path
2. False-positive filter — skip UUIDs, IPs, MACs, file paths, etc.
3. Regex — value matches a known secret format
4. Charset-aware entropy — base64 / hex thresholds with all-digit discount

Audit entries record (path, detection_method) only — actual secret values
are NEVER logged, printed, or stored.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from fnmatch import fnmatch

REDACTED = "[REDACTED]"


@dataclass
class AuditEntry:
    """Record of a redacted value. Never stores the actual secret."""

    path: str
    detection_method: str


# ── Regex patterns for known secret formats ──

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Existing 6
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "azure_connection_string",
        re.compile(r"DefaultEndpointsProtocol=https?;AccountName=", re.IGNORECASE),
    ),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]{20,}={0,2}")),
    ("github_token", re.compile(r"(?:ghp|gho|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}")),
    (
        "generic_credential_pair",
        re.compile(
            r"(?:password|passwd|secret|api_key|apikey|access_key|private_key|auth_token)"
            r"\s*[=:]\s*\S+",
            re.IGNORECASE,
        ),
    ),
    # Expanded patterns from detect-secrets / gitleaks
    (
        "aws_secret_key",
        re.compile(
            r"(?:aws)?_?(?:secret)?_?(?:access)?_?key.*?['\"]?\s*[:=]\s*['\"]?"
            r"[A-Za-z0-9/+=]{40}",
            re.IGNORECASE,
        ),
    ),
    ("basic_auth_url", re.compile(r"://[^/\s]+:[^/\s]+@[^/\s]+")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("gitlab_pat", re.compile(r"glpat-[A-Za-z0-9\-_]{20,}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("sendgrid", re.compile(r"SG\.[A-Za-z0-9_-]{22,}\.[A-Za-z0-9_-]{22,}")),
    ("stripe", re.compile(r"(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{20,}")),
    # Network device encrypted passwords
    ("cisco_type7", re.compile(r"\b[0-9]{2}(?:[0-9A-Fa-f]{2}){4,}\b")),
    ("cisco_type89", re.compile(r"\$[89]\$[^\s$]+")),
    ("junos_encrypted", re.compile(r"\$9\$[^\s$]+")),
]


# ── Default path patterns that always indicate secrets ──

DEFAULT_SECRET_PATHS: list[str] = [
    # Original 10
    "*.password",
    "*.secret",
    "*.secrets",
    "*.secrets.*",
    "*.credentials",
    "*.credentials.*",
    "*.private_key",
    "*.api_key",
    "*.connection_string",
    "*.env.*",
    # Extended
    "*.token",
    "*.auth_token",
    "*.access_token",
    "*.client_secret",
    "*.client-secret",
    "*.encryption_key",
    "*.encryption-key",
    "*.db_password",
    "*.db-password",
]


# ── Paths exempt from entropy-based detection ──

_ENTROPY_EXEMPT_PATHS: list[str] = [
    # Original 6
    "*.healthcheck.test",
    "*.healthcheck.test.*",
    "*.command",
    "*.command.*",
    "*.entrypoint",
    "*.entrypoint.*",
    # Extended for infrastructure
    "*.description",
    "*.description.*",
    "*.comment",
    "*.comment.*",
]


# ── Charset detection for entropy thresholds ──

_BASE64_RE = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")
_HEX_RE = re.compile(r"[0-9A-Fa-f]{16,}")
_ALL_DIGITS_RE = re.compile(r"^[0-9]+$")

# False-positive filter patterns
_PLACEHOLDER_RE = re.compile(
    r"<[^>]+>|"                     # <your-key>
    r"\{\{[^}]+\}\}|"              # {{VAR}}
    r"\$\{[^}]+\}|"               # ${VAR}
    r"\$\([^)]+\)|"               # $(cmd)
    r"%\([^)]+\)s",               # %(key)s
    re.IGNORECASE,
)
_PLACEHOLDER_WORDS = frozenset({
    "example", "test", "changeme", "change_me", "placeholder",
    "replace_me", "your_key", "your_secret", "xxx", "todo", "fixme",
    "dummy", "sample",
})
_INDIRECT_PREFIXES = (
    "vault:", "ssm:", "arn:", "env:", "ref:", "secret:", "gsm:",
    "kms:", "op://",
)
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_MAC_RE = re.compile(
    r"^([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}$|"
    r"^([0-9A-Fa-f]{4}\.){2}[0-9A-Fa-f]{4}$"
)
_IPV4_RE = re.compile(
    r"^(\d{1,3}\.){3}\d{1,3}(/\d{1,2})?$"
)
_IPV6_RE = re.compile(
    r"^([0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}(/\d{1,3})?$"
)


def shannon_entropy(s: str) -> float:
    """Calculate Shannon entropy of a string."""
    if not s:
        return 0.0
    counts = Counter(s)
    length = len(s)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def _path_matches_secret(path: str, patterns: list[str]) -> bool:
    """Check if a dotted path matches any secret path pattern."""
    return any(fnmatch(path, p) for p in patterns)


def _check_regex(value: str) -> str | None:
    """Check value against known secret patterns. Returns pattern name or None."""
    for name, pattern in _SECRET_PATTERNS:
        if pattern.search(value):
            return name
    return None


def _is_entropy_exempt(path: str) -> bool:
    """Check if a path is exempt from entropy-based detection."""
    return any(fnmatch(path, p) for p in _ENTROPY_EXEMPT_PATHS)


def is_likely_false_positive(value: str) -> bool:
    """Return True if value looks like legitimate infrastructure data, not a secret.

    Checked BEFORE entropy detection to prevent over-redaction.
    """
    stripped = value.strip()

    # Placeholder / example values
    if stripped.lower() in _PLACEHOLDER_WORDS:
        return True
    if _PLACEHOLDER_RE.search(stripped):
        return True

    # Indirect references (vault, SSM, ARN, etc.)
    lower = stripped.lower()
    if any(lower.startswith(p) for p in _INDIRECT_PREFIXES):
        return True

    # File paths
    if stripped.startswith(("/", "./", "../")) or stripped.endswith((".pem", ".crt", ".key", ".cert")):
        return True

    # URLs without credentials (no user:pass@host)
    if re.match(r"^https?://", stripped, re.IGNORECASE):
        if "://" in stripped and "@" not in stripped:
            return True

    # UUIDs
    if _UUID_RE.match(stripped):
        return True

    # MAC addresses
    if _MAC_RE.match(stripped):
        return True

    # IP addresses (v4 and v6, with optional CIDR)
    if _IPV4_RE.match(stripped):
        return True
    if _IPV6_RE.match(stripped):
        return True

    # Pure numeric strings (AS numbers, VLANs, ports, MTUs)
    if _ALL_DIGITS_RE.match(stripped):
        return True

    return False


def _charset_entropy(
    value: str,
    entropy_threshold_b64: float,
    entropy_threshold_hex: float,
) -> bool:
    """Charset-aware entropy check with hex all-digit discount.

    Returns True if value exceeds the appropriate entropy threshold.
    """
    # Check for base64 candidate
    if _BASE64_RE.search(value):
        return shannon_entropy(value) >= entropy_threshold_b64

    # Check for hex candidate
    hex_match = _HEX_RE.search(value)
    if hex_match:
        candidate = hex_match.group()
        # All-digit discount — pure numeric hex gets artificially reduced entropy
        if _ALL_DIGITS_RE.match(candidate):
            return False
        return shannon_entropy(value) >= entropy_threshold_hex

    # Default: use base64 threshold
    return shannon_entropy(value) >= entropy_threshold_b64


def detect_secret(
    value: str,
    path: str,
    secret_paths: list[str],
    entropy_threshold_b64: float = 4.5,
    entropy_threshold_hex: float = 3.0,
    min_entropy_length: int = 16,
) -> str | None:
    """Detect if a string value is a secret. Returns detection method or None.

    Detection order (first match wins):
    1. Path pattern match
    2. False-positive filter (skip UUIDs, IPs, MACs, etc.)
    3. Regex pattern match
    4. Charset-aware entropy

    Args:
        value: The string value to check.
        path: Dotted path to the value in the document.
        secret_paths: Path patterns that always indicate secrets.
        entropy_threshold_b64: Shannon entropy threshold for base64 candidates.
        entropy_threshold_hex: Shannon entropy threshold for hex candidates.
        min_entropy_length: Minimum string length for entropy check.

    Returns:
        Detection method string, or None if not a secret.
    """
    # 1. Path pattern
    if _path_matches_secret(path, secret_paths):
        return "path_pattern"

    # 2. False-positive filter — skip values that are clearly infrastructure data
    #    before regex can match (e.g. UUIDs, IPs, MACs, file paths)
    if is_likely_false_positive(value):
        return None

    # 3. Regex
    regex_match = _check_regex(value)
    if regex_match:
        return f"regex:{regex_match}"

    # 4. Entropy exemptions
    if _is_entropy_exempt(path):
        return None

    # 5. Charset-aware entropy
    if len(value) >= min_entropy_length and _charset_entropy(
        value, entropy_threshold_b64, entropy_threshold_hex
    ):
        return "entropy"

    return None
