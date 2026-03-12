"""Layer 2: Strict bidirectional source fidelity validation.

Proves that the EntityGraph captures ALL source data and ONLY source data
via token-sequence normalisation. Both source leaves and entity leaves are
projected to canonical token tuples, sorted, and compared with a merge-join.

Any token present in source but not entity → "missing_from_entity"
Any token present in entity but not source → "fabricated_in_entity"

No heuristics, no fuzzy matching, no false positives.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from decoct.core.composite_value import CompositeValue
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import Entity

logger = logging.getLogger(__name__)

# Path segments that are adapter-internal (not present in source)
INTERNAL_PATHS: frozenset[str] = frozenset({"_uuid"})

# Singular↔plural naming normalisation from IOS-XR composites
SEGMENT_ALIASES: dict[str, str] = {
    "evis": "evi",
    "neighbors": "neighbor",
    "bridge-groups": "bridge-group",
    "bridge-domains": "bridge-domain",
}


# ── Token normalisation ──────────────────────────────────────────────────


def _tokenize_path(path: str) -> list[str]:
    """Replace [] with ., split on ., filter empty segments."""
    cleaned = path.replace("[", ".").replace("]", ".")
    return [seg for seg in cleaned.split(".") if seg]


def _tokenize_value(value: str) -> list[str]:
    """Split value on . and space (handles IPs in values), filter empty.

    Also strips Python list repr chars ([ ] ' ") and commas so that
    list-serialized values normalize identically regardless of how the
    adapter serialized the list (comma-join vs Python repr).

    Special tokens like [REDACTED] are preserved intact.
    """
    # Preserve [REDACTED] as a single token
    if value == "[REDACTED]":
        return [value]
    # Strip list repr characters: ['a', 'b'] → a  b
    cleaned = value
    for ch in "[]'\"":
        cleaned = cleaned.replace(ch, "")
    # Replace . and , with space, then split
    cleaned = cleaned.replace(".", " ").replace(",", " ")
    return [tok for tok in cleaned.split() if tok]


def normalize_leaf(path: str, value: str) -> tuple[str, ...]:
    """Normalize a (path, value) leaf to a canonical token tuple.

    Handles discrimination, singular/plural aliases, array indices,
    IP splitting, and boolean "true" elision.
    """
    tokens = _tokenize_path(path)
    tokens = [SEGMENT_ALIASES.get(t, t) for t in tokens]
    if value and value != "true":
        tokens.extend(_tokenize_value(value))
    return tuple(tokens)


# ── Entity leaf expansion ────────────────────────────────────────────────


def expand_entity_leaves(entity: Entity) -> list[tuple[str, str]]:
    """Expand entity attributes into individual (path, value) leaves.

    Scalar attrs → emit directly.
    CompositeValue(list) of strings → (base[i], item)
    CompositeValue(list) of dicts → (base[i].key, value) per entry
    CompositeValue(map) of dicts → (base.entry_key.attr_key, value) per entry
    CompositeValue(map) of scalars → (base.entry_key, str(value))

    Skips INTERNAL_PATHS.
    """
    leaves: list[tuple[str, str]] = []

    for attr_path, attr in entity.attributes.items():
        if attr_path in INTERNAL_PATHS:
            continue

        if isinstance(attr.value, CompositeValue):
            _expand_composite(attr_path, attr.value, leaves)
        else:
            leaves.append((attr_path, str(attr.value) if attr.value is not None else ""))

    return leaves


def _expand_composite(
    base_path: str,
    cv: CompositeValue,
    out: list[tuple[str, str]],
) -> None:
    """Recursively expand a CompositeValue into (path, value) leaves."""
    if cv.kind == "list" and isinstance(cv.data, list):
        for i, item in enumerate(cv.data):
            if isinstance(item, dict):
                for key, val in item.items():
                    if isinstance(val, CompositeValue):
                        _expand_composite(f"{base_path}[{i}].{key}", val, out)
                    elif isinstance(val, (dict, list)):
                        _expand_nested(f"{base_path}[{i}].{key}", val, out)
                    else:
                        out.append((f"{base_path}[{i}].{key}", str(val) if val is not None else ""))
            elif isinstance(item, (list, dict)):
                _expand_nested(f"{base_path}[{i}]", item, out)
            else:
                out.append((f"{base_path}[{i}]", str(item)))
    elif cv.kind == "map" and isinstance(cv.data, dict):
        for entry_key, entry_data in cv.data.items():
            if isinstance(entry_data, dict):
                for attr_key, val in entry_data.items():
                    if isinstance(val, CompositeValue):
                        _expand_composite(f"{base_path}.{entry_key}.{attr_key}", val, out)
                    elif isinstance(val, (dict, list)):
                        _expand_nested(f"{base_path}.{entry_key}.{attr_key}", val, out)
                    else:
                        out.append((
                            f"{base_path}.{entry_key}.{attr_key}",
                            str(val) if val is not None else "",
                        ))
            elif isinstance(entry_data, CompositeValue):
                _expand_composite(f"{base_path}.{entry_key}", entry_data, out)
            elif isinstance(entry_data, (list, dict)):
                _expand_nested(f"{base_path}.{entry_key}", entry_data, out)
            else:
                out.append((f"{base_path}.{entry_key}", str(entry_data)))


def _expand_nested(
    base_path: str,
    data: dict[str, object] | list[object],
    out: list[tuple[str, str]],
) -> None:
    """Expand plain nested dicts/lists (not wrapped in CompositeValue)."""
    if isinstance(data, dict):
        for key, val in data.items():
            child_path = f"{base_path}.{key}"
            if isinstance(val, CompositeValue):
                _expand_composite(child_path, val, out)
            elif isinstance(val, (dict, list)):
                _expand_nested(child_path, val, out)
            else:
                out.append((child_path, str(val) if val is not None else ""))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            child_path = f"{base_path}[{i}]"
            if isinstance(item, CompositeValue):
                _expand_composite(child_path, item, out)
            elif isinstance(item, (dict, list)):
                _expand_nested(child_path, item, out)
            else:
                out.append((child_path, str(item)))


# ── Strict bidirectional validation ──────────────────────────────────────


@dataclass
class StrictFidelityMismatch:
    """A single token mismatch between source and entity."""
    entity_id: str
    kind: str  # "missing_from_entity" | "fabricated_in_entity"
    token: tuple[str, ...]


class StrictFidelityError(Exception):
    """Raised when strict source fidelity check finds mismatches."""

    def __init__(self, message: str, mismatches: list[StrictFidelityMismatch]) -> None:
        super().__init__(message)
        self.mismatches = mismatches


def validate_strict_fidelity(
    source_leaves_map: dict[str, list[tuple[str, str]]],
    graph: EntityGraph,
    mode: str = "error",
) -> list[StrictFidelityMismatch]:
    """Strict bidirectional fidelity check.

    For each entity:
    1. Normalize source leaves → sorted list of token sequences
    2. Expand + normalize entity leaves → sorted list of token sequences
    3. Walk both sorted lists in lockstep (merge-join)
    4. Tokens in source but not entity → "missing_from_entity"
    5. Tokens in entity but not source → "fabricated_in_entity"

    Args:
        source_leaves_map: {entity_id: [(path, value), ...]} from collect_source_leaves()
        graph: The populated EntityGraph after extract_entities()
        mode: "error" (raises), "warn" (logs), "skip" (returns empty)

    Returns:
        List of mismatches (empty if all matched).

    Raises:
        StrictFidelityError: if mode=="error" and mismatches found.
    """
    if mode == "skip":
        return []

    all_mismatches: list[StrictFidelityMismatch] = []

    for entity_id, source_leaves in source_leaves_map.items():
        if not graph.has_entity(entity_id):
            # Entity not found — every source leaf is missing
            for path, value in source_leaves:
                all_mismatches.append(StrictFidelityMismatch(
                    entity_id=entity_id,
                    kind="missing_from_entity",
                    token=normalize_leaf(path, value),
                ))
            continue

        entity = graph.get_entity(entity_id)

        # Normalize source leaves
        src_tokens = sorted(normalize_leaf(p, v) for p, v in source_leaves)
        # Expand + normalize entity leaves
        entity_leaves = expand_entity_leaves(entity)
        ent_tokens = sorted(normalize_leaf(p, v) for p, v in entity_leaves)

        # Merge-join: walk both sorted lists with two pointers
        mismatches = _merge_join(entity_id, src_tokens, ent_tokens)
        all_mismatches.extend(mismatches)

    if all_mismatches:
        by_entity: dict[str, list[StrictFidelityMismatch]] = {}
        for m in all_mismatches:
            by_entity.setdefault(m.entity_id, []).append(m)

        lines = [f"Strict fidelity: {len(all_mismatches)} mismatches across {len(by_entity)} entities:"]
        for eid in sorted(by_entity):
            entity_mismatches = by_entity[eid]
            lines.append(f"  {eid}: {len(entity_mismatches)} mismatches")
            for m in entity_mismatches[:5]:
                lines.append(f"    {m.kind}: {'.'.join(m.token)}")
            if len(entity_mismatches) > 5:
                lines.append(f"    ... and {len(entity_mismatches) - 5} more")

        msg = "\n".join(lines)
        if mode == "error":
            raise StrictFidelityError(msg, all_mismatches)
        elif mode == "warn":
            logger.warning(msg)

    return all_mismatches


def _merge_join(
    entity_id: str,
    src_tokens: list[tuple[str, ...]],
    ent_tokens: list[tuple[str, ...]],
) -> list[StrictFidelityMismatch]:
    """Sorted merge-join of two token lists.

    Both lists must be sorted. Walks with two pointers, flagging any
    element present in one but not the other.
    """
    mismatches: list[StrictFidelityMismatch] = []
    i, j = 0, 0

    while i < len(src_tokens) and j < len(ent_tokens):
        if src_tokens[i] == ent_tokens[j]:
            i += 1
            j += 1
        elif src_tokens[i] < ent_tokens[j]:
            mismatches.append(StrictFidelityMismatch(
                entity_id=entity_id,
                kind="missing_from_entity",
                token=src_tokens[i],
            ))
            i += 1
        else:
            mismatches.append(StrictFidelityMismatch(
                entity_id=entity_id,
                kind="fabricated_in_entity",
                token=ent_tokens[j],
            ))
            j += 1

    # Remaining source tokens → missing
    while i < len(src_tokens):
        mismatches.append(StrictFidelityMismatch(
            entity_id=entity_id,
            kind="missing_from_entity",
            token=src_tokens[i],
        ))
        i += 1

    # Remaining entity tokens → fabricated
    while j < len(ent_tokens):
        mismatches.append(StrictFidelityMismatch(
            entity_id=entity_id,
            kind="fabricated_in_entity",
            token=ent_tokens[j],
        ))
        j += 1

    return mismatches
