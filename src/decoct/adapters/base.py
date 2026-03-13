"""Base adapter for entity graph extraction.

Concrete adapter that handles YAML, JSON, INI, and XML via ``formats.py``.
Custom adapters (IOS-XR, Entra/Intune) subclass for non-standard formats.
"""

from __future__ import annotations

import configparser
import re
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from ruamel.yaml.comments import CommentedMap, CommentedSeq

from decoct.adapters.ingestion_models import IngestionSpec
from decoct.adapters.ingestion_spec import match_entry
from decoct.core.composite_value import CompositeValue
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import Attribute, Entity
from decoct.formats import detect_format, detect_platform, load_input

# ---------------------------------------------------------------------------
# ParseResult
# ---------------------------------------------------------------------------

@dataclass
class ParseResult:
    """Result of parsing a single input file."""

    doc: Any  # CommentedMap / CommentedSeq
    path: Path
    format: str  # "yaml", "json", "ini", "xml"


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------

def _coerce_value(raw: str) -> Any:
    """Coerce a string value from space-separated config to a native type."""
    lower = raw.lower()
    if lower in ("true", "yes", "on"):
        return True
    if lower in ("false", "no", "off"):
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def _value_to_str(value: Any) -> str:
    """Convert a scalar value to its canonical string representation."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _classify(value: Any) -> str:
    """Return the attribute type string for a scalar value."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "number"
    if isinstance(value, float):
        return "number"
    return "string"


def _is_empty(value: Any) -> bool:
    """Check if a value should be filtered out (None, empty list, empty dict)."""
    if value is None:
        return True
    if isinstance(value, (list, CommentedSeq)) and len(value) == 0:
        return True
    if isinstance(value, (dict, CommentedMap)) and len(value) == 0:
        return True
    return False


def _is_scalar(value: Any) -> bool:
    """Check if a value is a scalar (not a collection)."""
    return isinstance(value, (str, int, float, bool))


# ---------------------------------------------------------------------------
# Space-separated fallback parser
# ---------------------------------------------------------------------------

def _parse_space_separated(raw: str) -> CommentedMap:
    """Parse sshd-style ``Key Value`` (no ``=``) config into a CommentedMap.

    Only invoked when load_input() returns an empty CommentedMap for an INI
    file that has content — i.e. lines have no ``=`` and no ``[section]``
    headers.
    """
    cm = CommentedMap()
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue
        parts = stripped.split(None, 1)  # split on first whitespace
        if len(parts) == 2:
            cm[parts[0]] = _coerce_value(parts[1])
        elif len(parts) == 1:
            cm[parts[0]] = True  # flag-style key with no value
    return cm


def _parse_ini_tolerant(raw: str) -> CommentedMap:
    """Parse a sectioned INI file tolerant of duplicate keys.

    Standard configparser raises DuplicateOptionError on duplicate keys
    (e.g. systemd ``Environment=`` repeated).  This parser accumulates
    duplicates into a comma-separated string, preserving all values.
    """
    cm = CommentedMap()
    current_section: str | None = None
    section_map: CommentedMap | None = None

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue
        # Section header?
        m = re.match(r"^\[(.+)\]\s*$", stripped)
        if m:
            current_section = m.group(1)
            section_map = CommentedMap()
            cm[current_section] = section_map
            continue
        if current_section is None or section_map is None:
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip().lower()  # configparser lowercases keys
        value = value.strip()
        coerced = _coerce_value(value)
        if key in section_map:
            # Accumulate duplicate keys as comma-separated string
            existing = section_map[key]
            section_map[key] = f"{existing},{coerced}"
        else:
            section_map[key] = coerced
    return cm


# ---------------------------------------------------------------------------
# Homogeneous map detection
# ---------------------------------------------------------------------------

def _is_homogeneous_map(
    value: Any,
    min_children: int = 1,
    jaccard_threshold: float = 0.5,
) -> bool:
    """Check if a dict-of-dicts has structurally similar children.

    Returns True if ``value`` is a dict with >= ``min_children`` dict children
    whose average pairwise Jaccard similarity of key sets >= ``jaccard_threshold``.

    For a single child, Jaccard is not applicable — returns True if the child
    is a dict with >= 2 keys (non-trivial structure worth treating as composite).
    """
    if not isinstance(value, (dict, CommentedMap)):
        return False
    children = [v for v in value.values() if isinstance(v, (dict, CommentedMap))]
    if len(children) < min_children or len(children) != len(value):
        return False

    # Single child: accept if it has enough keys to be worth compositing
    if len(children) == 1:
        return len(children[0]) >= 2

    key_sets = [frozenset(child.keys()) for child in children]

    # Compute average pairwise Jaccard similarity
    n = len(key_sets)

    total_sim = 0.0
    pair_count = 0
    for i in range(n):
        for j in range(i + 1, n):
            union = key_sets[i] | key_sets[j]
            if union:
                total_sim += len(key_sets[i] & key_sets[j]) / len(union)
            else:
                total_sim += 1.0
            pair_count += 1

    avg_sim = total_sim / pair_count if pair_count else 0.0
    return avg_sim >= jaccard_threshold


# ---------------------------------------------------------------------------
# Composite override matching
# ---------------------------------------------------------------------------

def _match_composite_override(
    path: str,
    overrides: dict[str, str] | None,
) -> str | None:
    """Match a dotted path against composite override patterns (fnmatch).

    Returns the kind string ("map" or "list") if matched, None otherwise.
    """
    if not overrides:
        return None
    for pattern, kind in overrides.items():
        if fnmatch(path, pattern):
            return kind
    return None


# ---------------------------------------------------------------------------
# Generic document flattening
# ---------------------------------------------------------------------------

def flatten_doc(
    doc: Any,
    prefix: str = "",
    composite_overrides: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, CompositeValue]]:
    """Flatten a parsed document into dotted-path attributes.

    Returns ``(flat_attrs, composites)`` — scalar attributes as strings and
    composite values (arrays of objects) as CompositeValue instances.

    Rules:
    - Nested dicts → recurse with dotted prefix
    - Scalars → string conversion
    - None / empty dict / empty list → skip
    - Arrays of scalars → comma-separated string
    - Arrays of objects → CompositeValue(kind="list")
    - Root list: single-element → unwrap, multi-element → CompositeValue
    """
    flat: dict[str, str] = {}
    composites: dict[str, CompositeValue] = {}

    if isinstance(doc, (list, CommentedSeq)):
        # Root-level list (e.g., Ansible playbooks)
        if len(doc) == 1 and isinstance(doc[0], (dict, CommentedMap)):
            # Single-element list — unwrap
            return flatten_doc(doc[0], prefix, composite_overrides)
        if len(doc) > 0 and all(isinstance(item, (dict, CommentedMap)) for item in doc):
            # Multi-element list of objects → CompositeValue at root
            items = [_flatten_composite_item(item) for item in doc]
            composites[prefix.rstrip(".") or "_root"] = CompositeValue.from_list(items)
            return flat, composites
        if len(doc) > 0 and all(_is_scalar(item) for item in doc):
            flat[prefix.rstrip(".") or "_root"] = ",".join(_value_to_str(x) for x in doc)
            return flat, composites
        return flat, composites

    if not isinstance(doc, (dict, CommentedMap)):
        # Bare scalar at root — unlikely but handle gracefully
        if not _is_empty(doc):
            flat[prefix.rstrip(".") or "_root"] = _value_to_str(doc)
        return flat, composites

    for key, value in doc.items():
        path = f"{prefix}{key}"

        if _is_empty(value):
            continue

        if isinstance(value, (dict, CommentedMap)):
            override_kind = _match_composite_override(path, composite_overrides)
            if override_kind == "map":
                # Forced map composite from ingestion spec
                map_items: dict[str, dict[str, str]] = {}
                for item_key, item_value in value.items():
                    if isinstance(item_value, (dict, CommentedMap)):
                        map_items[item_key] = _flatten_composite_item(item_value)
                    else:
                        map_items[item_key] = {"_value": _value_to_str(item_value)}
                composites[path] = CompositeValue.from_map(map_items)
            elif override_kind == "list":
                # Forced list composite from ingestion spec
                items = []
                for item_value in value.values():
                    if isinstance(item_value, (dict, CommentedMap)):
                        items.append(_flatten_composite_item(item_value))
                    else:
                        items.append({"_value": _value_to_str(item_value)})
                composites[path] = CompositeValue.from_list(items)
            elif _is_homogeneous_map(value):
                # Map of similarly-structured items → CompositeValue(kind="map")
                auto_map_items: dict[str, dict[str, str]] = {}
                for item_key, item_value in value.items():
                    auto_map_items[item_key] = _flatten_composite_item(item_value)
                composites[path] = CompositeValue.from_map(auto_map_items)
            else:
                child_flat, child_composites = flatten_doc(
                    value, f"{path}.", composite_overrides,
                )
                flat.update(child_flat)
                composites.update(child_composites)

        elif isinstance(value, (list, CommentedSeq)):
            if len(value) == 0:
                continue
            if all(_is_scalar(item) for item in value):
                # Array of scalars → comma-separated
                flat[path] = ",".join(_value_to_str(x) for x in value)
            elif all(isinstance(item, (dict, CommentedMap)) for item in value):
                # Array of objects → CompositeValue
                items = [_flatten_composite_item(item) for item in value]
                composites[path] = CompositeValue.from_list(items)
            else:
                # Mixed array — treat scalars as strings, skip nested
                scalar_parts = [_value_to_str(x) for x in value if _is_scalar(x)]
                if scalar_parts:
                    flat[path] = ",".join(scalar_parts)

        else:
            flat[path] = _value_to_str(value)

    return flat, composites


def _flatten_composite_item(item: Any) -> dict[str, str]:
    """Flatten a single object inside a composite array to string-valued dict."""
    result: dict[str, str] = {}
    if not isinstance(item, (dict, CommentedMap)):
        return result
    for k, v in item.items():
        if _is_empty(v):
            continue
        if isinstance(v, (dict, CommentedMap)):
            for ck, cv in v.items():
                if not _is_empty(cv):
                    if isinstance(cv, (dict, CommentedMap)):
                        # Recurse one more level
                        for dk, dv in cv.items():
                            if not _is_empty(dv):
                                result[f"{k}.{ck}.{dk}"] = _value_to_str(dv)
                    else:
                        result[f"{k}.{ck}"] = _value_to_str(cv)
        elif isinstance(v, (list, CommentedSeq)):
            if v and all(_is_scalar(x) for x in v):
                result[k] = ",".join(_value_to_str(x) for x in v)
            elif v:
                for i, entry in enumerate(v):
                    if isinstance(entry, (dict, CommentedMap)):
                        for ek, ev in entry.items():
                            if not _is_empty(ev):
                                result[f"{k}.{i}.{ek}"] = _value_to_str(ev)
                    elif not _is_empty(entry):
                        result[f"{k}.{i}"] = _value_to_str(entry)
        else:
            result[k] = _value_to_str(v)
    return result


# ---------------------------------------------------------------------------
# Document leaf walker
# ---------------------------------------------------------------------------

def _walk_doc_leaves(
    doc: Any,
    prefix: str = "",
) -> list[tuple[str, str]]:
    """Walk a parsed YAML/JSON/INI/XML document collecting ALL leaf data points.

    Independent of flatten_doc() — walks the raw parsed structure directly.
    Produces a flat list of (dotted_path, string_value) tuples.
    """
    leaves: list[tuple[str, str]] = []

    if isinstance(doc, (dict, CommentedMap)):
        for key, value in doc.items():
            path = f"{prefix}{key}" if prefix else str(key)
            if _is_empty(value):
                continue
            if isinstance(value, (dict, CommentedMap)):
                leaves.extend(_walk_doc_leaves(value, f"{path}."))
            elif isinstance(value, (list, CommentedSeq)):
                if len(value) == 0:
                    continue
                if all(_is_scalar(item) for item in value):
                    # Emit as comma-separated, matching flatten_doc() output
                    leaves.append((path, ",".join(_value_to_str(x) for x in value)))
                elif all(isinstance(item, (dict, CommentedMap)) for item in value):
                    # All objects → walk each
                    for i, item in enumerate(value):
                        leaves.extend(_walk_doc_leaves(item, f"{path}[{i}]."))
                else:
                    # Mixed array — only emit scalars, matching flatten_doc()
                    scalar_parts = [_value_to_str(x) for x in value if _is_scalar(x)]
                    if scalar_parts:
                        leaves.append((path, ",".join(scalar_parts)))
            else:
                leaves.append((path, _value_to_str(value)))
    elif isinstance(doc, (list, CommentedSeq)):
        # Match flatten_doc() root-level list handling:
        # - Single-element list of dict → unwrap (no [0] prefix)
        # - Multi-element list of dicts → indexed paths
        if (
            not prefix
            and len(doc) == 1
            and isinstance(doc[0], (dict, CommentedMap))
        ):
            # Single-element root list — unwrap, matching flatten_doc()
            leaves.extend(_walk_doc_leaves(doc[0], prefix))
        else:
            for i, item in enumerate(doc):
                path = f"{prefix}[{i}]" if prefix else f"[{i}]"
                if isinstance(item, (dict, CommentedMap)):
                    leaves.extend(_walk_doc_leaves(item, f"{path.rstrip('.')}."))
                elif not _is_empty(item):
                    leaves.append((path, _value_to_str(item)))
    elif not _is_empty(doc):
        path = prefix.rstrip(".") or "_root"
        leaves.append((path, _value_to_str(doc)))

    return leaves


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class BaseAdapter:
    """Concrete adapter for standard structured formats (YAML, JSON, INI, XML).

    Parses any of the four standard formats via ``load_input()`` and extracts
    one entity per file. Custom adapters (IOS-XR, Entra/Intune) subclass for
    non-standard formats.
    """

    def __init__(self, ingestion_spec: IngestionSpec | None = None) -> None:
        self._spec = ingestion_spec

    def source_type(self) -> str:
        """Return the adapter type identifier."""
        return "standard"

    def parse(self, source: str) -> ParseResult:
        """Parse a file into a ParseResult."""
        path = Path(source)
        raw = path.read_text()
        fmt = detect_format(path)

        try:
            doc, _ = load_input(path)
        except configparser.Error:
            # Duplicate keys or other INI issues — use tolerant parser
            doc = _parse_ini_tolerant(raw)

        # Fallback: if INI parsed empty but file has content, try space-separated
        if fmt == "ini" and isinstance(doc, CommentedMap) and len(doc) == 0 and raw.strip():
            doc = _parse_space_separated(raw)

        return ParseResult(doc=doc, path=path, format=fmt)

    def extract_entities(self, parsed: Any, graph: EntityGraph) -> None:
        """Extract a single entity from a parsed document into the graph."""
        if isinstance(parsed, ParseResult):
            doc, path = parsed.doc, parsed.path
        else:
            # Legacy tuple form (backward compat with HybridInfraAdapter)
            doc, path = parsed

        entity_id = path.stem
        entity = Entity(id=entity_id)
        entity.schema_type_hint = detect_platform(doc)

        # Apply ingestion spec overrides
        composite_overrides: dict[str, str] | None = None
        if self._spec is not None:
            entry = match_entry(self._spec, entity_id)
            if entry is not None:
                entity.schema_type_hint = entry.platform
                if entry.composite_paths:
                    composite_overrides = {
                        cp.path: cp.kind for cp in entry.composite_paths
                    }

        flat, composites = flatten_doc(doc, composite_overrides=composite_overrides)

        # Add flat attributes
        for p, v in sorted(flat.items()):
            entity.attributes[p] = Attribute(
                path=p, value=v, type=_classify(v), source=entity_id,
            )

        # Add composite attributes
        for p, cv in sorted(composites.items()):
            entity.attributes[p] = Attribute(
                path=p, value=cv, type=cv.kind, source=entity_id,
            )

        graph.add_entity(entity)

    def collect_source_leaves(self, parsed: Any) -> dict[str, list[tuple[str, str]]]:
        """Collect ALL leaf data points from parsed document.

        Independent of extract_entities() — walks the raw parsed structure
        directly using _walk_doc_leaves().
        """
        if isinstance(parsed, ParseResult):
            doc, path = parsed.doc, parsed.path
        else:
            doc, path = parsed

        entity_id = path.stem
        leaves = _walk_doc_leaves(doc)
        return {entity_id: leaves}

    def extract_relationships(self, graph: EntityGraph) -> None:
        """Extract inter-entity relationships using ingestion spec hints.

        Only activated when spec entries have relationship_hints.
        For each entity, finds matching spec entry, iterates hints,
        looks up target entities by matching attribute values.
        """
        if self._spec is None:
            return

        for entity in graph.entities:
            entry = match_entry(self._spec, entity.id)
            if entry is None or not entry.relationship_hints:
                continue

            for hint in entry.relationship_hints:
                source_attr = entity.attributes.get(hint.source_field)
                if source_attr is None:
                    continue
                source_value = source_attr.value

                for target in graph.entities:
                    if target.id == entity.id:
                        continue
                    target_attr = target.attributes.get(hint.target_field)
                    if target_attr is not None and target_attr.value == source_value:
                        graph.add_relationship(entity.id, hint.label, target.id)

    def secret_paths(self) -> list[str]:
        """Extra path patterns that indicate secrets for this adapter.

        Override to add adapter-specific secret paths (e.g. TACACS keys,
        SNMP communities). These are appended to the global DEFAULT_SECRET_PATHS
        by the pipeline.

        Returns empty list by default — only global patterns apply.
        """
        return []

    def secret_value_patterns(self) -> list[tuple[str, re.Pattern[str]]] | None:
        """Extra value-level regex patterns for this adapter.

        Override to add patterns that match secret content inside attribute
        *values* (e.g. IOS-XR ``key 7 ...``). These run after core detection.

        Returns None by default — no extra value patterns.
        """
        return None
