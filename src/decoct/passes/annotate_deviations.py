"""Annotate-deviations pass — add comments where values deviate from assertions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ruamel.yaml.comments import CommentedMap

from decoct.assertions.matcher import _SENTINEL, evaluate_match, find_matches
from decoct.assertions.models import Assertion
from decoct.passes.base import BasePass, PassResult, register_pass


@dataclass
class Deviation:
    """A detected deviation from an assertion."""

    assertion_id: str
    path: str
    message: str


def annotate_deviations(doc: Any, assertions: list[Assertion]) -> list[Deviation]:
    """Annotate deviating values with inline comments.

    Returns list of deviations found.
    """
    deviations: list[Deviation] = []

    for assertion in assertions:
        if assertion.match is None:
            continue

        matches = find_matches(doc, "", assertion)
        for path, value, parent, key in matches:
            if not evaluate_match(assertion.match, value):
                if value is _SENTINEL:
                    comment = f" [!] missing: {assertion.assert_}"
                elif assertion.match.value is not None:
                    comment = f" [!] standard: {assertion.match.value}"
                else:
                    comment = f" [!] assertion: {assertion.assert_}"

                # For absent keys, we can't annotate the key itself — skip YAML comment
                if value is not _SENTINEL and isinstance(parent, CommentedMap):
                    parent.yaml_add_eol_comment(comment, key)

                deviations.append(Deviation(
                    assertion_id=assertion.id,
                    path=path,
                    message=comment.strip(),
                ))

    return deviations


@register_pass
class AnnotateDeviationsPass(BasePass):
    """Annotate values that deviate from assertions with comments."""

    name = "annotate-deviations"
    run_after = ["strip-conformant"]
    run_before: list[str] = []

    def __init__(self, assertions: list[Assertion] | None = None) -> None:
        self.assertions = assertions or []

    def run(self, doc: Any, **kwargs: Any) -> PassResult:
        assertions = self.assertions or kwargs.get("assertions", [])
        deviations = annotate_deviations(doc, assertions)
        return PassResult(
            name=self.name,
            items_removed=0,
            details=[f"{d.assertion_id}: {d.path}" for d in deviations],
        )
