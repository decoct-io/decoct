"""Keep-fields pass — retain only paths matching patterns, prune everything else."""

from __future__ import annotations

from typing import Any

from decoct.passes.base import BasePass, PassResult, register_pass
from decoct.passes.drop_fields import _path_matches


def _collect_keep_paths(node: Any, path: str, patterns: list[str], keep: set[str]) -> None:
    """Collect all paths (and their ancestors) that match keep patterns."""
    if isinstance(node, dict):
        for key in node:
            child_path = f"{path}.{key}" if path else str(key)
            if any(_path_matches(child_path, p) for p in patterns):
                # Mark this path and all ancestors
                _mark_ancestors(child_path, keep)
                # Also mark all descendants
                _mark_descendants(node[key], child_path, keep)
            elif isinstance(node[key], (dict, list)):
                _collect_keep_paths(node[key], child_path, patterns, keep)
    elif isinstance(node, list):
        for i, child in enumerate(node):
            child_path = f"{path}[{i}]"
            if isinstance(child, (dict, list)):
                _collect_keep_paths(child, child_path, patterns, keep)


def _strip_list_indices(path: str) -> str:
    """Remove [N] list index notation from a path."""
    result: list[str] = []
    i = 0
    while i < len(path):
        if path[i] == "[":
            while i < len(path) and path[i] != "]":
                i += 1
            i += 1  # skip ]
        else:
            result.append(path[i])
            i += 1
    return "".join(result)


def _mark_ancestors(path: str, keep: set[str]) -> None:
    """Mark a path and all its ancestor paths."""
    # Mark both the raw path and the version with list indices stripped,
    # since _prune uses plain dotted paths for dict keys.
    for p in {path, _strip_list_indices(path)}:
        keep.add(p)
        parts = p.split(".")
        for i in range(1, len(parts)):
            keep.add(".".join(parts[:i]))


def _mark_descendants(node: Any, path: str, keep: set[str]) -> None:
    """Mark all descendant paths of a node."""
    keep.add(path)
    if isinstance(node, dict):
        for key in node:
            child_path = f"{path}.{key}"
            keep.add(child_path)
            _mark_descendants(node[key], child_path, keep)
    elif isinstance(node, list):
        for i, child in enumerate(node):
            child_path = f"{path}[{i}]"
            keep.add(child_path)
            _mark_descendants(child, child_path, keep)


def _prune(node: Any, path: str, keep: set[str]) -> int:
    """Remove all paths not in the keep set. Returns count removed."""
    count = 0
    if isinstance(node, dict):
        keys_to_drop = []
        for key in list(node.keys()):
            child_path = f"{path}.{key}" if path else str(key)
            if child_path not in keep:
                keys_to_drop.append(key)
            elif isinstance(node[key], (dict, list)):
                count += _prune(node[key], child_path, keep)
        for key in keys_to_drop:
            del node[key]
            count += 1
    return count


def keep_fields(doc: Any, patterns: list[str]) -> int:
    """Keep only fields matching patterns, prune everything else.

    Returns count of fields removed.
    """
    keep: set[str] = set()
    _collect_keep_paths(doc, "", patterns, keep)
    return _prune(doc, "", keep)


@register_pass
class KeepFieldsPass(BasePass):
    """Retain only fields matching patterns, drop everything else."""

    name = "keep-fields"
    run_after: list[str] = []
    run_before: list[str] = []

    def __init__(self, patterns: list[str] | None = None) -> None:
        self.patterns = patterns or []

    def run(self, doc: Any, **kwargs: Any) -> PassResult:
        patterns = self.patterns or kwargs.get("keep_patterns", [])
        count = keep_fields(doc, patterns)
        return PassResult(name=self.name, items_removed=count)
