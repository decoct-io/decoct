"""Pass base class and registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PassResult:
    """Result from a single pass execution."""

    name: str
    items_removed: int = 0
    details: list[str] = field(default_factory=list)


class BasePass:
    """Base class for all compression passes.

    Subclasses must implement ``run`` and set ``name``.
    Ordering is declared via class-level ``run_after`` and ``run_before``.
    """

    name: str = ""
    run_after: list[str] = []
    run_before: list[str] = []

    def run(self, doc: Any, **kwargs: Any) -> PassResult:
        """Execute the pass on a YAML document (CommentedMap), modifying it in-place.

        Returns a PassResult with statistics.
        """
        raise NotImplementedError


# ── Pass registry ──

_registry: dict[str, type[BasePass]] = {}


def register_pass(cls: type[BasePass]) -> type[BasePass]:
    """Decorator to register a pass class by its name."""
    if not cls.name:
        msg = f"Pass class {cls.__name__} must define a 'name' attribute"
        raise ValueError(msg)
    _registry[cls.name] = cls
    return cls


def get_pass(name: str) -> type[BasePass]:
    """Look up a registered pass class by name."""
    if name not in _registry:
        msg = f"Unknown pass '{name}'. Registered: {sorted(_registry)}"
        raise KeyError(msg)
    return _registry[name]


def list_passes() -> list[str]:
    """Return sorted list of registered pass names."""
    return sorted(_registry)


def clear_registry() -> None:
    """Clear the pass registry. For testing only."""
    _registry.clear()
