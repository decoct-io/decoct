"""Base adapter ABC for entity graph extraction."""

from __future__ import annotations

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
    def source_type(self) -> str:
        """Return the adapter type identifier (e.g., 'iosxr')."""
        ...
