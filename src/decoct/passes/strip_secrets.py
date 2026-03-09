"""Strip-secrets pass — redacts secrets from YAML documents.

This pass MUST run before any LLM contact. It is the first pass after
normalisation in the pipeline. Audit entries record (path, method) only —
actual secret values are never logged.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Any

REDACTED = "[REDACTED]"


@dataclass
class AuditEntry:
    """Record of a redacted value. Never stores the actual secret."""

    path: str
    detection_method: str


# Regex patterns for known secret formats: (name, compiled pattern)
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("azure_connection_string", re.compile(r"DefaultEndpointsProtocol=https?;AccountName=", re.IGNORECASE)),
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
]

# Default path patterns that always indicate secrets
DEFAULT_SECRET_PATHS: list[str] = [
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
]


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


# Paths that should never trigger entropy-based secret detection.
# These contain commands or values that naturally have high entropy.
_ENTROPY_EXEMPT_PATHS: list[str] = [
    "*.healthcheck.test",
    "*.healthcheck.test.*",
    "*.command",
    "*.command.*",
    "*.entrypoint",
    "*.entrypoint.*",
]


def _is_entropy_exempt(path: str) -> bool:
    """Check if a path is exempt from entropy-based detection."""
    return any(fnmatch(path, p) for p in _ENTROPY_EXEMPT_PATHS)


def _detect_secret(
    value: str,
    path: str,
    secret_paths: list[str],
    entropy_threshold: float,
    min_entropy_length: int,
) -> str | None:
    """Detect if a value is a secret. Returns detection method or None."""
    if _path_matches_secret(path, secret_paths):
        return "path_pattern"

    regex_match = _check_regex(value)
    if regex_match:
        return f"regex:{regex_match}"

    if _is_entropy_exempt(path):
        return None

    if len(value) >= min_entropy_length and shannon_entropy(value) >= entropy_threshold:
        return "entropy"

    return None


def _walk_and_redact(
    node: Any,
    path: str,
    audit: list[AuditEntry],
    secret_paths: list[str],
    entropy_threshold: float,
    min_entropy_length: int,
) -> None:
    """Recursively walk a YAML tree, redacting secrets in-place."""
    if isinstance(node, dict):
        for key in list(node.keys()):
            child_path = f"{path}.{key}" if path else str(key)
            child = node[key]
            if isinstance(child, str):
                method = _detect_secret(child, child_path, secret_paths, entropy_threshold, min_entropy_length)
                if method:
                    node[key] = REDACTED
                    audit.append(AuditEntry(path=child_path, detection_method=method))
            elif isinstance(child, (dict, list)):
                _walk_and_redact(child, child_path, audit, secret_paths, entropy_threshold, min_entropy_length)
    elif isinstance(node, list):
        for i, child in enumerate(node):
            child_path = f"{path}[{i}]"
            if isinstance(child, str):
                method = _detect_secret(child, child_path, secret_paths, entropy_threshold, min_entropy_length)
                if method:
                    node[i] = REDACTED
                    audit.append(AuditEntry(path=child_path, detection_method=method))
            elif isinstance(child, (dict, list)):
                _walk_and_redact(child, child_path, audit, secret_paths, entropy_threshold, min_entropy_length)


def strip_secrets(
    doc: Any,
    *,
    secret_paths: list[str] | None = None,
    entropy_threshold: float = 4.5,
    min_entropy_length: int = 16,
) -> list[AuditEntry]:
    """Strip secrets from a YAML document in-place.

    Args:
        doc: ruamel.yaml CommentedMap (or dict) to process.
        secret_paths: Path patterns that always indicate secrets.
            Defaults to DEFAULT_SECRET_PATHS.
        entropy_threshold: Shannon entropy threshold for detection.
        min_entropy_length: Minimum string length for entropy check.

    Returns:
        Audit log of redacted entries (path + method, never values).
    """
    if secret_paths is None:
        secret_paths = list(DEFAULT_SECRET_PATHS)

    audit: list[AuditEntry] = []
    _walk_and_redact(doc, "", audit, secret_paths, entropy_threshold, min_entropy_length)
    return audit


# ── Pass class ──

from decoct.passes.base import BasePass, PassResult, register_pass  # noqa: E402


@register_pass
class StripSecretsPass(BasePass):
    """Redact secrets from YAML documents. Must run first in every pipeline."""

    name = "strip-secrets"
    run_after: list[str] = []
    run_before: list[str] = []

    def __init__(
        self,
        *,
        secret_paths: list[str] | None = None,
        entropy_threshold: float = 4.5,
        min_entropy_length: int = 16,
    ) -> None:
        self.secret_paths = secret_paths
        self.entropy_threshold = entropy_threshold
        self.min_entropy_length = min_entropy_length

    def run(self, doc: Any, **kwargs: Any) -> PassResult:
        audit = strip_secrets(
            doc,
            secret_paths=self.secret_paths,
            entropy_threshold=self.entropy_threshold,
            min_entropy_length=self.min_entropy_length,
        )
        return PassResult(
            name=self.name,
            items_removed=len(audit),
            details=[f"{e.path} ({e.detection_method})" for e in audit],
        )
