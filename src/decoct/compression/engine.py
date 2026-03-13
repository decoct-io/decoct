"""Swappable compression engine ABC and registry.

Allows alternative compression algorithms (Phase 4: class extraction +
Phase 5: delta compression) to be plugged in via a registry pattern.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from decoct.core.config import EntityGraphConfig
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import AttributeProfile, ClassHierarchy, Entity


class CompressionEngine(ABC):
    """Abstract base for compression engines (Phase 4 + Phase 5)."""

    @abstractmethod
    def compress(
        self,
        type_map: dict[str, list[Entity]],
        graph: EntityGraph,
        profiles: dict[str, dict[str, AttributeProfile]],
        config: EntityGraphConfig,
    ) -> dict[str, ClassHierarchy]:
        """Run class extraction and delta compression, returning hierarchies per type."""

    @abstractmethod
    def name(self) -> str:
        """Return the registered engine name."""


class _EngineRegistry:
    """Registry of compression engine classes, keyed by name."""

    def __init__(self) -> None:
        self._engines: dict[str, type[CompressionEngine]] = {}

    def register(self, engine_class: type[CompressionEngine]) -> type[CompressionEngine]:
        """Register an engine class.  Can be used as a decorator.

        Raises:
            ValueError: if an engine with the same name is already registered.
        """
        instance = engine_class()
        engine_name = instance.name()
        if engine_name in self._engines:
            msg = f"Compression engine {engine_name!r} is already registered"
            raise ValueError(msg)
        self._engines[engine_name] = engine_class
        return engine_class

    def get(self, name: str) -> CompressionEngine:
        """Return a new instance of the named engine.

        Raises:
            KeyError: if no engine with that name is registered.
        """
        if name not in self._engines:
            available = ", ".join(sorted(self._engines))
            msg = f"Unknown compression engine {name!r}; available: {available}"
            raise KeyError(msg)
        return self._engines[name]()

    def available(self) -> list[str]:
        """Return sorted list of registered engine names."""
        return sorted(self._engines)


registry = _EngineRegistry()


def get_engine(name: str) -> CompressionEngine:
    """Convenience wrapper around ``registry.get(name)``."""
    return registry.get(name)
