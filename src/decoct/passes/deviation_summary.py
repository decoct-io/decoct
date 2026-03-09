"""Deviation-summary pass — add summary comment block at document start."""

from __future__ import annotations

from typing import Any

from ruamel.yaml.comments import CommentedMap

from decoct.assertions.matcher import evaluate_match, find_matches
from decoct.assertions.models import Assertion
from decoct.passes.base import BasePass, PassResult, register_pass


def deviation_summary(doc: Any, assertions: list[Assertion]) -> list[str]:
    """Collect all deviations and add a summary comment block at document start.

    Returns list of summary lines.
    """
    deviations: list[tuple[str, str]] = []

    for assertion in assertions:
        if assertion.match is None:
            continue

        matches = find_matches(doc, "", assertion)
        for path, value, _parent, _key in matches:
            if not evaluate_match(assertion.match, value):
                deviations.append((assertion.id, path))

    if not deviations or not isinstance(doc, CommentedMap):
        return []

    lines = [f"decoct: {len(deviations)} deviations from standards"]
    for assertion_id, path in deviations:
        lines.append(f"[!] {assertion_id}: {path}")

    doc.yaml_set_start_comment("\n".join(lines))

    return lines


@register_pass
class DeviationSummaryPass(BasePass):
    """Add deviation summary comment block at document start."""

    name = "deviation-summary"
    run_after = ["annotate-deviations"]
    run_before: list[str] = []

    def __init__(self, assertions: list[Assertion] | None = None) -> None:
        self.assertions = assertions or []

    def run(self, doc: Any, **kwargs: Any) -> PassResult:
        assertions = self.assertions or kwargs.get("assertions", [])
        lines = deviation_summary(doc, assertions)
        return PassResult(
            name=self.name,
            items_removed=0,
            details=lines,
        )
