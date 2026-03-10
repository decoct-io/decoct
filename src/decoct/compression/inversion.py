"""FK detection helpers (§7.3).

v1 stub: returns empty dict. FK detection deferred.
"""

from __future__ import annotations

from typing import Any

from decoct.core.entity_graph import EntityGraph
from decoct.core.types import AttributeProfile


def detect_foreign_keys_on_scalar_attrs(
    graph: EntityGraph,
    profiles: dict[str, AttributeProfile],
    type_id: str,
) -> dict[str, Any]:
    """Detect foreign keys on scalar Tier C attributes.

    v1 stub: returns empty dict.
    """
    return {}
