"""Entity graph with deduplicating relationship storage."""

from __future__ import annotations

from decoct.core.types import Entity


class EntityGraph:
    """In-memory entity graph: entities + attributes + relationships.

    Relationships are stored as a set of (source_id, label, target_id) triples
    for idempotent add_relationship().
    """

    def __init__(self) -> None:
        self._entities: dict[str, Entity] = {}
        self._relationships: set[tuple[str, str, str]] = set()

    def add_entity(self, entity: Entity) -> None:
        """Add or replace an entity in the graph."""
        self._entities[entity.id] = entity

    def get_entity(self, entity_id: str) -> Entity:
        """Get an entity by ID. Raises KeyError if not found."""
        return self._entities[entity_id]

    def has_entity(self, entity_id: str) -> bool:
        return entity_id in self._entities

    @property
    def entities(self) -> list[Entity]:
        """All entities sorted by ID."""
        return sorted(self._entities.values(), key=lambda e: e.id)

    @property
    def entity_ids(self) -> list[str]:
        """All entity IDs sorted."""
        return sorted(self._entities.keys())

    def add_relationship(self, source_id: str, label: str, target_id: str) -> None:
        """Add a relationship triple. Idempotent — deduplicates on (source, label, target)."""
        self._relationships.add((source_id, label, target_id))

    def relationships_from(self, source_id: str) -> list[tuple[str, str]]:
        """Get all (label, target_id) pairs for a source entity, sorted."""
        return sorted(
            [(label, target) for (src, label, target) in self._relationships if src == source_id]
        )

    def has_relationship_from(self, source_id: str, label: str) -> bool:
        """Check if source has any relationship with the given label."""
        return any(src == source_id and lbl == label for src, lbl, _ in self._relationships)

    @property
    def all_relationships(self) -> list[tuple[str, str, str]]:
        """All relationship triples sorted."""
        return sorted(self._relationships)

    def entities_of_type(self, type_id: str) -> list[Entity]:
        """Get all entities with a given discovered_type, sorted by ID."""
        return sorted(
            [e for e in self._entities.values() if e.discovered_type == type_id],
            key=lambda e: e.id,
        )

    def unique_relationship_labels_from_entities(self, entities: list[Entity]) -> list[str]:
        """Get unique relationship labels from a set of entities, sorted."""
        entity_ids = {e.id for e in entities}
        labels: set[str] = set()
        for src, label, _ in self._relationships:
            if src in entity_ids:
                labels.add(label)
        return sorted(labels)

    def __len__(self) -> int:
        return len(self._entities)
