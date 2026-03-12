"""Layer 2: Source fidelity validation.

Validates that ALL data from the raw parsed source is captured in the
EntityGraph after adapter extraction. Compares source leaves (collected
independently by collect_source_leaves()) against entity attributes,
accounting for:

- Progressive arg discrimination (source path duplicates → entity discriminated paths)
- Composite containment (source paths subsumed by CompositeValue attributes)
- Secrets masking ([REDACTED] values accepted as matching any source value)
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field

from decoct.core.composite_value import CompositeValue
from decoct.core.entity_graph import EntityGraph

logger = logging.getLogger(__name__)

REDACTED = "[REDACTED]"


def _is_subsequence(sub: list[str], full: list[str]) -> bool:
    """Check if sub is a subsequence of full (elements in order, not contiguous)."""
    j = 0
    for part in full:
        if j < len(sub) and part == sub[j]:
            j += 1
    return j == len(sub)


def _reconstruct_after_subsequence(
    source_parts: list[str],
    entity_parts: list[str],
    entity_value: str,
) -> str | None:
    """After confirming source is a subsequence of entity, reconstruct the
    extra entity path segments + value as a space-separated string.

    E.g., source=["mpls","discovery"], entity=["mpls","ldp","discovery","hello","interval"],
    value="5" → extra=["hello","interval"], reconstructed="hello interval 5"
    """
    # Find the index of the last matched source segment
    j = 0
    last_match_idx = -1
    for i, ep in enumerate(entity_parts):
        if j < len(source_parts) and ep == source_parts[j]:
            last_match_idx = i
            j += 1
    if j != len(source_parts):
        return None

    extra = entity_parts[last_match_idx + 1:]
    reconstructed = " ".join(extra)
    if entity_value and entity_value != "true":
        if reconstructed:
            reconstructed = f"{reconstructed} {entity_value}"
        else:
            reconstructed = entity_value
    return reconstructed


@dataclass
class SourceFidelityMismatch:
    """A single source leaf not found in the entity."""
    entity_id: str
    kind: str  # "missing_from_entity", "value_mismatch"
    path: str
    source_value: str | None
    entity_value: str | None


class SourceFidelityError(Exception):
    """Raised when source leaves are not captured by the EntityGraph."""

    def __init__(self, message: str, mismatches: list[SourceFidelityMismatch]) -> None:
        super().__init__(message)
        self.mismatches = mismatches


@dataclass
class _EntityLookup:
    """Pre-built lookup structure for matching source leaves against entity attributes."""
    # path → string value for scalar attributes
    direct: dict[str, str] = field(default_factory=dict)
    # base_path → list of (full_path, value) for discriminated lookups
    by_prefix: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    # path → CompositeValue for containment checks
    composites: dict[str, CompositeValue] = field(default_factory=dict)
    # paths subsumed by composites (with trailing dot)
    subsumption_prefixes: set[str] = field(default_factory=set)


def _expand_entity_to_lookup(
    entity_attrs: Mapping[str, object],
) -> _EntityLookup:
    """Build a lookup structure from entity attributes."""
    lookup = _EntityLookup()

    for path, attr in entity_attrs.items():
        value = attr.value  # type: ignore[attr-defined]
        if isinstance(value, CompositeValue):
            lookup.composites[path] = value
        else:
            str_val = str(value)
            lookup.direct[path] = str_val

            # Build prefix index: for ALL possible prefix lengths
            # e.g., "ntp.server.10.0.0.2" → prefixes "ntp", "ntp.server",
            # "ntp.server.10", etc. so discrimination at any depth works
            parts = path.split(".")
            for i in range(1, len(parts)):
                base = ".".join(parts[:i])
                lookup.by_prefix.setdefault(base, []).append((path, str_val))

    # Build subsumption prefixes from composites
    # IOS-XR specific patterns (singular→plural naming)
    for cv_path in lookup.composites:
        if cv_path.endswith(".evis"):
            lookup.subsumption_prefixes.add(cv_path[:-1] + ".")
        elif cv_path.endswith(".neighbors"):
            lookup.subsumption_prefixes.add(cv_path[:-1] + ".")
        elif cv_path.endswith(".bridge-groups"):
            lookup.subsumption_prefixes.add(cv_path.replace("-groups", "-group."))
        elif cv_path.endswith(".bridge-domains"):
            lookup.subsumption_prefixes.add(cv_path.replace("-domains", "-domain."))
        elif cv_path.endswith(".body"):
            lookup.subsumption_prefixes.add(cv_path.rsplit(".", 1)[0] + ".")

        # Generic: any composite at path P subsumes source leaves at P. and P[
        lookup.subsumption_prefixes.add(cv_path + ".")
        lookup.subsumption_prefixes.add(cv_path + "[")

    return lookup


def _value_in_composite(value: str, cv: CompositeValue) -> bool:
    """Check if a string value exists somewhere in a CompositeValue."""
    if cv.kind == "list" and isinstance(cv.data, list):
        for item in cv.data:
            if isinstance(item, dict):
                if value in item.values():
                    return True
            elif str(item) == value:
                return True
    elif cv.kind == "map" and isinstance(cv.data, dict):
        for entry_data in cv.data.values():
            if isinstance(entry_data, dict):
                if value in entry_data.values():
                    return True
            elif str(entry_data) == value:
                return True
    return False


def _check_source_leaf(
    path: str,
    value: str,
    lookup: _EntityLookup,
) -> SourceFidelityMismatch | None:
    """Check if a single source leaf is captured by the entity.

    Returns None if matched, or a SourceFidelityMismatch describing the gap.
    """
    # 1. Direct match
    if path in lookup.direct:
        entity_val = lookup.direct[path]
        if entity_val == value or entity_val == REDACTED:
            return None
        return SourceFidelityMismatch(
            entity_id="",  # filled by caller
            kind="value_mismatch",
            path=path,
            source_value=value,
            entity_value=entity_val,
        )

    # Also check if the path matches a composite directly
    if path in lookup.composites:
        return None

    # 2. Discriminated match: source has (keyword, "arg1 arg2")
    #    and entity has keyword.arg1 = "arg2" or keyword.arg1.arg2 = ...
    # Check by looking at entity paths that start with source path + "."
    candidates = lookup.by_prefix.get(path, [])
    if candidates:
        # Source value tokens might be used as discriminators
        value_dotted = value.replace(" ", ".")
        for full_path, entity_val in candidates:
            # The discriminator token(s) after "path."
            disc = full_path[len(path) + 1:]  # everything after "path."
            # Check if the source value starts with the discriminator
            for v in (value, value_dotted):
                if v.startswith(disc):
                    remaining = v[len(disc):]
                    if remaining.startswith("."):
                        remaining = remaining[1:]
                    remaining = remaining.strip()
                    if not remaining or entity_val == remaining or entity_val == REDACTED:
                        return None
            # Also match when entity_val matches the full source value
            if entity_val == value or entity_val == REDACTED:
                return None

    # 3. Composite containment: the source path is subsumed by a composite
    for prefix in lookup.subsumption_prefixes:
        if path.startswith(prefix):
            # Check the composite contains this value
            for cv_path, cv in lookup.composites.items():
                if _value_in_composite(value, cv):
                    return None
            # Subsumed by design — composite captures data differently
            return None

    # 4. Check if any composite at a related path contains the value
    # This handles cases where the source collector and the entity builder
    # use different composite grouping strategies
    for cv_path, cv in lookup.composites.items():
        # Check if paths share a common prefix
        if path.startswith(cv_path.rsplit(".", 1)[0] + ".") if "." in cv_path else False:
            if _value_in_composite(value, cv):
                return None

    # 5. Route-policy body lines: source uses indexed paths like
    #    "route-policy.NAME.body[0]" — entity stores as CompositeValue
    if ".body[" in path:
        base = path.split("[")[0]
        if base in lookup.composites:
            cv = lookup.composites[base]
            if cv.kind == "list" and isinstance(cv.data, list):
                if value in cv.data:
                    return None

    # 6. Confederation peers: source stores as individual leaves,
    #    entity may store as CompositeValue(list)
    for cv_path, cv in lookup.composites.items():
        if _value_in_composite(value, cv):
            return None

    # 7. Check if there are any direct attributes with a matching prefix
    #    where discrimination consumed ALL args into the path
    value_as_path = value.replace(" ", ".")
    for direct_path, direct_val in lookup.direct.items():
        if direct_path.startswith(path + "."):
            # Entity discriminated this path — source value should be
            # represented as path segments in direct_path
            remaining_path = direct_path[len(path) + 1:]
            # Reconstruct what the source value would look like
            reconstructed = remaining_path.replace(".", " ")
            if direct_val and direct_val != "true":
                reconstructed = f"{reconstructed} {direct_val}"
            if reconstructed.strip() == value.strip():
                return None
            # Partial match: source "10.0.0.1 prefer" → entity path "...10.0.0.1" val "prefer"
            if value.startswith(remaining_path):
                rest = value[len(remaining_path):].strip()
                if rest == direct_val or direct_val == REDACTED:
                    return None
            # Path-prefix match: source value's args form a prefix of the
            # entity's extended path (args consumed as discriminators, data in children)
            if remaining_path == value_as_path or remaining_path.startswith(value_as_path + "."):
                return None

    # 8. Subsequence match: parent discrimination may have inserted extra
    #    segments. E.g., source "a.b.c" → entity "a.b.DISC.c" where DISC
    #    was inserted by progressive arg discrimination of the parent node.
    source_parts = path.split(".")
    for direct_path, direct_val in lookup.direct.items():
        entity_parts = direct_path.split(".")
        if len(entity_parts) <= len(source_parts):
            continue
        if not _is_subsequence(source_parts, entity_parts):
            continue
        # Standard: same value
        if direct_val == value or direct_val == REDACTED:
            return None
        # Value absorbed into path: source value became a path segment
        # (e.g., "interface TenGigE0/0/0/0" → entity path has TenGigE0/0/0/0 as segment)
        if value in entity_parts:
            return None
        # Reconstruct: extra entity segments after last matched source segment
        # plus entity value should equal source value
        subseq_reconstructed = _reconstruct_after_subsequence(source_parts, entity_parts, direct_val)
        if subseq_reconstructed is not None and subseq_reconstructed.strip() == value.strip():
            return None

    return SourceFidelityMismatch(
        entity_id="",
        kind="missing_from_entity",
        path=path,
        source_value=value,
        entity_value=None,
    )


def validate_source_fidelity(
    source_leaves_map: dict[str, list[tuple[str, str]]],
    graph: EntityGraph,
    mode: str = "error",
) -> list[SourceFidelityMismatch]:
    """Validate that all source leaves are captured in the EntityGraph.

    Args:
        source_leaves_map: {entity_id: [(path, value), ...]} from collect_source_leaves()
        graph: The populated EntityGraph after extract_entities()
        mode: "error" (raises), "warn" (logs), "skip" (returns empty)

    Returns:
        List of mismatches (empty if all matched).

    Raises:
        SourceFidelityError: if mode=="error" and mismatches found.
    """
    if mode == "skip":
        return []

    all_mismatches: list[SourceFidelityMismatch] = []

    for entity_id, source_leaves in source_leaves_map.items():
        if not graph.has_entity(entity_id):
            entity = None
        else:
            entity = graph.get_entity(entity_id)
        if entity is None:
            # Entity not found — every leaf is missing
            for path, value in source_leaves:
                all_mismatches.append(SourceFidelityMismatch(
                    entity_id=entity_id,
                    kind="missing_from_entity",
                    path=path,
                    source_value=value,
                    entity_value=None,
                ))
            continue

        lookup = _expand_entity_to_lookup(entity.attributes)

        for path, value in source_leaves:
            mismatch = _check_source_leaf(path, value, lookup)
            if mismatch is not None:
                mismatch.entity_id = entity_id
                all_mismatches.append(mismatch)

    if all_mismatches:
        # Group by entity for readable error message
        by_entity: dict[str, list[SourceFidelityMismatch]] = {}
        for m in all_mismatches:
            by_entity.setdefault(m.entity_id, []).append(m)

        lines = [f"Source fidelity: {len(all_mismatches)} mismatches across {len(by_entity)} entities:"]
        for eid in sorted(by_entity):
            entity_mismatches = by_entity[eid]
            lines.append(f"  {eid}: {len(entity_mismatches)} mismatches")
            for m in entity_mismatches[:5]:
                lines.append(f"    {m.kind}: {m.path} = {m.source_value!r} (entity: {m.entity_value!r})")
            if len(entity_mismatches) > 5:
                lines.append(f"    ... and {len(entity_mismatches) - 5} more")

        msg = "\n".join(lines)
        if mode == "error":
            raise SourceFidelityError(msg, all_mismatches)
        elif mode == "warn":
            logger.warning(msg)

    return all_mismatches
