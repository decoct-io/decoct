"""Hybrid infrastructure adapter: generic multi-format parser and entity extraction.

Handles mixed-format infrastructure configs (YAML, JSON, INI/conf) using
existing load_input() and detect_platform() from formats.py.  Each file
becomes one entity. No hardcoded schema names, field names, or format-
specific logic beyond a space-separated fallback for sshd-style configs.
"""

from __future__ import annotations

import configparser
import re
from pathlib import Path
from typing import Any

from ruamel.yaml.comments import CommentedMap, CommentedSeq

from decoct.adapters.base import BaseAdapter
from decoct.core.composite_value import CompositeValue
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import Attribute, Entity
from decoct.formats import detect_format, detect_platform, load_input

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
# Generic document flattening
# ---------------------------------------------------------------------------

def flatten_doc(
    doc: Any,
    prefix: str = "",
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
            return flatten_doc(doc[0], prefix)
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
            if _is_homogeneous_map(value):
                # Map of similarly-structured items → CompositeValue(kind="map")
                map_items: dict[str, dict[str, str]] = {}
                for item_key, item_value in value.items():
                    map_items[item_key] = _flatten_composite_item(item_value)
                composites[path] = CompositeValue.from_map(map_items)
            else:
                child_flat, child_composites = flatten_doc(value, f"{path}.")
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
# Adapter
# ---------------------------------------------------------------------------

class HybridInfraAdapter(BaseAdapter):
    """Generic multi-format infrastructure adapter.

    Parses YAML, JSON, and INI/conf files via ``load_input()`` and extracts
    one entity per file.  Schema type hints come from ``detect_platform()``.
    No relationships — the entity graph still forms types and classes without them.
    """

    def source_type(self) -> str:
        return "hybrid-infra"

    def parse(self, source: str) -> tuple[Any, Path]:
        """Parse a file into (document, file_path)."""
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
        return doc, path

    def extract_entities(self, parsed: Any, graph: EntityGraph) -> None:
        """Extract a single entity from a parsed document into the graph."""
        doc, path = parsed
        entity_id = path.stem

        entity = Entity(id=entity_id)
        entity.schema_type_hint = detect_platform(doc)

        flat, composites = flatten_doc(doc)

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
