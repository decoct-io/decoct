"""Bridge logic for the two-agent progressive disclosure QA harness.

Provides formatting, parsing, and file-loading utilities that sit between
the Router Agent and the Answerer Agent.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from decoct.agent_qa.prompts import ANSWERER_PROMPT_TEMPLATE, ROUTER_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)

_DATA_MANUAL_EXCERPT = """\
## Reconstruction Rule

To reconstruct a single entity's full configuration from compressed output:

1. Start with the **base_class** from Tier B — this is the entity's foundation.
2. Add the class **own_attrs** — look up the entity's class from Tier C `class_assignments`.
3. Add **subclass own_attrs** (if any) — same lookup via `subclass_assignments`.
4. Apply **overrides** (if any) — patch specific attributes; `__ABSENT__` means the \
attribute is deleted (not present in the original).
5. Add **instance_attrs** (if sparse/complex) — per-entity complex data structures.
6. Add **instance_data** (phone book) — dense per-entity scalar values.

Later layers override earlier ones. The result is the complete entity configuration.

## Phone Book (instance_data)

The phone book stores dense scalar values efficiently:
- `schema`: ordered list of attribute paths (column headers).
- `records`: mapping of entity_id → positional list of values matching schema order.

Example: if schema is `[hostname, domain]` and records has `srv-01: [srv-01, example.com]`, \
then srv-01 has `hostname: srv-01` and `domain: example.com`.

## Projections

Projections are subject-specific slices (e.g. "authentication", "networking") that \
extract only the relevant attributes from Tier B+C. They contain the same structure \
(classes, overrides, instance_data) but scoped to a single topic. Prefer projections \
when the question targets a specific subject.

## Special Values

- `__ABSENT__`: the attribute does not exist in the original entity (explicitly removed).
- Composite templates: reusable structural patterns with per-entity deltas.
"""

_CATEGORY_HINTS: dict[str, str] = {
    "FR": "This is a factual retrieval question — look up the specific value.",
    "CR": "This is a cross-reference question — compare values across entities/types.",
    "OI": "This is an operational inference question — reason about what these settings mean in practice.",
    "DC": "This is a design compliance question — assess whether the configuration meets the stated standard.",
    "NA": "This is a negative/absence question — determine whether something is missing or not configured.",
}


def get_data_manual_excerpt() -> str:
    """Return a condensed reconstruction-instructions excerpt for the Answerer Agent."""
    return _DATA_MANUAL_EXCERPT


def format_router_prompt(tier_a_content: str, question: str) -> str:
    """Fill the router prompt template with Tier A content and the user question."""
    return ROUTER_PROMPT_TEMPLATE.format(tier_a_content=tier_a_content, question=question)


def parse_router_response(response_text: str) -> dict[str, object]:
    """Extract the JSON routing decision from a Router Agent response.

    Handles three formats:
    - Raw JSON string
    - JSON inside a markdown ```json``` code block
    - JSON object embedded in surrounding prose

    Returns a dict with ``"files"`` (list[str]) and ``"reasoning"`` (str).
    On parse failure returns ``{"files": [], "reasoning": ""}``.
    """
    fallback: dict[str, object] = {"files": [], "reasoning": ""}
    text = response_text.strip()

    # 1. Try raw JSON
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "files" in parsed:
            return parsed
    except json.JSONDecodeError:
        pass

    # 2. Try markdown code block
    md_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if md_match:
        try:
            parsed = json.loads(md_match.group(1).strip())
            if isinstance(parsed, dict) and "files" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

    # 3. Try to find an embedded JSON object with "files" key
    obj_match = re.search(r'\{[^{}]*"files"\s*:\s*\[.*?\][^{}]*\}', text, re.DOTALL)
    if obj_match:
        try:
            parsed = json.loads(obj_match.group(0))
            if isinstance(parsed, dict) and "files" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

    return fallback


def validate_routed_files(output_dir: Path, files: list[str]) -> tuple[list[str], list[str]]:
    """Check which routed files actually exist on disk.

    Returns a tuple of (valid_files, missing_files). Missing files are logged
    as warnings but not sent to the answerer.
    """
    valid: list[str] = []
    missing: list[str] = []
    for name in files:
        path = output_dir / name
        if path.is_file():
            valid.append(name)
        else:
            missing.append(name)
            logger.warning("Router selected non-existent file: %s", name)
    return valid, missing


def load_files(output_dir: Path, filenames: list[str]) -> str:
    """Read files from *output_dir* and return their contents with separators.

    Missing files are skipped with a note. Each file's content is preceded by
    a ``--- filename ---`` header line.
    """
    parts: list[str] = []
    for name in filenames:
        path = output_dir / name
        if not path.is_file():
            parts.append(f"--- {name} ---\n[file not found]\n")
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            parts.append(f"--- {name} ---\n[read error]\n")
            continue
        parts.append(f"--- {name} ---\n{content}\n")
    return "\n".join(parts)


def _extract_tier_a_types_section(tier_a_content: str) -> str:
    """Extract just the ``types`` section from Tier A YAML for fleet context.

    Returns the types block (with counts and summaries) without assertions
    or topology, to keep the excerpt compact.
    """
    lines = tier_a_content.splitlines(keepends=True)
    result: list[str] = []
    in_types = False
    for line in lines:
        stripped = line.rstrip()
        # Detect top-level keys (no indentation)
        if stripped and not stripped[0].isspace() and stripped.endswith(":"):
            if stripped == "types:":
                in_types = True
                result.append(line)
                continue
            elif in_types:
                # Hit another top-level key — stop
                break
        if in_types:
            result.append(line)
    return "".join(result) if result else ""


def format_answerer_prompt(
    question: str,
    loaded_contents: str,
    category: str = "",
    tier_a_excerpt: str = "",
) -> str:
    """Fill the answerer prompt template with loaded file contents and the question.

    Parameters
    ----------
    question:
        The user question to answer.
    loaded_contents:
        Concatenated file contents loaded by the router.
    category:
        Optional question category code (FR, CR, OI, DC, NA) for hint injection.
    tier_a_excerpt:
        Optional condensed Tier A excerpt for fleet context.
    """
    hint = _CATEGORY_HINTS.get(category.upper(), "") if category else ""
    hint_block = f"**Hint:** {hint}" if hint else ""

    # Prepend Tier A excerpt to loaded contents if provided
    if tier_a_excerpt:
        loaded_contents = (
            f"--- tier_a.yaml (fleet context) ---\n{tier_a_excerpt}\n\n{loaded_contents}"
        )

    return ANSWERER_PROMPT_TEMPLATE.format(
        data_manual_excerpt=get_data_manual_excerpt(),
        loaded_file_contents=loaded_contents,
        category_hint=hint_block,
        question=question,
    )
