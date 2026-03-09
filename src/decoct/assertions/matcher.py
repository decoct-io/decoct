"""Assertion match evaluator."""

from __future__ import annotations

import re
from typing import Any

from decoct.assertions.models import Assertion, Match
from decoct.passes.drop_fields import _path_matches

_SENTINEL = object()


def evaluate_match(match: Match, value: Any) -> bool:
    """Evaluate whether a value satisfies a match condition.

    Returns True if the value is conformant (matches the assertion).
    For ``exists`` matches the sentinel ``_SENTINEL`` signals an absent key.
    """
    if match.exists is not None:
        key_present = value is not _SENTINEL
        return key_present == match.exists
    if match.value is not None:
        return _values_equal(value, match.value)
    if match.pattern is not None:
        return bool(re.search(match.pattern, str(value)))
    if match.range is not None:
        try:
            num = float(value)
            return match.range[0] <= num <= match.range[1]
        except (ValueError, TypeError):
            return False
    if match.contains is not None:
        if isinstance(value, list):
            return match.contains in value
        return False
    if match.not_value is not None:
        return value != match.not_value
    return True


def _values_equal(actual: Any, expected: Any) -> bool:
    """Compare values with type coercion for YAML types."""
    if actual == expected:
        return True
    try:
        if str(actual).lower() == str(expected).lower():
            return True
    except (ValueError, TypeError):
        pass
    return False


def find_matches(
    node: Any,
    path: str,
    assertion: Assertion,
) -> list[tuple[str, Any, Any, str]]:
    """Find all (path, value, parent_node, key) tuples matching an assertion's path pattern.

    For ``exists`` assertions the path pattern is split: the prefix (all segments
    except the last) locates parent nodes, and the final segment is the key whose
    presence is tested. Absent keys are represented with the ``_SENTINEL`` value.
    """
    if assertion.match is None:
        return []

    if assertion.match.exists is not None:
        return _find_exists_matches(node, path, assertion.match.path)

    results: list[tuple[str, Any, Any, str]] = []
    _walk_for_matches(node, path, assertion.match.path, results)
    return results


def _find_exists_matches(
    node: Any,
    path: str,
    pattern: str,
) -> list[tuple[str, Any, Any, str]]:
    """Find matches for exists assertions.

    Splits the pattern into a parent pattern and a leaf key, walks to
    all parents, then checks if the leaf key is present.
    """
    parts = pattern.rsplit(".", 1)
    if len(parts) != 2:
        return []
    parent_pattern, leaf_key = parts

    # Find all parent nodes matching the parent pattern
    parent_results: list[tuple[str, Any, Any, str]] = []
    _walk_for_matches(node, path, parent_pattern, parent_results)

    results: list[tuple[str, Any, Any, str]] = []
    for parent_path, parent_val, _grandparent, _pkey in parent_results:
        if isinstance(parent_val, dict):
            child_path = f"{parent_path}.{leaf_key}"
            if leaf_key in parent_val:
                results.append((child_path, parent_val[leaf_key], parent_val, leaf_key))
            else:
                results.append((child_path, _SENTINEL, parent_val, leaf_key))

    return results


def _walk_for_matches(
    node: Any,
    current_path: str,
    pattern: str,
    results: list[tuple[str, Any, Any, str]],
) -> None:
    """Walk tree collecting (path, value, parent, key) for paths matching pattern."""
    if isinstance(node, dict):
        for key in list(node.keys()):
            child_path = f"{current_path}.{key}" if current_path else str(key)
            child = node[key]
            if _path_matches(child_path, pattern):
                results.append((child_path, child, node, str(key)))
            if isinstance(child, (dict, list)):
                _walk_for_matches(child, child_path, pattern, results)
    elif isinstance(node, list):
        for i, child in enumerate(node):
            child_path = f"{current_path}[{i}]"
            if isinstance(child, (dict, list)):
                _walk_for_matches(child, child_path, pattern, results)
