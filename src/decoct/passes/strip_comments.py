"""Strip-comments pass — removes all YAML comments."""

from __future__ import annotations

from typing import Any

from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.tokens import CommentToken

from decoct.passes.base import BasePass, PassResult, register_pass


def _strip_comments(node: Any) -> int:
    """Recursively remove all comments from a ruamel.yaml node. Returns count removed."""
    count = 0

    if isinstance(node, CommentedMap):
        if hasattr(node, "comment") and node.comment:
            count += _count_comments(node.comment)
            node.comment = None
        if hasattr(node, "ca") and node.ca:
            count += _count_comment_attribs(node.ca)
            node.ca.comment = None
            node.ca.items.clear()
            if hasattr(node.ca, "end"):
                node.ca.end = None
        for value in node.values():
            count += _strip_comments(value)

    elif isinstance(node, CommentedSeq):
        if hasattr(node, "comment") and node.comment:
            count += _count_comments(node.comment)
            node.comment = None
        if hasattr(node, "ca") and node.ca:
            count += _count_comment_attribs(node.ca)
            node.ca.comment = None
            node.ca.items.clear()
            if hasattr(node.ca, "end"):
                node.ca.end = None
        for item in node:
            count += _strip_comments(item)

    return count


def _count_comments(comment: Any) -> int:
    """Count comment tokens in a comment attribute."""
    if comment is None:
        return 0
    if isinstance(comment, list):
        return sum(1 for c in comment if isinstance(c, CommentToken))
    return 0


def _count_comment_attribs(ca: Any) -> int:
    """Count comments in a CommentAttrib object."""
    count = 0
    if ca.comment:
        count += _count_comments(ca.comment)
    for item_comments in ca.items.values():
        if isinstance(item_comments, list):
            count += sum(1 for c in item_comments if isinstance(c, CommentToken))
    return count


@register_pass
class StripCommentsPass(BasePass):
    """Remove all comments from a YAML document."""

    name = "strip-comments"
    run_after: list[str] = []
    run_before: list[str] = []

    def run(self, doc: Any, **kwargs: Any) -> PassResult:
        count = _strip_comments(doc)
        return PassResult(name=self.name, items_removed=count)
