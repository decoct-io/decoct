"""Shannon entropy computation on value frequency counters."""

from __future__ import annotations

import math
from collections import Counter


def shannon_entropy(freq: Counter[str]) -> float:
    """Compute Shannon entropy from a frequency counter.

    Returns entropy in bits. Returns 0.0 for empty or single-value counters.
    """
    total = sum(freq.values())
    if total <= 0:
        return 0.0

    entropy = 0.0
    for count in freq.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)
    return entropy


def normalized_entropy(freq: Counter[str]) -> float:
    """Compute normalized Shannon entropy (0.0 to 1.0).

    Normalized by log2(cardinality). Returns 0.0 for cardinality <= 1.
    """
    cardinality = len(freq)
    if cardinality <= 1:
        return 0.0

    h = shannon_entropy(freq)
    max_h = math.log2(cardinality)
    if max_h == 0:
        return 0.0
    return h / max_h
