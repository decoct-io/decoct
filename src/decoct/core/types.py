"""Core data types for the entity-graph compression pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FinalRole(Enum):
    """Final emission role for an attribute within a discovered type."""
    A_BASE = "A_BASE"
    B = "B"
    C = "C"


class BootstrapSignal(Enum):
    """Bootstrap signal used during type refinement only."""
    VALUE_SIGNAL = "VALUE_SIGNAL"
    PRESENCE_SIGNAL = "PRESENCE_SIGNAL"
    NONE = "NONE"


class TierCStorage(Enum):
    """Physical encoding for Tier C attributes."""
    PHONE_BOOK = "PHONE_BOOK"
    INSTANCE_ATTRS = "INSTANCE_ATTRS"
    NONE = "NONE"


class _AbsentType:
    """Sentinel for a path present in template but absent in entity."""
    _instance: _AbsentType | None = None

    def __new__(cls) -> _AbsentType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "ABSENT"

    def __bool__(self) -> bool:
        return False


class _MissingType:
    """Sentinel distinguishing 'not present' from literal null."""
    _instance: _MissingType | None = None

    def __new__(cls) -> _MissingType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "MISSING"

    def __bool__(self) -> bool:
        return False


ABSENT = _AbsentType()
MISSING = _MissingType()


@dataclass
class Attribute:
    """A single attribute on an entity."""
    path: str
    value: Any
    type: str  # 'string', 'number', 'boolean', 'null', 'enum', 'list', 'map', 'composite_template_ref'
    source: str = ""


@dataclass
class Entity:
    """An entity in the graph."""
    id: str
    attributes: dict[str, Attribute] = field(default_factory=dict)
    schema_type_hint: str | None = None
    discovered_type: str | None = None


@dataclass
class AttributeProfile:
    """Per-type attribute profile computed during bootstrap."""
    path: str
    cardinality: int
    entropy: float
    entropy_norm: float
    coverage: float
    value_length_mean: float
    value_length_var: float
    attribute_type: str
    final_role: FinalRole
    bootstrap_role: BootstrapSignal
    entity_type: str


@dataclass
class CompositeTemplate:
    """A template extracted from composite value decomposition."""
    id: str
    content: Any  # The common elements
    variable_positions: list[Any] = field(default_factory=list)
    decomp_kind: str = ""  # "" for v1, "map_inner" for inner map decomposition


@dataclass
class BaseClass:
    """Base class containing A_BASE + universal B attributes."""
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class ClassDef:
    """A primary class extracted from frequent B bundles."""
    name: str
    inherits: str
    own_attrs: dict[str, Any] = field(default_factory=dict)
    entity_ids: list[str] = field(default_factory=list)
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class SubclassDef:
    """A subclass extracted from delta compression."""
    name: str
    parent_class: str
    own_attrs: dict[str, Any] = field(default_factory=dict)
    entity_ids: list[str] = field(default_factory=list)
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class ClassHierarchy:
    """Complete class hierarchy for a type."""
    base_class: BaseClass = field(default_factory=BaseClass)
    classes: dict[str, ClassDef] = field(default_factory=dict)
    subclasses: dict[str, SubclassDef] = field(default_factory=dict)


@dataclass
class PhoneBook:
    """Dense scalar-like Tier C storage."""
    schema: list[str] = field(default_factory=list)
    records: dict[str, list[Any]] = field(default_factory=dict)


@dataclass
class TierC:
    """Complete Tier C data for a type."""
    class_assignments: dict[str, dict[str, Any]] = field(default_factory=dict)
    subclass_assignments: dict[str, dict[str, Any]] = field(default_factory=dict)
    instance_data: PhoneBook = field(default_factory=PhoneBook)
    instance_attrs: dict[str, dict[str, Any]] = field(default_factory=dict)
    relationship_store: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    b_composite_deltas: dict[str, dict[str, Any]] = field(default_factory=dict)
    foreign_keys: dict[str, Any] = field(default_factory=dict)


@dataclass
class BundleCandidate:
    """A candidate bundle for class or subclass extraction."""
    bundle: frozenset[tuple[str, str]]
    covered: list[str]
    gain: float


@dataclass
class SubclassCandidate:
    """A candidate subclass for delta compression."""
    bundle: frozenset[tuple[str, str]]
    template: dict[str, Any]
    covered: list[str]
    residuals: dict[str, dict[str, Any]]
    gain: float


@dataclass
class ReconstructedEntity:
    """An entity reconstructed from Tier B + Tier C."""
    id: str
    entity_type: str
    attributes: dict[str, Any] = field(default_factory=dict)
    relationships: list[tuple[str, str]] = field(default_factory=list)
