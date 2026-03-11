"""Segment-aware glob matching over dotted attribute paths (R3)."""

from __future__ import annotations

from fnmatch import fnmatch


def matches_path(attr_path: str, pattern: str) -> bool:
    """Check if a dotted attribute path matches a glob pattern.

    Segment-aware matching:
    - ``*`` matches exactly one segment: ``router.bgp.*`` matches
      ``router.bgp.65002`` but not ``router.bgp.65002.nsr``
    - ``**`` matches zero or more segments: ``router.bgp.**`` matches
      anything starting with ``router.bgp.``
    - Per-segment ``fnmatch`` for character-level wildcards within segments.
    """
    path_parts = attr_path.split(".")
    pattern_parts = pattern.split(".")
    return _match_segments(path_parts, 0, pattern_parts, 0)


def _match_segments(
    path: list[str],
    pi: int,
    pattern: list[str],
    qi: int,
) -> bool:
    """Recursive segment matcher."""
    while qi < len(pattern):
        seg = pattern[qi]

        if seg == "**":
            # ** matches zero or more segments
            # Try matching the rest of the pattern at every remaining position
            for k in range(pi, len(path) + 1):
                if _match_segments(path, k, pattern, qi + 1):
                    return True
            return False

        # Need a path segment to match against
        if pi >= len(path):
            return False

        # Single-segment match (supports fnmatch wildcards like * and ?)
        if not fnmatch(path[pi], seg):
            return False

        pi += 1
        qi += 1

    # Pattern exhausted — path must also be exhausted
    return pi == len(path)


def collect_matching_paths(
    all_paths: set[str],
    include_patterns: list[str],
    related_patterns: list[str] | None = None,
) -> set[str]:
    """Collect all paths from ``all_paths`` matching include or related patterns.

    Returns the union of matches from both pattern lists.
    """
    patterns = list(include_patterns)
    if related_patterns:
        patterns.extend(related_patterns)

    matched: set[str] = set()
    for path in all_paths:
        for pattern in patterns:
            if matches_path(path, pattern):
                matched.add(path)
                break

    return matched
