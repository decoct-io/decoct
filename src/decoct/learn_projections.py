"""LLM-assisted projection spec inference — identify subjects from Tier B+C.

Workflow: load Tier B classes + Tier C instance metadata → extract attribute
context → send to LLM → parse response → return ProjectionSpec.

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
compression tool. You will be given Tier B class definitions AND Tier C \
instance metadata for an entity type. Your job is to identify logical \
subjects — focused groups of related attributes that an engineer would \
query together.

## Input Data

You receive two data sources:
- **Tier B** (class definitions): shared attribute sets, class own_attrs, \
subclass own_attrs — these are the attributes that are COMMON across entities.
- **Tier C context** (instance metadata): phone book schema (attributes that \
VARY per entity), override attribute keys (per-entity exceptions), and \
instance count. These reveal what differs across the fleet.

## Task
1. Identify 4-10 logical subjects from the attribute paths.
2. For each subject, write glob patterns that select the relevant paths.
3. Include ``hostname`` as a related_path for all subjects.
4. Write 2-3 example questions per subject that the projection can answer.

## Critical Guidance

**Use Tier C metadata to create focused subjects:**
- Phone book schema attributes are the ones that VARY per entity. These are \
high-value for per-entity queries (e.g. IP addresses, SIDs, server IDs).
- Override keys show which shared attributes have per-entity exceptions.
- Create subjects that group related variable attributes together — these \
are the most useful for answering fleet comparison questions.

**Create narrow, query-answerable subjects:**
- Each subject should answer a clear category of questions.
- Prefer 4-6 attributes per subject over 20+ attribute mega-subjects.
- Split large domains into sub-topics. For example, instead of one broad \
"interfaces" subject with 30 attributes, create "interface-identity" \
(descriptions, names), "interface-addressing" (IPs, VRFs), \
"interface-protocols" (ARP, ISIS, MPLS settings) as separate subjects.
- A subject with 50+ matched attributes is too broad — split it.

**Ensure phone book attributes are covered:**
- Every phone book schema attribute must appear in at least one subject.
- Phone book attributes that relate to identity (hostname, description, \
location) should be in an "identity" or "device-metadata" subject.
- Phone book attributes that relate to protocols should join the relevant \
protocol subject.

**Cross-entity comparison subjects:**
- If several phone book columns belong to the same protocol or function \
(e.g. multiple prefix-sid attributes, multiple IP addresses), group them \
into a dedicated comparison subject.

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
- Subject names should be descriptive kebab-case (e.g. ``bgp-neighbors``, \
``interface-addressing``, ``isis-segment-routing``)
- Each attribute path should belong to at least one subject
- Prefer focused patterns over catch-all wildcards
- Related paths are cross-references that provide context (hostname is mandatory)
- Example questions should be specific and answerable from the projected data
"""

_USER_PROMPT = """\
Below is the Tier B class definition and Tier C instance metadata for \
entity type ``{entity_type}``. Identify the logical subjects and their \
attribute path patterns.

## Tier B — Class Definitions
```yaml
{tier_b_content}
```

## Tier C — Instance Metadata
{tier_c_context}

Based on BOTH the class structure AND the per-entity variance data, \
identify focused projection subjects.
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


def _extract_tier_c_context(tier_c: dict[str, Any]) -> str:
    """Extract a concise metadata summary from Tier C instance data.

    Returns a human-readable string describing:
    - Phone book schema (per-entity variable attributes)
    - Override attribute keys (per-entity exceptions to class values)
    - Instance count and class assignment summary
    """
    parts: list[str] = []

    # Phone book schema
    instance_data = tier_c.get("instance_data", {})
    schema = instance_data.get("schema", [])
    if schema:
        parts.append(f"**Phone book schema** ({len(schema)} per-entity variable attributes):")
        for attr in schema:
            parts.append(f"  - ``{attr}``")

        # Count records for instance count
        records = instance_data.get("records", {})
        if records:
            parts.append(f"\n**Instance count:** {len(records)} entities with phone book values.")
    else:
        parts.append("**Phone book:** (none — no per-entity scalar variance)")

    # Override keys
    overrides = tier_c.get("overrides", {})
    if overrides:
        override_keys: set[str] = set()
        for entity_overrides in overrides.values():
            if isinstance(entity_overrides, dict):
                delta = entity_overrides.get("delta", entity_overrides)
                if isinstance(delta, dict):
                    override_keys.update(delta.keys())
        if override_keys:
            parts.append(f"\n**Override attributes** ({len(override_keys)} attributes with per-entity exceptions):")
            for key in sorted(override_keys):
                parts.append(f"  - ``{key}``")
            total = len(tier_c.get("instance_data", {}).get("records", {})) or len(overrides)
            parts.append(f"\n**Entities with overrides:** {len(overrides)}/{total} entities")

    # Instance attrs (sparse complex structures)
    instance_attrs = tier_c.get("instance_attrs", {})
    if instance_attrs:
        attr_keys: set[str] = set()
        for entity_attrs in instance_attrs.values():
            if isinstance(entity_attrs, dict):
                attr_keys.update(entity_attrs.keys())
        if attr_keys:
            n_keys, n_ents = len(attr_keys), len(instance_attrs)
            parts.append(f"\n**Instance-specific complex attributes** ({n_keys} unique keys across {n_ents} entities):")
            for key in sorted(attr_keys):
                parts.append(f"  - ``{key}``")

    # Class assignments summary
    class_assignments = tier_c.get("class_assignments", {})
    if class_assignments:
        parts.append(f"\n**Class assignments:** {len(class_assignments)} classes")
        for cls_name, cls_data in class_assignments.items():
            instances = cls_data if isinstance(cls_data, dict) else {}
            inst_list = instances.get("instances", []) if isinstance(instances, dict) else []
            if isinstance(inst_list, list):
                parts.append(f"  - ``{cls_name}``: {len(inst_list)} instances")

    return "\n".join(parts) if parts else "(No Tier C data available)"


def _call_llm(
    tier_b_content: str,
    tier_c_context: str,
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
        tier_c_context=tier_c_context,
    )

    client = OpenAI(base_url=base_url, api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=8192,
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
    """Orchestrator: load Tier B+C → extract context → LLM call → ProjectionSpec.

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

    # Load Tier C (optional — degrade gracefully)
    instances_file = output_dir / f"{type_id}_instances.yaml"
    tier_c_context = "(No Tier C data available)"
    if instances_file.exists():
        _progress(f"Loading Tier C from {instances_file}...")
        tier_c = yaml.load(instances_file.read_text())
        if isinstance(tier_c, dict):
            tier_c_context = _extract_tier_c_context(tier_c)
    else:
        _progress("No Tier C file found — proceeding with Tier B only.")

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

    llm_result = _call_llm(tier_b_content, tier_c_context, entity_type, model, base_url, api_key_env)
    spec = _build_spec(entity_type, llm_result)

    _progress(f"Identified {len(spec.subjects)} subjects: {', '.join(s.name for s in spec.subjects)}")
    return spec
