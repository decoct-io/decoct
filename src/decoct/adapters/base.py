"""Base adapter ABC for entity graph extraction."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

from decoct.core.entity_graph import EntityGraph


class BaseAdapter(ABC):
    """Abstract base class for all adapters.

    An adapter transforms a source file into entities, attributes, and relationships
    that populate an EntityGraph.
    """

    @abstractmethod
    def parse(self, source: str) -> Any:
        """Parse source file into an internal representation."""
        ...

    @abstractmethod
    def extract_entities(self, parsed: Any, graph: EntityGraph) -> None:
        """Extract entities, attributes, and relationships into the graph."""
        ...

    @abstractmethod
    def collect_source_leaves(self, parsed: Any) -> dict[str, list[tuple[str, str]]]:
        """Collect ALL leaf data points from parsed source, keyed by entity_id.

        Must be independent of extract_entities() — walks the raw parsed
        structure directly. Returns list (not dict) to preserve duplicates.

        Each tuple is (dotted_path, string_value).
        """
        ...

    @abstractmethod
    def source_type(self) -> str:
        """Return the adapter type identifier (e.g., 'iosxr')."""
        ...

    def secret_paths(self) -> list[str]:
        """Extra path patterns that indicate secrets for this adapter.

        Override to add adapter-specific secret paths (e.g. TACACS keys,
        SNMP communities). These are appended to the global DEFAULT_SECRET_PATHS
        by the pipeline.

        Returns empty list by default — only global patterns apply.
        """
        return []

    def secret_value_patterns(self) -> list[tuple[str, re.Pattern[str]]] | None:
        """Extra value-level regex patterns for this adapter.

        Override to add patterns that match secret content inside attribute
        *values* (e.g. IOS-XR ``key 7 ...``). These run after core detection.

        Returns None by default — no extra value patterns.
        """
        return None
