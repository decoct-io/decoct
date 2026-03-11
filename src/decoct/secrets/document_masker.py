"""Document-level secrets masking — walks a YAML/JSON tree and redacts in-place.

Works on CommentedMap, plain dict, and list structures.
"""

from __future__ import annotations

from typing import Any

from decoct.secrets.detection import (
    DEFAULT_SECRET_PATHS,
    REDACTED,
    AuditEntry,
    detect_secret,
)


def _walk_and_redact(
    node: Any,
    path: str,
    audit: list[AuditEntry],
    secret_paths: list[str],
    entropy_threshold_b64: float,
    entropy_threshold_hex: float,
    min_entropy_length: int,
) -> None:
    """Recursively walk a YAML/JSON tree, redacting secrets in-place."""
    if isinstance(node, dict):
        for key in list(node.keys()):
            child_path = f"{path}.{key}" if path else str(key)
            child = node[key]
            if isinstance(child, str):
                method = detect_secret(
                    child, child_path, secret_paths,
                    entropy_threshold_b64, entropy_threshold_hex, min_entropy_length,
                )
                if method:
                    node[key] = REDACTED
                    audit.append(AuditEntry(path=child_path, detection_method=method))
            elif isinstance(child, (dict, list)):
                _walk_and_redact(
                    child, child_path, audit, secret_paths,
                    entropy_threshold_b64, entropy_threshold_hex, min_entropy_length,
                )
    elif isinstance(node, list):
        for i, child in enumerate(node):
            child_path = f"{path}[{i}]"
            if isinstance(child, str):
                method = detect_secret(
                    child, child_path, secret_paths,
                    entropy_threshold_b64, entropy_threshold_hex, min_entropy_length,
                )
                if method:
                    node[i] = REDACTED
                    audit.append(AuditEntry(path=child_path, detection_method=method))
            elif isinstance(child, (dict, list)):
                _walk_and_redact(
                    child, child_path, audit, secret_paths,
                    entropy_threshold_b64, entropy_threshold_hex, min_entropy_length,
                )


def mask_document(
    doc: Any,
    *,
    secret_paths: list[str] | None = None,
    entropy_threshold_b64: float = 4.5,
    entropy_threshold_hex: float = 3.0,
    min_entropy_length: int = 16,
) -> list[AuditEntry]:
    """Mask secrets in a document (CommentedMap or dict) in-place.

    Args:
        doc: ruamel.yaml CommentedMap (or dict) to process.
        secret_paths: Path patterns that always indicate secrets.
            Defaults to DEFAULT_SECRET_PATHS.
        entropy_threshold_b64: Shannon entropy threshold for base64 candidates.
        entropy_threshold_hex: Shannon entropy threshold for hex candidates.
        min_entropy_length: Minimum string length for entropy check.

    Returns:
        Audit log of redacted entries (path + method, never values).
    """
    if secret_paths is None:
        secret_paths = list(DEFAULT_SECRET_PATHS)

    audit: list[AuditEntry] = []
    _walk_and_redact(
        doc, "", audit, secret_paths,
        entropy_threshold_b64, entropy_threshold_hex, min_entropy_length,
    )
    return audit
