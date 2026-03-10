"""Corpus-learned compression classes — LZ77-style dictionary discovery.

Discovers repeated (path, value) patterns across a corpus of config files
and produces Schema objects whose defaults can be stripped by the existing
StripDefaultsPass + EmitClassesPass pipeline.

The algorithm is fully general — no platform-specific rules.  It discovers
structure from the data the same way LZ77 discovers repeated byte sequences.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any

from decoct.schemas.models import Schema
from decoct.tokens import count_tokens

# ── Data structures ──────────────────────────────────────────────────────


@dataclass
class LearnedClass:
    """A class discovered from corpus co-occurrence patterns."""

    name: str
    defaults: dict[str, Any]  # normalised_path → value
    matching_file_count: int
    total_file_count: int
    net_score: int  # positive = worth emitting


# ── 1. Flatten ───────────────────────────────────────────────────────────


def flatten_doc(node: Any, path: str = "") -> list[tuple[str, Any]]:
    """Walk a document depth-first, collecting all leaf (path, value) pairs.

    List indices are replaced with ``*`` so that structurally equivalent
    entries in different list positions merge.
    """
    pairs: list[tuple[str, Any]] = []

    if isinstance(node, dict):
        for key in node:
            child_path = f"{path}.{key}" if path else str(key)
            child = node[key]
            if isinstance(child, (dict, list)):
                pairs.extend(flatten_doc(child, child_path))
            else:
                pairs.append((child_path, child))

    elif isinstance(node, list):
        for child in node:
            child_path = f"{path}.*" if path else "*"
            if isinstance(child, (dict, list)):
                pairs.extend(flatten_doc(child, child_path))
            else:
                pairs.append((child_path, child))

    return pairs


# ── 2. Instance-level discovery ──────────────────────────────────────────


def _split_path(path: str) -> list[str]:
    """Split a dotted path into segments."""
    return path.split(".")


def discover_instance_levels(all_paths: list[str], *, threshold_ratio: float = 0.5) -> set[int]:
    """Detect which path depths are instance keys (user-chosen names).

    At each depth, count the number of unique keys.  If a depth has many
    unique keys relative to the number of paths reaching that depth, it's
    an instance level and should be wildcarded.

    Returns a set of depth indices (0-based) to wildcard.
    """
    # Collect keys at each depth, grouped by their parent prefix
    depth_keys: dict[int, dict[str, set[str]]] = {}

    for path in all_paths:
        segments = _split_path(path)
        for i, seg in enumerate(segments):
            if seg == "*":
                continue
            parent = ".".join(segments[:i]) if i > 0 else "<root>"
            depth_keys.setdefault(i, {}).setdefault(parent, set()).add(seg)

    instance_levels: set[int] = set()

    for depth, parents in depth_keys.items():
        for parent, keys in parents.items():
            n_unique = len(keys)
            # Heuristic: if a parent prefix has many children, those children
            # are likely instance names.  Scale threshold with log of total
            # paths to avoid false positives on small corpora.
            min_unique = max(5, int(math.log2(max(len(all_paths), 2)) * threshold_ratio * 3))
            if n_unique >= min_unique:
                instance_levels.add(depth)

    return instance_levels


def normalise_paths(
    pairs: list[tuple[str, Any]],
    instance_levels: set[int],
) -> list[tuple[str, Any]]:
    """Replace instance-level path segments with ``*``.

    Segments already wildcarded (from list-index replacement) are left alone.
    """
    result: list[tuple[str, Any]] = []
    for path, value in pairs:
        segments = _split_path(path)
        new_segments: list[str] = []
        for i, seg in enumerate(segments):
            if i in instance_levels and seg != "*":
                new_segments.append("*")
            else:
                new_segments.append(seg)
        result.append((".".join(new_segments), value))
    return result


# ── 3. Mine frequent pairs ──────────────────────────────────────────────


def _mine_frequent_pairs(
    doc_pairs: list[list[tuple[str, Any]]],
    *,
    min_frequency: float = 0.3,
) -> dict[tuple[str, str], int]:
    """Count frequency of each (path, str(value)) pair across documents.

    Returns pairs appearing in >= min_frequency fraction of docs, mapped
    to their doc count.
    """
    n_docs = len(doc_pairs)
    if n_docs == 0:
        return {}

    min_count = max(2, int(n_docs * min_frequency))

    # Count how many docs contain each (path, value) pair
    pair_doc_count: Counter[tuple[str, str]] = Counter()
    for pairs in doc_pairs:
        # Deduplicate within a single doc
        unique_pairs = {(p, str(v)) for p, v in pairs}
        pair_doc_count.update(unique_pairs)

    return {pair: count for pair, count in pair_doc_count.items() if count >= min_count}


# ── 4. Co-occurrence class discovery ─────────────────────────────────────


def _doc_pair_sets(
    doc_pairs: list[list[tuple[str, Any]]],
) -> list[set[tuple[str, str]]]:
    """Convert each doc's pairs to a set of (path, str_value) for fast lookup."""
    return [{(p, str(v)) for p, v in pairs} for pairs in doc_pairs]


def _find_co_occurring_class(
    seed: tuple[str, str],
    frequent_pairs: dict[tuple[str, str], int],
    doc_sets: list[set[tuple[str, str]]],
    *,
    min_frequency: float = 0.3,
) -> set[tuple[str, str]]:
    """Find all frequent pairs that co-occur with *seed* in enough docs.

    Returns the set of pairs (including seed) that form a candidate class.
    """
    # Docs containing the seed
    seed_docs = [i for i, s in enumerate(doc_sets) if seed in s]
    if not seed_docs:
        return set()

    n_seed = len(seed_docs)
    min_co = max(2, int(n_seed * min_frequency))

    # Count co-occurrence of every frequent pair within seed docs
    co_count: Counter[tuple[str, str]] = Counter()
    for i in seed_docs:
        for pair in doc_sets[i]:
            if pair in frequent_pairs:
                co_count[pair] += 1

    return {pair for pair, count in co_count.items() if count >= min_co}


# ── 5. Scoring ───────────────────────────────────────────────────────────


def _score_class(
    members: set[tuple[str, str]],
    doc_sets: list[set[tuple[str, str]]],
    *,
    encoding: str = "cl100k_base",
) -> tuple[int, int]:
    """Score a candidate class.

    Returns (net_score, matching_file_count).
    net_score = tokens_saved_per_file × matching_files - class_def_tokens
    """
    # Count how many docs contain ALL members of the class
    matching = sum(1 for s in doc_sets if members <= s)
    if matching == 0:
        return 0, 0

    # Tokens saved per file: sum of tokens for each "leaf: value\n" line
    saved_per_file = sum(
        count_tokens(f"{path.rsplit('.', 1)[-1]}: {value}\n", encoding)
        for path, value in members
    )

    # Class definition cost: "@class name: key=val, key=val, ..."
    pairs_str = ", ".join(f"{p.rsplit('.', 1)[-1]}={v}" for p, v in sorted(members))
    class_def = f"@class corpus-learned: {pairs_str}\n"
    class_def_tokens = count_tokens(class_def, encoding)

    net = saved_per_file * matching - class_def_tokens
    return net, matching


# ── 6. Greedy selection ──────────────────────────────────────────────────


def _greedy_select(
    candidates: list[set[tuple[str, str]]],
    doc_sets: list[set[tuple[str, str]]],
    *,
    encoding: str = "cl100k_base",
) -> list[tuple[set[tuple[str, str]], int, int]]:
    """Greedily select non-overlapping classes with positive net score.

    Returns list of (member_set, net_score, matching_count).
    """
    selected: list[tuple[set[tuple[str, str]], int, int]] = []
    used_pairs: set[tuple[str, str]] = set()

    # De-duplicate candidates by frozenset
    unique: dict[frozenset[tuple[str, str]], set[tuple[str, str]]] = {}
    for c in candidates:
        key = frozenset(c)
        if key not in unique:
            unique[key] = c

    remaining = list(unique.values())

    while remaining:
        best_score = 0
        best_idx = -1
        best_matching = 0

        for i, cand in enumerate(remaining):
            trimmed = cand - used_pairs
            if len(trimmed) < 2:
                continue
            score, matching = _score_class(trimmed, doc_sets, encoding=encoding)
            if score > best_score:
                best_score = score
                best_idx = i
                best_matching = matching

        if best_idx < 0:
            break

        winner = remaining[best_idx] - used_pairs
        selected.append((winner, best_score, best_matching))
        used_pairs |= winner
        remaining.pop(best_idx)

    return selected


# ── 7. Public API ────────────────────────────────────────────────────────


def learn_classes(
    docs: list[Any],
    *,
    min_frequency: float = 0.3,
    encoding: str = "cl100k_base",
) -> list[LearnedClass]:
    """Discover compression classes from a corpus of parsed documents.

    Full pipeline: flatten → discover instance levels → normalise →
    mine frequent pairs → co-occurrence classes → score → greedy select.

    Args:
        docs: List of parsed documents (CommentedMap / dict / list).
        min_frequency: Minimum fraction of docs a pair must appear in.
        encoding: Tiktoken encoding for token counting.

    Returns:
        List of LearnedClass objects with positive net_score, sorted by
        descending score.
    """
    if len(docs) < 3:
        return []

    # 1. Flatten all docs
    raw_pairs_per_doc = [flatten_doc(doc) for doc in docs]

    # 2. Discover instance levels from all paths
    all_paths = [path for pairs in raw_pairs_per_doc for path, _ in pairs]
    instance_levels = discover_instance_levels(all_paths)

    # 3. Normalise paths
    normalised_per_doc = [normalise_paths(pairs, instance_levels) for pairs in raw_pairs_per_doc]

    # 4. Mine frequent pairs
    frequent = _mine_frequent_pairs(normalised_per_doc, min_frequency=min_frequency)
    if not frequent:
        return []

    # 5. Build doc sets for fast lookup
    doc_sets = _doc_pair_sets(normalised_per_doc)

    # 6. Find co-occurring classes seeded by each frequent pair
    candidates: list[set[tuple[str, str]]] = []
    for seed in frequent:
        cand = _find_co_occurring_class(seed, frequent, doc_sets, min_frequency=min_frequency)
        if len(cand) >= 2:
            candidates.append(cand)

    if not candidates:
        return []

    # 7. Greedy select
    selected = _greedy_select(candidates, doc_sets, encoding=encoding)

    # 8. Build LearnedClass objects
    n_docs = len(docs)
    result: list[LearnedClass] = []
    for i, (members, net_score, matching) in enumerate(selected):
        defaults = {path: _coerce_value(value) for path, value in members}
        result.append(
            LearnedClass(
                name=f"corpus-class-{i}",
                defaults=defaults,
                matching_file_count=matching,
                total_file_count=n_docs,
                net_score=net_score,
            )
        )

    return sorted(result, key=lambda c: c.net_score, reverse=True)


def _coerce_value(value_str: str) -> Any:
    """Coerce a stringified value back to a native type for schema defaults."""
    if value_str.lower() == "true":
        return True
    if value_str.lower() == "false":
        return False
    if value_str.lower() == "none":
        return None
    try:
        return int(value_str)
    except ValueError:
        pass
    try:
        return float(value_str)
    except ValueError:
        pass
    return value_str


def classes_to_schema(classes: list[LearnedClass], platform: str) -> Schema:
    """Convert learned classes into a Schema for the existing pipeline.

    Merges all class defaults into a single Schema that StripDefaultsPass
    and EmitClassesPass can consume directly.
    """
    merged: dict[str, Any] = {}
    for cls in classes:
        merged.update(cls.defaults)

    return Schema(
        platform=f"{platform}-corpus",
        source="corpus-learned",
        confidence="medium",
        defaults=merged,
    )
