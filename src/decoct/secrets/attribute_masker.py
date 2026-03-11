"""Post-flatten secrets masking for Entity.attributes.

Operates on already-extracted entities — handles string values,
CompositeValue internals, and adapter-specific value patterns.
"""

from __future__ import annotations

import re
from typing import Any

from decoct.core.composite_value import CompositeValue
from decoct.core.types import Entity
from decoct.secrets.detection import (
    DEFAULT_SECRET_PATHS,
    REDACTED,
    AuditEntry,
    detect_secret,
)


def _mask_composite(
    data: Any,
    base_path: str,
    audit: list[AuditEntry],
    secret_paths: list[str],
    extra_value_patterns: list[tuple[str, re.Pattern[str]]] | None,
    entropy_threshold_b64: float,
    entropy_threshold_hex: float,
    min_entropy_length: int,
) -> Any:
    """Recursively mask secrets inside CompositeValue data.

    Returns the (possibly modified) data.
    """
    if isinstance(data, dict):
        for key in list(data.keys()):
            child_path = f"{base_path}.{key}"
            child = data[key]
            if isinstance(child, str):
                method = _detect_with_extras(
                    child, child_path, secret_paths,
                    extra_value_patterns,
                    entropy_threshold_b64, entropy_threshold_hex, min_entropy_length,
                )
                if method:
                    data[key] = REDACTED
                    audit.append(AuditEntry(path=child_path, detection_method=method))
            elif isinstance(child, dict):
                _mask_composite(
                    child, child_path, audit, secret_paths,
                    extra_value_patterns,
                    entropy_threshold_b64, entropy_threshold_hex, min_entropy_length,
                )
            elif isinstance(child, list):
                _mask_composite(
                    child, child_path, audit, secret_paths,
                    extra_value_patterns,
                    entropy_threshold_b64, entropy_threshold_hex, min_entropy_length,
                )
    elif isinstance(data, list):
        for i, item in enumerate(data):
            child_path = f"{base_path}[{i}]"
            if isinstance(item, str):
                method = _detect_with_extras(
                    item, child_path, secret_paths,
                    extra_value_patterns,
                    entropy_threshold_b64, entropy_threshold_hex, min_entropy_length,
                )
                if method:
                    data[i] = REDACTED
                    audit.append(AuditEntry(path=child_path, detection_method=method))
            elif isinstance(item, (dict, list)):
                _mask_composite(
                    item, child_path, audit, secret_paths,
                    extra_value_patterns,
                    entropy_threshold_b64, entropy_threshold_hex, min_entropy_length,
                )
    return data


def _detect_with_extras(
    value: str,
    path: str,
    secret_paths: list[str],
    extra_value_patterns: list[tuple[str, re.Pattern[str]]] | None,
    entropy_threshold_b64: float,
    entropy_threshold_hex: float,
    min_entropy_length: int,
) -> str | None:
    """Detect secret using core detection + extra value patterns."""
    # Core detection first
    method = detect_secret(
        value, path, secret_paths,
        entropy_threshold_b64, entropy_threshold_hex, min_entropy_length,
    )
    if method:
        return method

    # Extra value patterns (adapter-specific content matching)
    if extra_value_patterns:
        for name, pattern in extra_value_patterns:
            if pattern.search(value):
                return f"value_pattern:{name}"

    return None


def mask_entity_attributes(
    entity: Entity,
    *,
    secret_paths: list[str] | None = None,
    extra_value_patterns: list[tuple[str, re.Pattern[str]]] | None = None,
    entropy_threshold_b64: float = 4.5,
    entropy_threshold_hex: float = 3.0,
    min_entropy_length: int = 16,
) -> list[AuditEntry]:
    """Mask secrets in an entity's attributes in-place.

    Handles:
    - String attribute values
    - CompositeValue internals (map and list kinds)
    - Extra value patterns for adapter-specific content matching

    Args:
        entity: Entity with attributes to scan.
        secret_paths: Path patterns that always indicate secrets.
        extra_value_patterns: Additional (name, regex) pairs for value-level matching.
        entropy_threshold_b64: Shannon entropy threshold for base64 candidates.
        entropy_threshold_hex: Shannon entropy threshold for hex candidates.
        min_entropy_length: Minimum string length for entropy check.

    Returns:
        Audit log of redacted entries with paths prefixed by entity ID.
    """
    if secret_paths is None:
        secret_paths = list(DEFAULT_SECRET_PATHS)

    audit: list[AuditEntry] = []

    for attr_path, attr in entity.attributes.items():
        full_path = f"{entity.id}.{attr_path}"

        if isinstance(attr.value, str):
            method = _detect_with_extras(
                attr.value, full_path, secret_paths,
                extra_value_patterns,
                entropy_threshold_b64, entropy_threshold_hex, min_entropy_length,
            )
            if method:
                attr.value = REDACTED
                audit.append(AuditEntry(path=full_path, detection_method=method))

        elif isinstance(attr.value, CompositeValue):
            _mask_composite(
                attr.value.data, full_path, audit, secret_paths,
                extra_value_patterns,
                entropy_threshold_b64, entropy_threshold_hex, min_entropy_length,
            )

    return audit
