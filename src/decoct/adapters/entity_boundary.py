"""Entity boundary detection helpers for adapters."""

from __future__ import annotations


def file_is_entity(source_path: str, hostname: str | None) -> str:
    """v1 boundary: each .cfg file = one entity. Canonical ID = hostname."""
    if hostname:
        return hostname
    # Fallback to filename without extension
    import os
    return os.path.splitext(os.path.basename(source_path))[0]
