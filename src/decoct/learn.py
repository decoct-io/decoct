"""LLM-assisted schema derivation — extract defaults from examples and docs."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

_SYSTEM_PROMPT = """\
You are a schema extraction assistant for decoct, an infrastructure compression tool.
Your job is to analyse configuration files and/or documentation and extract platform
default values — values that the platform assigns when a field is not explicitly set.

Output a YAML schema in exactly this format:

```yaml
platform: <platform-name>
source: <where you derived defaults from>
confidence: <authoritative|high|medium|low>
defaults:
  <dotted.path>: <default_value>
  <dotted.path.with.*.wildcard>: <default_value>
drop_patterns: []
system_managed: []
```

Rules:
- Use dotted paths with `*` as single-segment wildcard (e.g., `services.*.restart`)
- Use `**` for any-depth wildcard (e.g., `**.backup: false`)
- Only include values you are confident are actual platform defaults
- Quote YAML keys that start with `*` or `**` (e.g., `"**.backup": false`)
- Set confidence based on your certainty: authoritative if from official docs/specs,
  high if from well-known conventions, medium if inferred, low if guessing
- For system_managed, list paths of fields generated/managed by the system (e.g., metadata.uid)
- For drop_patterns, list paths that should always be removed (e.g., internal IDs)
- Do NOT include fields that have no default (required fields, or fields whose absence
  means the feature is disabled)
- Scalars only for default values — no dicts or lists
"""

_EXAMPLE_PROMPT = """\
Analyse the following configuration {source_type} and extract platform defaults.
For each field, determine: is there a known default value for this platform?
If a field in the example matches the platform default, include it in the schema.

{content}

Generate the decoct schema YAML.
"""

_DOC_PROMPT = """\
Analyse the following platform documentation and extract all default values mentioned.

{content}

Generate the decoct schema YAML.
"""

_COMBINED_PROMPT = """\
Analyse the following configuration examples and documentation to extract platform defaults.

## Configuration Examples
{examples}

## Documentation
{docs}

Generate the decoct schema YAML with all defaults you can identify.
"""


def _read_file(path: Path) -> str:
    """Read a file and return labelled content."""
    content = path.read_text()
    return f"### {path.name}\n```\n{content}\n```\n"


def _extract_schema_yaml(response_text: str) -> str:
    """Extract YAML from a markdown code block or raw response."""
    # Look for ```yaml ... ``` block
    import re

    match = re.search(r"```ya?ml\s*\n(.*?)```", response_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Try ``` ... ``` block
    match = re.search(r"```\s*\n(.*?)```", response_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Return as-is (might be raw YAML)
    return response_text.strip()


def _validate_schema(schema_yaml: str) -> dict[str, Any]:
    """Parse and validate the generated schema YAML."""
    yaml = YAML(typ="rt")
    doc = yaml.load(schema_yaml)
    if not isinstance(doc, dict):
        msg = "Generated schema is not a YAML mapping"
        raise ValueError(msg)
    required_keys = {"platform", "defaults"}
    missing = required_keys - set(doc.keys())
    if missing:
        msg = f"Generated schema missing required keys: {missing}"
        raise ValueError(msg)
    if not isinstance(doc["defaults"], dict):
        msg = "defaults must be a mapping"
        raise ValueError(msg)
    # Ensure optional keys exist
    doc.setdefault("source", "LLM-derived")
    doc.setdefault("confidence", "medium")
    doc.setdefault("drop_patterns", [])
    doc.setdefault("system_managed", [])
    return dict(doc)


def learn_schema(
    *,
    examples: list[Path] | None = None,
    docs: list[Path] | None = None,
    platform: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> str:
    """Derive a schema from example files and/or documentation using an LLM.

    Args:
        examples: Configuration file paths to analyse.
        docs: Documentation file paths to analyse.
        platform: Optional platform name hint.
        model: Anthropic model to use.

    Returns:
        Schema YAML string.

    Raises:
        ImportError: If anthropic SDK is not installed.
        ValueError: If no input files provided or schema generation fails.
    """
    try:
        import anthropic
    except ImportError:
        msg = (
            "The anthropic SDK is required for schema learning. "
            "Install it with: pip install decoct[llm]"
        )
        raise ImportError(msg)  # noqa: B904

    if not examples and not docs:
        msg = "At least one example file or documentation file is required"
        raise ValueError(msg)

    # Build prompt
    if examples and docs:
        example_content = "\n".join(_read_file(p) for p in examples)
        doc_content = "\n".join(_read_file(p) for p in docs)
        user_prompt = _COMBINED_PROMPT.format(examples=example_content, docs=doc_content)
    elif examples:
        content = "\n".join(_read_file(p) for p in examples)
        user_prompt = _EXAMPLE_PROMPT.format(source_type="files", content=content)
    else:
        content = "\n".join(_read_file(p) for p in (docs or []))
        user_prompt = _DOC_PROMPT.format(content=content)

    if platform:
        user_prompt += f"\n\nThe platform is: {platform}\n"

    # Call the API
    client = anthropic.Anthropic()
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    response_text = message.content[0].text
    schema_yaml = _extract_schema_yaml(response_text)

    # Validate
    _validate_schema(schema_yaml)

    return schema_yaml


def learn_schema_to_file(
    output: Path,
    *,
    examples: list[Path] | None = None,
    docs: list[Path] | None = None,
    platform: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> Path:
    """Derive a schema and write it to a file.

    Returns the output path.
    """
    schema_yaml = learn_schema(
        examples=examples,
        docs=docs,
        platform=platform,
        model=model,
    )
    output.write_text(schema_yaml + "\n")
    return output


def merge_schemas(base: Path, additions: str) -> str:
    """Merge additional defaults into an existing schema.

    Returns the merged schema YAML string.
    """
    yaml = YAML(typ="rt")
    base_doc = yaml.load(base.read_text())
    add_doc = yaml.load(additions)

    if not isinstance(base_doc, dict) or not isinstance(add_doc, dict):
        msg = "Both schemas must be YAML mappings"
        raise ValueError(msg)

    # Merge defaults
    base_defaults = base_doc.get("defaults", {})
    add_defaults = add_doc.get("defaults", {})
    for key, value in add_defaults.items():
        if key not in base_defaults:
            base_defaults[key] = value

    # Merge system_managed and drop_patterns
    for list_key in ("system_managed", "drop_patterns"):
        base_list = base_doc.get(list_key, []) or []
        add_list = add_doc.get(list_key, []) or []
        merged = list(dict.fromkeys(list(base_list) + list(add_list)))
        base_doc[list_key] = merged

    stream = StringIO()
    yaml.dump(base_doc, stream)
    return stream.getvalue()
