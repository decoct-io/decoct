"""Deterministic content hashing for identifiers and ordering (§2.4)."""

from __future__ import annotations

import hashlib
from typing import Any

from decoct.core.canonical import CANONICAL_KEY


def STABLE_CONTENT_HASH(value: Any) -> str:
    """Deterministic hash for identifiers and ordering only."""
    return hashlib.sha256(CANONICAL_KEY(value).encode()).hexdigest()
