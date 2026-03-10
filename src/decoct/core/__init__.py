"""Core types and utilities for the entity-graph compression pipeline."""

from decoct.core.canonical import (
    CANONICAL_EQUAL,
    CANONICAL_KEY,
    IS_SCALAR_LIKE,
    ITEM_KEY,
    VALUE_KEY,
    encode_canonical,
)
from decoct.core.composite_value import CompositeValue
from decoct.core.config import EntityGraphConfig
from decoct.core.entity_graph import EntityGraph
from decoct.core.hashing import STABLE_CONTENT_HASH
from decoct.core.types import (
    ABSENT,
    MISSING,
    Attribute,
    AttributeProfile,
    BaseClass,
    BootstrapSignal,
    BundleCandidate,
    ClassDef,
    ClassHierarchy,
    CompositeTemplate,
    Entity,
    FinalRole,
    PhoneBook,
    ReconstructedEntity,
    SubclassCandidate,
    SubclassDef,
    TierC,
)

__all__ = [
    "ABSENT",
    "CANONICAL_EQUAL",
    "CANONICAL_KEY",
    "CompositeTemplate",
    "CompositeValue",
    "Entity",
    "EntityGraph",
    "EntityGraphConfig",
    "ITEM_KEY",
    "IS_SCALAR_LIKE",
    "MISSING",
    "STABLE_CONTENT_HASH",
    "VALUE_KEY",
    "Attribute",
    "AttributeProfile",
    "BaseClass",
    "BundleCandidate",
    "ClassDef",
    "ClassHierarchy",
    "FinalRole",
    "BootstrapSignal",
    "PhoneBook",
    "ReconstructedEntity",
    "SubclassCandidate",
    "SubclassDef",
    "TierC",
    "encode_canonical",
]
