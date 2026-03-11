"""LLM-assisted Tier A spec inference — generate corpus description and type summaries.

Workflow: load Tier A + all Tier B files → send to LLM → parse response → return TierASpec.

LLM provider: OpenAI SDK with configurable ``--base-url`` (defaults to
OpenRouter). Works with any OpenAI-compatible endpoint.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from io import StringIO
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from decoct.assembly.tier_a_models import (
    TierASpec,
    TierATypeDescription,
)
from decoct.llm_utils import extract_yaml_block

_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_API_KEY_ENV = "OPENROUTER_API_KEY"

_SYSTEM_PROMPT = """\
You are a Tier A spec generator for decoct, an infrastructure compression tool. \
You will be given a Tier A summary and Tier B class definitions for all entity \
types in a compressed infrastructure corpus. Your job is to generate a human- and \
LLM-readable orientation guide.

## Task
1. Write a concise ``corpus_description`` (1-3 sentences) explaining what this \
infrastructure corpus contains.
2. Write 3-5 ``how_to_use`` bullet points explaining how an LLM should navigate \
the tiered data (Tier A for orientation, Tier B for class definitions, Tier C for \
per-entity differences).
3. For each entity type, write a ``summary`` (1-2 sentences) and 2-4 \
``key_differentiators`` that distinguish it from other types.

## Output format
```yaml
version: 1
generated_by: decoct-infer
corpus_description: "<corpus description>"
how_to_use:
- "<instruction 1>"
- "<instruction 2>"
type_descriptions:
  <type_id>:
    summary: "<type summary>"
    key_differentiators:
    - "<differentiator 1>"
    - "<differentiator 2>"
```

## Rules
- Keep descriptions factual and grounded in the data provided
- ``corpus_description`` should mention the number and types of entities
- ``how_to_use`` should reference the tier structure (A/B/C) and file references
- ``key_differentiators`` should highlight what makes each type unique in the fleet
- Use the actual type IDs from the Tier A data
"""

_USER_PROMPT = """\
Below is the Tier A summary and Tier B class definitions for a compressed \
infrastructure corpus. Generate the orientation guide.

## Tier A
```yaml
{tier_a_content}
```

## Tier B files
{tier_b_sections}
"""


def _call_llm(
    tier_a_content: str,
    tier_b_sections: str,
    model: str,
    base_url: str,
    api_key_env: str,
) -> dict[str, Any]:
    """Lazy import openai. Build prompt. Call API. Extract YAML block."""
    try:
        from openai import OpenAI
    except ImportError:
        msg = (
            "The openai SDK is required for Tier A spec inference. "
            "Install it with: pip install decoct[llm]"
        )
        raise ImportError(msg)  # noqa: B904

    # Load .env if python-dotenv is available
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.environ.get(api_key_env)
    if not api_key:
        msg = f"Environment variable {api_key_env} is not set"
        raise ValueError(msg)

    user_prompt = _USER_PROMPT.format(
        tier_a_content=tier_a_content,
        tier_b_sections=tier_b_sections,
    )

    client = OpenAI(base_url=base_url, api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=4096,
    )
    response_text = response.choices[0].message.content or ""
    yaml_str = extract_yaml_block(response_text)
    return _validate_llm_response(yaml_str)


def _sanitize_yaml(yaml_str: str) -> str:
    """Clean LLM-generated YAML that may have unquoted colons or special chars."""
    import re

    yaml_str = yaml_str.replace("\t", "  ")
    # Replace smart/curly quotes with plain quotes
    yaml_str = yaml_str.replace("\u201c", '"').replace("\u201d", '"')
    yaml_str = yaml_str.replace("\u2018", "'").replace("\u2019", "'")

    # Quote values that contain unquoted colons (`: `) which YAML interprets as mappings.
    # This handles both list items (`- value`) and mapping values (`key: value`).
    lines = yaml_str.splitlines()
    result: list[str] = []
    for line in lines:
        # List items: `  - some value with colon: inside`
        m = re.match(r"^(\s*- )(.+)$", line)
        if m:
            prefix, value = m.group(1), m.group(2)
            if not value.startswith('"') and not value.startswith("'"):
                if ": " in value:
                    value = '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
            result.append(prefix + value)
            continue

        # Mapping values: `key: value` or `  key: value`
        m2 = re.match(r"^(\s*[\w][\w_-]*:\s+)(.+)$", line)
        if m2:
            prefix, value = m2.group(1), m2.group(2)
            if not value.startswith(('"', "'", "|", ">")):
                # If the value itself contains `: ` it needs quoting
                if ": " in value:
                    value = '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
            result.append(prefix + value)
            continue

        result.append(line)

    return "\n".join(result)


def _validate_llm_response(yaml_str: str) -> dict[str, Any]:
    """Parse YAML. Require corpus_description and type_descriptions."""
    yaml_str = _sanitize_yaml(yaml_str)
    yaml = YAML(typ="safe")
    doc = yaml.load(yaml_str)
    if not isinstance(doc, dict):
        msg = "LLM response is not a YAML mapping"
        raise ValueError(msg)

    if "corpus_description" not in doc or not isinstance(doc["corpus_description"], str):
        msg = "LLM response missing required 'corpus_description' string"
        raise ValueError(msg)

    type_descs = doc.get("type_descriptions", {})
    if not isinstance(type_descs, dict):
        msg = "LLM response 'type_descriptions' must be a mapping"
        raise ValueError(msg)

    for type_id, desc in type_descs.items():
        if not isinstance(desc, dict):
            msg = f"type_descriptions['{type_id}'] must be a mapping"
            raise ValueError(msg)
        if "summary" not in desc or not isinstance(desc["summary"], str):
            msg = f"type_descriptions['{type_id}'] must have a 'summary' string"
            raise ValueError(msg)

    return dict(doc)


def _build_spec(llm_result: dict[str, Any]) -> TierASpec:
    """Convert validated LLM result to TierASpec."""
    type_descriptions: dict[str, TierATypeDescription] = {}
    for type_id, desc_raw in llm_result.get("type_descriptions", {}).items():
        type_descriptions[type_id] = TierATypeDescription(
            summary=desc_raw["summary"],
            key_differentiators=list(desc_raw.get("key_differentiators", []) or []),
        )

    return TierASpec(
        version=1,
        generated_by="decoct-infer",
        corpus_description=llm_result["corpus_description"],
        how_to_use=list(llm_result.get("how_to_use", []) or []),
        type_descriptions=type_descriptions,
    )


def infer_tier_a_spec(
    output_dir: Path,
    model: str = "google/gemini-2.5-flash",
    base_url: str = _DEFAULT_BASE_URL,
    api_key_env: str = _DEFAULT_API_KEY_ENV,
    on_progress: Callable[[str], None] | None = None,
) -> TierASpec:
    """Orchestrator: load Tier A + Tier B files → LLM call → TierASpec.

    ``on_progress`` callback for status messages.
    """
    def _progress(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    # Load Tier A
    tier_a_file = output_dir / "tier_a.yaml"
    if not tier_a_file.exists():
        msg = f"Tier A file not found: {tier_a_file}"
        raise FileNotFoundError(msg)

    _progress(f"Loading Tier A from {tier_a_file}...")
    yaml = YAML(typ="safe")
    tier_a = yaml.load(tier_a_file.read_text())

    # Serialize Tier A for the prompt
    rt_yaml = YAML(typ="rt")
    rt_yaml.default_flow_style = False
    stream = StringIO()
    rt_yaml.dump(tier_a, stream)
    tier_a_content = stream.getvalue()

    # Load all Tier B files referenced in Tier A
    tier_b_sections_parts: list[str] = []
    types_section = tier_a.get("types", {})
    for type_id, type_info in sorted(types_section.items()):
        tier_b_ref = type_info.get("tier_b_ref", f"{type_id}_classes.yaml")
        tier_b_file = output_dir / tier_b_ref
        if tier_b_file.exists():
            _progress(f"Loading Tier B: {tier_b_ref}...")
            tier_b_content = tier_b_file.read_text()
            tier_b_sections_parts.append(f"### {type_id}\n```yaml\n{tier_b_content}\n```")

    tier_b_sections = "\n\n".join(tier_b_sections_parts)

    type_count = len(types_section)
    _progress(f"Found {type_count} types. Calling LLM ({model})...")

    llm_result = _call_llm(tier_a_content, tier_b_sections, model, base_url, api_key_env)
    spec = _build_spec(llm_result)

    _progress(
        f"Generated spec: {len(spec.type_descriptions)} type descriptions, "
        f"{len(spec.how_to_use)} usage instructions"
    )
    return spec
