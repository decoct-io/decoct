"""Drop-fields pass — prune paths matching glob patterns."""

from __future__ import annotations

from fnmatch import fnmatch
from typing import Any

from decoct.passes.base import BasePass, PassResult, register_pass


def _path_matches(path: str, pattern: str) -> bool:
    """Check if a dotted path matches a glob pattern.

    Supports:
        ``*`` — matches a single path segment
        ``**`` — matches any number of segments (including zero)
    """
    path_parts = path.split(".")
    pattern_parts = pattern.split(".")
    return _match_parts(path_parts, 0, pattern_parts, 0)


def _match_parts(path: list[str], pi: int, pattern: list[str], qi: int) -> bool:
    """Recursive path segment matcher."""
    while pi < len(path) and qi < len(pattern):
        if pattern[qi] == "**":
            # ** matches zero or more segments
            if qi == len(pattern) - 1:
                return True
            for i in range(pi, len(path) + 1):
                if _match_parts(path, i, pattern, qi + 1):
                    return True
            return False
        elif fnmatch(path[pi], pattern[qi]):
            pi += 1
            qi += 1
        else:
            return False

    # Skip trailing ** patterns
    while qi < len(pattern) and pattern[qi] == "**":
        qi += 1

    return pi == len(path) and qi == len(pattern)


def _walk_and_drop(node: Any, path: str, patterns: list[str]) -> int:
    """Walk a YAML tree, dropping nodes whose paths match any pattern. Returns count removed."""
    count = 0

    if isinstance(node, dict):
        keys_to_drop = []
        for key in list(node.keys()):
            child_path = f"{path}.{key}" if path else str(key)
            if any(_path_matches(child_path, p) for p in patterns):
                keys_to_drop.append(key)
            elif isinstance(node[key], (dict, list)):
                count += _walk_and_drop(node[key], child_path, patterns)

        for key in keys_to_drop:
            del node[key]
            count += 1

    elif isinstance(node, list):
        for i, child in enumerate(node):
            child_path = f"{path}.{i}"
            if isinstance(child, (dict, list)):
                count += _walk_and_drop(child, child_path, patterns)

    return count


def drop_fields(doc: Any, patterns: list[str]) -> int:
    """Drop fields matching glob patterns from a YAML document in-place.

    Returns count of fields removed.
    """
    return _walk_and_drop(doc, "", patterns)


@register_pass
class DropFieldsPass(BasePass):
    """Remove fields matching glob patterns."""

    name = "drop-fields"
    run_after: list[str] = []
    run_before: list[str] = []

    def __init__(self, patterns: list[str] | None = None) -> None:
        self.patterns = patterns or []

    def run(self, doc: Any, **kwargs: Any) -> PassResult:
        patterns = self.patterns or kwargs.get("drop_patterns", [])
        count = drop_fields(doc, patterns)
        return PassResult(name=self.name, items_removed=count)
