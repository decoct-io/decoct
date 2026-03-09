"""Strip-conformant pass — remove values conforming to must assertions."""

from __future__ import annotations

from typing import Any

from decoct.assertions.matcher import evaluate_match, find_matches
from decoct.assertions.models import Assertion
from decoct.passes.base import BasePass, PassResult, register_pass


def strip_conformant(doc: Any, assertions: list[Assertion]) -> int:
    """Strip conformant values for 'must' assertions with match conditions.

    Returns count of fields removed.
    """
    count = 0
    for assertion in assertions:
        if assertion.match is None or assertion.severity != "must":
            continue

        matches = find_matches(doc, "", assertion)
        for _path, value, parent, key in matches:
            if evaluate_match(assertion.match, value):
                del parent[key]
                count += 1

    return count


@register_pass
class StripConformantPass(BasePass):
    """Remove values that conform to must-severity assertions."""

    name = "strip-conformant"
    run_after = ["strip-defaults"]
    run_before: list[str] = []

    def __init__(self, assertions: list[Assertion] | None = None) -> None:
        self.assertions = assertions or []

    def run(self, doc: Any, **kwargs: Any) -> PassResult:
        assertions = self.assertions or kwargs.get("assertions", [])
        count = strip_conformant(doc, assertions)
        return PassResult(name=self.name, items_removed=count)
