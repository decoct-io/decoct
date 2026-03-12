"""Layer 1: Parser structure validation.

Validates the IOS-XR parser's correctness by comparing raw text section
structure against parsed ConfigTree section structure WITHOUT using the
parser itself.

Raw text counting uses ONLY indentation to determine section ownership.
If the parser has a bug that moves data between sections (e.g., consuming
address-family lines as route-policy body), the counts will diverge.
"""

from __future__ import annotations

import logging

from decoct.adapters.iosxr import (
    POLICY_TERMINATORS,
    SECTION_KEYWORDS,
    TWO_WORD_SECTIONS,
    ConfigNode,
    IosxrConfigTree,
)

logger = logging.getLogger(__name__)


class ParserStructureError(Exception):
    """Raised when raw text section structure diverges from parsed tree."""

    def __init__(self, message: str, discrepancies: list[tuple[str, int, int]]) -> None:
        super().__init__(message)
        self.discrepancies = discrepancies


def _section_key_from_tokens(tokens: list[str]) -> str:
    """Compute a section key from the first tokens of a top-level line.

    Mirrors _get_section_key() logic for top-level sections only.
    """
    if not tokens:
        return ""

    keyword = tokens[0]
    args = tokens[1:]

    # Two-word sections (e.g., "bridge group")
    for tw in TWO_WORD_SECTIONS:
        parts = tw.split()
        if keyword == parts[0] and args and args[0] == parts[1]:
            spec = SECTION_KEYWORDS[tw]
            remaining = args[1:]
            if spec == "all":
                return tw.replace(" ", "-") + "." + "-".join(remaining)
            n = int(spec)
            consumed = remaining[:n]
            return tw.replace(" ", "-") + "." + ".".join(consumed) if consumed else tw.replace(" ", "-")

    if keyword in SECTION_KEYWORDS:
        spec = SECTION_KEYWORDS[keyword]
        if spec == "all":
            return keyword + "." + "-".join(args) if args else keyword
        n = int(spec)
        consumed = args[:n]
        return keyword + "." + ".".join(consumed) if consumed else keyword

    return keyword


def count_section_lines(cfg_text: str) -> dict[str, int]:
    """Count data-bearing lines per top-level section using ONLY indentation.

    Walks raw .cfg text, tracking indent depth to determine section ownership.
    A 'section' is a top-level keyword (indent=0). Lines at deeper indents
    belong to the most recent top-level section.

    Skips: blank lines, '!' terminators, 'end', '!!' header comments.
    Returns: {"router.bgp.1": 45, "interface.Loopback0": 12, "ntp": 3, ...}

    Route-policy definitions (``route-policy NAME`` at indent=0 with 2 tokens)
    consume lines until ``end-policy``, counting body lines as belonging to
    that route-policy section.
    """
    counts: dict[str, int] = {}
    current_section: str | None = None
    in_policy = False

    for line in cfg_text.splitlines():
        stripped = line.rstrip()

        # Skip blanks
        if not stripped:
            continue

        # Skip !! header comments
        if stripped.startswith("!!"):
            continue

        # Skip ! terminators/comments
        if stripped.strip() == "!":
            continue
        if stripped.strip().startswith("!"):
            continue

        # Skip 'end'
        if stripped.strip() == "end":
            break

        # If inside a route-policy block, count body lines
        if in_policy:
            if stripped.strip() in POLICY_TERMINATORS:
                in_policy = False
                continue
            if current_section is not None:
                counts[current_section] = counts.get(current_section, 0) + 1
            continue

        # Calculate indentation
        depth = len(line) - len(line.lstrip(" "))

        if depth == 0:
            # New top-level section
            tokens = stripped.split()

            # Handle 'no' prefix
            if tokens and tokens[0] == "no" and len(tokens) > 1:
                tokens = tokens[1:]

            current_section = _section_key_from_tokens(tokens)
            counts[current_section] = counts.get(current_section, 0) + 1

            # Check for route-policy definition
            raw_tokens = stripped.split()
            if (raw_tokens[0] == "route-policy" and len(raw_tokens) == 2):
                in_policy = True
        else:
            # Indented line belongs to current section
            if current_section is not None:
                counts[current_section] = counts.get(current_section, 0) + 1

    return counts


def _count_leaves(node: ConfigNode) -> int:
    """Count total data-bearing nodes (leaf + internal) in a subtree.

    Skips '!' nodes — the parser creates ConfigNodes for indented bangs
    but they carry no data.
    """
    if node.keyword == "!":
        return 0
    if not node.children:
        return 1
    # Count this node + all descendants
    return 1 + sum(_count_leaves(child) for child in node.children)


def count_tree_section_nodes(tree: IosxrConfigTree) -> dict[str, int]:
    """Count data-bearing nodes per top-level section in the parsed ConfigTree.

    For each top-level child node, count the node itself plus all descendants.
    Returns: {"router.bgp.1": 45, "interface.Loopback0": 12, "ntp": 3, ...}
    """
    counts: dict[str, int] = {}

    for node in tree.children:
        # Compute section key the same way as raw counting
        tokens = [node.keyword] + node.args
        if node.negated:
            # Raw line had 'no' prefix, but parser strips it
            pass
        key = _section_key_from_tokens(tokens)
        counts[key] = counts.get(key, 0) + _count_leaves(node)

    return counts


def validate_parser_structure(
    cfg_text: str,
    tree: IosxrConfigTree,
    entity_id: str,
    mode: str = "error",
) -> list[tuple[str, int, int]]:
    """Compare raw text section counts against parsed tree section counts.

    Returns list of (section, raw_count, parsed_count) for mismatches.
    Raises ParserStructureError if mode=="error" and mismatches found.
    """
    raw_counts = count_section_lines(cfg_text)
    tree_counts = count_tree_section_nodes(tree)

    all_sections = sorted(set(raw_counts) | set(tree_counts))
    discrepancies: list[tuple[str, int, int]] = []

    for section in all_sections:
        raw = raw_counts.get(section, 0)
        parsed = tree_counts.get(section, 0)
        if raw != parsed:
            discrepancies.append((section, raw, parsed))

    if discrepancies:
        lines = [f"Parser structure mismatch for {entity_id}:"]
        for section, raw, parsed in discrepancies:
            lines.append(f"  {section}: raw={raw}, parsed={parsed}")

        msg = "\n".join(lines)
        if mode == "error":
            raise ParserStructureError(msg, discrepancies)
        elif mode == "warn":
            logger.warning(msg)

    return discrepancies
