"""CompositeValue type for representing complex infrastructure values."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CompositeValue:
    """A composite (non-scalar) attribute value.

    Wraps lists or maps that represent repeated sub-structures
    (e.g., BGP neighbor blocks, EVPN EVI blocks).
    """
    data: Any  # list or dict
    kind: str = "map"  # "map" or "list"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CompositeValue):
            return NotImplemented
        return self.kind == other.kind and self.data == other.data

    def __hash__(self) -> int:
        # CompositeValues are mutable, use id-based hash
        return id(self)

    @property
    def items(self) -> list[Any]:
        """Return items as a list regardless of kind."""
        if isinstance(self.data, list):
            return list(self.data)
        if isinstance(self.data, dict):
            return list(self.data.items())
        return [self.data]

    @classmethod
    def from_list(cls, items: list[Any]) -> CompositeValue:
        return cls(data=list(items), kind="list")

    @classmethod
    def from_map(cls, mapping: dict[str, Any]) -> CompositeValue:
        return cls(data=dict(mapping), kind="map")


def is_composite_type(attribute_type: str) -> bool:
    """Check if an attribute type represents a collection."""
    return attribute_type in ("list", "map")
