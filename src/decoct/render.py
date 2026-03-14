"""YAML rendering with compact, LLM-friendly formatting rules.

Rules implemented:
1. Dot-notation collapse — single-child dict chains become ``a.b.c: val``
2. Flow maps at leaf dicts — ``{k: v, k: v}`` when ≤6 leaf-only keys
3. Flow maps for list items — items with only leaves/small dicts rendered as flow maps
4. No subclass refs in Tier B — class bodies must not contain ``_list_class``/``_instances``/``_also``
5. ``_identity``/``_discriminators`` as flow sequences — ``[a, b]`` not block list
"""

from __future__ import annotations

from io import StringIO
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

_FLOW_MAP_MAX_KEYS = 6
_SUBCLASS_REF_KEYS = {"_list_class", "_instances", "_also"}


# ---------------------------------------------------------------------------
# Rule 1: Dot-notation collapse
# ---------------------------------------------------------------------------

def collapse_single_child_dicts(data: Any) -> Any:
    """Collapse single-child dict chains into dotted keys.

    ``{a: {b: {c: 1}}}`` becomes ``{a.b.c: 1}``.

    Does NOT collapse when the parent key starts with ``_``, but still
    recurses into its value.  Stops at: leaf, list, dict with 2+ keys,
    or ``_``-prefixed child key.
    """
    if isinstance(data, list):
        return [collapse_single_child_dicts(item) for item in data]
    if not isinstance(data, dict):
        return data

    result: dict[str, Any] = {}
    for key, value in data.items():
        value = collapse_single_child_dicts(value)  # recurse into value first
        # Don't collapse if parent key is a control key
        if key.startswith("_"):
            result[key] = value
            continue
        # Collapse chain: while value is single-key dict with non-control child
        while (
            isinstance(value, dict)
            and len(value) == 1
            and not next(iter(value.keys())).startswith("_")
        ):
            child_key = next(iter(value.keys()))
            key = f"{key}.{child_key}"
            value = value[child_key]
        result[key] = value
    return result


# ---------------------------------------------------------------------------
# Rule 4: No subclass refs in Tier B class bodies
# ---------------------------------------------------------------------------

def assert_no_subclass_refs(tier_b: dict[str, Any]) -> None:
    """Assert that no class body in tier_b contains ``_list_class``, ``_instances``, or ``_also``.

    The ``_list_classes`` top-level key is excluded from the check.
    """
    for class_name, class_body in tier_b.items():
        if class_name == "_list_classes":
            continue
        if not isinstance(class_body, dict):
            continue
        bad_keys = _SUBCLASS_REF_KEYS & set(class_body.keys())
        if bad_keys:
            raise ValueError(
                f"Tier B class '{class_name}' contains subclass ref keys: {sorted(bad_keys)}"
            )


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------

def _is_scalar(v: Any) -> bool:
    """True if *v* is a YAML scalar (not a dict or list)."""
    return not isinstance(v, (dict, list, CommentedMap, CommentedSeq))


def _is_flow_eligible_dict(d: dict[str, Any] | CommentedMap) -> bool:
    """Rule 2: dict with all-scalar values and ≤6 keys."""
    return len(d) <= _FLOW_MAP_MAX_KEYS and all(_is_scalar(v) for v in d.values())


def _is_flow_eligible_list_item(item: Any) -> bool:
    """Rule 3: list item is a dict whose values are all scalars or flow-eligible dicts."""
    if not isinstance(item, (dict, CommentedMap)):
        return False
    for v in item.values():
        if _is_scalar(v):
            continue
        if isinstance(v, (dict, CommentedMap)) and _is_flow_eligible_dict(v):
            continue
        return False
    return True


def _sort_key(k: str) -> tuple[bool, str]:
    """Sort ``_``-prefixed keys first, then alphabetically."""
    return (not k.startswith("_"), k)


# ---------------------------------------------------------------------------
# Conversion + style annotation
# ---------------------------------------------------------------------------

def _to_commented(data: Any, sort_keys: bool = True) -> Any:
    """Recursively convert plain dict/list to CommentedMap/CommentedSeq."""
    if isinstance(data, dict):
        cm = CommentedMap()
        keys = sorted(data.keys(), key=_sort_key) if sort_keys else list(data.keys())
        for k in keys:
            cm[k] = _to_commented(data[k], sort_keys)
        return cm
    if isinstance(data, list):
        seq = CommentedSeq(_to_commented(item, sort_keys) for item in data)
        return seq
    return data


def _apply_styles(node: Any) -> None:
    """Walk the tree and set flow styles per the rendering rules."""
    if isinstance(node, CommentedMap):
        for key, value in node.items():
            # Rule 5: _identity / _discriminators as flow sequences
            if key in ("_identity", "_discriminators") and isinstance(value, CommentedSeq):
                value.fa.set_flow_style()
                continue
            # Recurse first so children are styled before parent check
            _apply_styles(value)
        # Rule 2: flow map at leaf dicts
        if _is_flow_eligible_dict(node):
            node.fa.set_flow_style()
    elif isinstance(node, CommentedSeq):
        # Rule 3: flow maps for list items
        all_eligible = len(node) > 0 and all(_is_flow_eligible_list_item(item) for item in node)
        for item in node:
            _apply_styles(item)
        if all_eligible:
            for item in node:
                if isinstance(item, CommentedMap):
                    item.fa.set_flow_style()


def to_styled_yaml(data: Any, sort_keys: bool = True) -> Any:
    """Convert plain data to styled ``CommentedMap``/``CommentedSeq``.

    Applies all flow-style rules (2, 3, 5).
    """
    cm = _to_commented(data, sort_keys)
    _apply_styles(cm)
    return cm


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def render_yaml(data: Any, sort_keys: bool = True, width: int = 120) -> str:
    """Render data as compact, LLM-friendly YAML.

    1. Collapse single-child dict chains (Rule 1)
    2. Convert to ``CommentedMap``/``CommentedSeq`` with style annotations (Rules 2, 3, 5)
    3. Dump with ``ruamel.yaml`` round-trip mode
    """
    collapsed = collapse_single_child_dicts(data)
    styled = to_styled_yaml(collapsed, sort_keys=sort_keys)

    y = YAML(typ="rt")
    y.default_flow_style = False
    y.width = width
    y.allow_unicode = True

    buf = StringIO()
    y.dump(styled, buf)
    return buf.getvalue()
