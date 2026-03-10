"""Phone book: dense scalar-like Tier C storage (§7.3)."""

from __future__ import annotations

import copy
from typing import Any

from decoct.core.types import Entity, PhoneBook


def build_phone_book_dense(
    entities: list[Entity],
    schema_paths: list[str],
) -> PhoneBook:
    """Build dense phone book from entities and schema paths (§7.3)."""
    if not schema_paths:
        return PhoneBook(schema=[], records={})

    records: dict[str, list[Any]] = {}
    for e in sorted(entities, key=lambda x: x.id):
        records[e.id] = [copy.deepcopy(e.attributes[p].value) for p in schema_paths]

    return PhoneBook(schema=schema_paths, records=records)
