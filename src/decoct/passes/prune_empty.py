"""Prune-empty pass — remove empty dicts and lists left after other passes."""

from __future__ import annotations

from typing import Any

from decoct.passes.base import BasePass, PassResult, register_pass


def prune_empty(node: Any) -> int:
    """Recursively remove empty dict/list values from a YAML tree.

    Returns count of pruned nodes.
    """
    count = 0
    if isinstance(node, dict):
        # Recurse first, then prune
        for key in list(node.keys()):
            child = node[key]
            if isinstance(child, (dict, list)):
                count += prune_empty(child)
                # After recursion, prune if now empty
                if isinstance(child, (dict, list)) and len(child) == 0:
                    del node[key]
                    count += 1
    elif isinstance(node, list):
        for i in range(len(node) - 1, -1, -1):
            child = node[i]
            if isinstance(child, (dict, list)):
                count += prune_empty(child)
                if isinstance(child, (dict, list)) and len(child) == 0:
                    del node[i]
                    count += 1
    return count


@register_pass
class PruneEmptyPass(BasePass):
    """Remove empty dicts and lists left by other passes."""

    name = "prune-empty"
    run_after = ["strip-defaults", "strip-conformant", "drop-fields", "keep-fields"]
    run_before: list[str] = []

    def run(self, doc: Any, **kwargs: Any) -> PassResult:
        count = prune_empty(doc)
        return PassResult(name=self.name, items_removed=count)
