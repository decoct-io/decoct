"""LLM-assisted projection spec inference — identify subjects from Tier B.

Workflow: load Tier B classes → extract attribute path prefixes → send to LLM
→ parse response → return ProjectionSpec.

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

from decoct.llm_utils import extract_yaml_block
from decoct.projections.models import (
    ProjectionSpec,
    RelatedPath,
    SubjectSpec,
)

_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_API_KEY_ENV = "OPENROUTER_API_KEY"

_SYSTEM_PROMPT = """\
You are a projection spec generator for decoct, an infrastructure \
compression tool. You will be given Tier B class definitions for an \
entity type. Your job is to identify logical subjects — groups of \
related attributes that an engineer would want to view together.

## Task
1. Identify 3-8 logical subjects from the attribute paths.
2. For each subject, write glob patterns that select the relevant paths.
3. Include ``hostname`` as a related_path for all subjects.
4. Write 2-3 example questions per subject.

## Output format
```yaml
version: 1
source_type: <entity_type from meta>
generated_by: decoct-infer
subjects:
- name: <kebab-case subject name>
  description: <one-line description>
  include_paths:
  - <glob pattern using ** for multi-level matching>
  related_paths:
  - path: hostname
    reason: "Device identity"
  example_questions:
  - "<question this projection answers>"
```

## Rules
- Use ``**`` glob patterns for include_paths (e.g. ``router.bgp.**``)
- Subject names should be descriptive kebab-case (e.g. ``bgp``, ``interfaces``, \
``isis-routing``)
- Each attribute path should belong to at least one subject
- Prefer broader patterns over enumerating specific paths
- Related paths are cross-references that provide context (hostname is mandatory)
- Example questions should be specific and answerable from the projected data
"""

_USER_PROMPT = """\
Below is the Tier B class definition for entity type ``{entity_type}``. \
Identify the logical subjects and their attribute path patterns.

```yaml
{tier_b_content}
```
"""


def _extract_path_prefixes(tier_b: dict[str, Any]) -> list[str]:
    """Extract unique top-level path prefixes from Tier B data."""
    prefixes: set[str] = set()

    for key in tier_b.get("base_class", {}):
        prefix = key.split(".")[0]
        prefixes.add(prefix)

    for cls_data in tier_b.get("classes", {}).values():
        for key in cls_data.get("own_attrs", {}):
            prefix = key.split(".")[0]
            prefixes.add(prefix)

    for sub_data in tier_b.get("subclasses", {}).values():
        for key in sub_data.get("own_attrs", {}):
            prefix = key.split(".")[0]
            prefixes.add(prefix)

    return sorted(prefixes)


def _call_llm(
    tier_b_content: str,
    entity_type: str,
    model: str,
    base_url: str,
    api_key_env: str,
) -> dict[str, Any]:
    """Lazy import openai. Build prompt. Call API. Extract YAML block."""
    try:
        from openai import OpenAI
    except ImportError:
        msg = (
            "The openai SDK is required for projection spec inference. "
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
        entity_type=entity_type,
        tier_b_content=tier_b_content,
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


def _validate_llm_response(yaml_str: str) -> dict[str, Any]:
    """Parse YAML. Require subjects list with names and include_paths."""
    yaml = YAML(typ="safe")
    doc = yaml.load(yaml_str)
    if not isinstance(doc, dict):
        msg = "LLM response is not a YAML mapping"
        raise ValueError(msg)
    if "subjects" not in doc or not isinstance(doc["subjects"], list):
        msg = "LLM response missing required 'subjects' list"
        raise ValueError(msg)

    for i, subj in enumerate(doc["subjects"]):
        if not isinstance(subj, dict):
            msg = f"subjects[{i}] must be a mapping"
            raise ValueError(msg)
        if "name" not in subj or not isinstance(subj["name"], str):
            msg = f"subjects[{i}] must have a 'name' string"
            raise ValueError(msg)
        if "include_paths" not in subj or not subj["include_paths"]:
            msg = f"subjects[{i}] must have non-empty 'include_paths'"
            raise ValueError(msg)

    return dict(doc)


def _build_spec(entity_type: str, llm_result: dict[str, Any]) -> ProjectionSpec:
    """Convert validated LLM result to ProjectionSpec."""
    subjects: list[SubjectSpec] = []
    for subj_raw in llm_result.get("subjects", []):
        related_paths: list[RelatedPath] = []
        for rp in subj_raw.get("related_paths", []) or []:
            if isinstance(rp, dict):
                related_paths.append(RelatedPath(
                    path=rp.get("path", ""),
                    reason=rp.get("reason", ""),
                ))
            elif isinstance(rp, str):
                related_paths.append(RelatedPath(path=rp))

        subjects.append(SubjectSpec(
            name=subj_raw["name"],
            description=subj_raw.get("description", ""),
            include_paths=list(subj_raw["include_paths"]),
            related_paths=related_paths,
            example_questions=list(subj_raw.get("example_questions", []) or []),
        ))

    return ProjectionSpec(
        version=1,
        source_type=entity_type,
        generated_by="decoct-infer",
        subjects=subjects,
    )


def infer_projection_spec(
    output_dir: Path,
    type_id: str,
    model: str = "google/gemini-2.5-flash",
    base_url: str = _DEFAULT_BASE_URL,
    api_key_env: str = _DEFAULT_API_KEY_ENV,
    on_progress: Callable[[str], None] | None = None,
) -> ProjectionSpec:
    """Orchestrator: load Tier B → extract paths → LLM call → ProjectionSpec.

    ``on_progress`` callback for status messages.
    """
    def _progress(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    # Load Tier B
    classes_file = output_dir / f"{type_id}_classes.yaml"
    if not classes_file.exists():
        msg = f"Tier B file not found: {classes_file}"
        raise FileNotFoundError(msg)

    _progress(f"Loading Tier B from {classes_file}...")
    yaml = YAML(typ="safe")
    tier_b = yaml.load(classes_file.read_text())

    # Extract path prefixes for context
    prefixes = _extract_path_prefixes(tier_b)
    _progress(f"Found {len(prefixes)} top-level path prefixes: {', '.join(prefixes)}")

    # Serialize Tier B for the prompt
    rt_yaml = YAML(typ="rt")
    rt_yaml.default_flow_style = False
    stream = StringIO()
    rt_yaml.dump(tier_b, stream)
    tier_b_content = stream.getvalue()

    entity_type = tier_b.get("meta", {}).get("entity_type", type_id)
    _progress(f"Calling LLM ({model}) for subject identification...")

    llm_result = _call_llm(tier_b_content, entity_type, model, base_url, api_key_env)
    spec = _build_spec(entity_type, llm_result)

    _progress(f"Identified {len(spec.subjects)} subjects: {', '.join(s.name for s in spec.subjects)}")
    return spec
