"""Hybrid infrastructure adapter — backward-compatible alias.

All generic logic has been promoted into ``BaseAdapter``. This module
subclasses it with hybrid-infra-specific overrides and re-exports all
previously public names so existing imports continue to work.
"""

from __future__ import annotations

from decoct.adapters.base import (  # noqa: F401 — re-exports for backward compat
    BaseAdapter,
    ParseResult,
    _classify,
    _coerce_value,
    _flatten_composite_item,
    _is_empty,
    _is_homogeneous_map,
    _is_scalar,
    _match_composite_override,
    _parse_ini_tolerant,
    _parse_space_separated,
    _value_to_str,
    _walk_doc_leaves,
    flatten_doc,
)
from decoct.adapters.ingestion_models import IngestionSpec


class HybridInfraAdapter(BaseAdapter):
    """Backward-compatible hybrid-infra adapter.

    Identical to ``BaseAdapter`` except for source_type and secret_paths.
    """

    def __init__(self, ingestion_spec: IngestionSpec | None = None) -> None:
        super().__init__(ingestion_spec)

    def source_type(self) -> str:
        return "hybrid-infra"

    def secret_paths(self) -> list[str]:
        from decoct.secrets.iosxr_patterns import NETWORK_SECRET_PATHS
        return list(NETWORK_SECRET_PATHS)
