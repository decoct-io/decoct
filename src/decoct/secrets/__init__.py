"""Shared secrets detection and masking — used by both pipelines."""

from decoct.secrets.attribute_masker import mask_entity_attributes
from decoct.secrets.detection import (
    DEFAULT_SECRET_PATHS,
    REDACTED,
    AuditEntry,
    detect_secret,
    is_likely_false_positive,
    shannon_entropy,
)
from decoct.secrets.document_masker import mask_document

__all__ = [
    "REDACTED",
    "AuditEntry",
    "DEFAULT_SECRET_PATHS",
    "detect_secret",
    "is_likely_false_positive",
    "mask_document",
    "mask_entity_attributes",
    "shannon_entropy",
]
