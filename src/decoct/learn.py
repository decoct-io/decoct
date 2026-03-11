"""LLM-assisted learning — derive schemas and assertions from examples and docs."""

from __future__ import annotations

import sys
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


def extract_yaml_block(response_text: str) -> str:
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


# Keep backward-compatible alias
_extract_yaml_block = extract_yaml_block  # backward-compatible private alias
_extract_schema_yaml = extract_yaml_block


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
    schema_yaml = extract_yaml_block(response_text)

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


# ---------------------------------------------------------------------------
# Assertion learning
# ---------------------------------------------------------------------------

_ASSERTION_SYSTEM_PROMPT = """\
You are an assertion extraction assistant for decoct, an infrastructure compression tool.
Your job is to analyse standards documents, policy documents, and/or example configuration
files and produce machine-evaluable assertions that encode the design standards described.

Output assertions YAML in exactly this format:

```yaml
assertions:
  - id: <short-kebab-case-id>
    assert: <one-line description of what should be true>
    rationale: <why this matters>
    severity: <must|should|may>
    match:
      path: <dotted.path.with.*.wildcard>
      <condition>: <value>
```

Match condition types (use exactly one per match):
- value: exact value match (e.g., `value: "always"`)
- pattern: regex pattern match (e.g., `pattern: "^sha256:"`)
- range: numeric range [min, max] (e.g., `range: [1, 65535]`)
- contains: value must appear in a list (e.g., `contains: "no-new-privileges"`)
- not_value: value must NOT be this (e.g., `not_value: "latest"`)
- exists: field must be present (true) or absent (false) (e.g., `exists: true`)

Rules:
- Use dotted paths with `*` as single-segment wildcard (e.g., `services.*.restart`)
- Use `**` for any-depth wildcard (e.g., `**.resources.limits.memory`)
- severity: `must` for security/compliance requirements, `should` for best practices, \
`may` for recommendations
- `match` is optional — assertions without `match` serve as LLM context only, not \
machine-evaluated
- Quote YAML keys that start with `*` or `**`
- Each assertion needs a unique `id` in kebab-case
- Keep `assert` descriptions concise and declarative
- Include `rationale` explaining why the standard exists
"""

_ASSERTION_STANDARDS_PROMPT = """\
Analyse the following standards/policy document(s) and extract design assertions.
For each requirement or recommendation, create a machine-evaluable assertion.

{content}

Generate the decoct assertions YAML.
"""

_ASSERTION_EXAMPLE_PROMPT = """\
Analyse the following configuration {source_type} and infer design standards.
Look for patterns that suggest intentional standards (naming conventions, resource limits,
security settings, etc.) and create assertions for them.

{content}

Generate the decoct assertions YAML.
"""

_ASSERTION_COMBINED_PROMPT = """\
Analyse the following standards documents and configuration examples to extract \
design assertions.
Use the standards as the primary source and the examples to validate and refine the assertions.

## Standards / Policy Documents
{standards}

## Configuration Examples
{examples}

Generate the decoct assertions YAML with all standards you can identify.
"""

_ASSERTION_CORPUS_PROMPT = """\
You have been given {file_count} configuration files from the same organisation. \
Treat them as a statistical sample of real-world practice. Your job is to identify \
cross-file commonalities — de facto standards the organisation follows even if never \
written down.

Compare values across files and find consensus:
- Only include patterns present in more than 50% of the files.
- Map consistency to severity: `must` (100% of files), `should` (>75%), `may` (>50%).
- In the `rationale`, always state the prevalence (e.g., "Set in 8/10 files").
- Ignore environment-specific values (hostnames, IP addresses, ports that vary, \
passwords, paths containing environment names).
- Focus on security settings, resource limits, restart policies, naming conventions, \
and structural patterns.

## Corpus Files
{corpus}

Generate the decoct assertions YAML.
"""

_ASSERTION_CORPUS_STANDARDS_PROMPT = """\
You have been given {file_count} configuration files from the same organisation \
and a set of standards/policy documents. Compare de facto practice against written policy.

Generate assertions for both:
1. Written standards from the policy documents (use the standard severity).
2. Observed patterns from the corpus (only patterns in >50% of files).

For observed patterns, map consistency to severity: `must` (100%), `should` (>75%), \
`may` (>50%). In the `rationale`, note the compliance level (e.g., \
"Policy requires X; 8/10 files comply" or "Not in policy but set in 9/10 files").

Ignore environment-specific values (hostnames, IP addresses, varying ports, passwords).

## Standards / Policy Documents
{standards}

## Corpus Files
{corpus}

Generate the decoct assertions YAML with all standards you can identify.
"""

_VALID_SEVERITY = {"must", "should", "may"}


def _validate_assertions(assertions_yaml: str) -> list[dict[str, Any]]:
    """Parse and validate the generated assertions YAML.

    Returns the list of assertion dicts.
    """
    yaml = YAML(typ="rt")
    doc = yaml.load(assertions_yaml)
    if not isinstance(doc, dict):
        msg = "Generated assertions is not a YAML mapping"
        raise ValueError(msg)
    if "assertions" not in doc:
        msg = "Generated assertions missing required 'assertions' key"
        raise ValueError(msg)
    items = doc["assertions"]
    if not isinstance(items, list):
        msg = "'assertions' must be a list"
        raise ValueError(msg)
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            msg = f"Assertion at index {i} is not a mapping"
            raise ValueError(msg)
        for required in ("id", "assert", "rationale", "severity"):
            if required not in item:
                msg = f"Assertion at index {i} missing required field '{required}'"
                raise ValueError(msg)
        if item["severity"] not in _VALID_SEVERITY:
            msg = f"Assertion '{item['id']}' severity must be one of {_VALID_SEVERITY}, got '{item['severity']}'"
            raise ValueError(msg)
        if "match" in item and isinstance(item["match"], dict):
            if "path" not in item["match"]:
                msg = f"Assertion '{item['id']}' match missing required field 'path'"
                raise ValueError(msg)
    return list(items)


_CORPUS_MAX_CHARS = 300_000


def _prepare_corpus(files: list[Path]) -> str:
    """Read corpus files, truncating proportionally if total exceeds limit."""
    contents = [(p, p.read_text()) for p in files]
    total = sum(len(c) for _, c in contents)
    if total > _CORPUS_MAX_CHARS:
        print(
            f"Warning: corpus content ({total} chars) exceeds {_CORPUS_MAX_CHARS} limit; "
            "truncating files proportionally.",
            file=sys.stderr,
        )
        ratio = _CORPUS_MAX_CHARS / total
        truncated: list[tuple[Path, str]] = []
        for p, c in contents:
            limit = max(100, int(len(c) * ratio))
            truncated.append((p, c[:limit]))
        contents = truncated
    return "\n".join(f"### {p.name}\n```\n{c}\n```\n" for p, c in contents)


def learn_assertions(
    *,
    standards: list[Path] | None = None,
    examples: list[Path] | None = None,
    corpus: list[Path] | None = None,
    platform: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> str:
    """Derive assertions from standards documents, examples, or corpus using an LLM.

    Args:
        standards: Standards/policy document paths to analyse.
        examples: Example configuration file paths to analyse.
        corpus: Config files for cross-file pattern analysis.
        platform: Optional platform name hint.
        model: Anthropic model to use.

    Returns:
        Assertions YAML string.

    Raises:
        ImportError: If anthropic SDK is not installed.
        ValueError: If no input files provided, or corpus and examples both given.
    """
    try:
        import anthropic
    except ImportError:
        msg = (
            "The anthropic SDK is required for assertion learning. "
            "Install it with: pip install decoct[llm]"
        )
        raise ImportError(msg)  # noqa: B904

    if corpus and examples:
        msg = "--corpus and --example are mutually exclusive"
        raise ValueError(msg)

    if not standards and not examples and not corpus:
        msg = "At least one standard, example, or corpus file is required"
        raise ValueError(msg)

    # Build prompt
    if corpus and standards:
        standards_content = "\n".join(_read_file(p) for p in standards)
        corpus_content = _prepare_corpus(corpus)
        user_prompt = _ASSERTION_CORPUS_STANDARDS_PROMPT.format(
            file_count=len(corpus), standards=standards_content, corpus=corpus_content
        )
    elif corpus:
        corpus_content = _prepare_corpus(corpus)
        user_prompt = _ASSERTION_CORPUS_PROMPT.format(file_count=len(corpus), corpus=corpus_content)
    elif standards and examples:
        standards_content = "\n".join(_read_file(p) for p in standards)
        example_content = "\n".join(_read_file(p) for p in examples)
        user_prompt = _ASSERTION_COMBINED_PROMPT.format(standards=standards_content, examples=example_content)
    elif standards:
        content = "\n".join(_read_file(p) for p in standards)
        user_prompt = _ASSERTION_STANDARDS_PROMPT.format(content=content)
    else:
        content = "\n".join(_read_file(p) for p in (examples or []))
        user_prompt = _ASSERTION_EXAMPLE_PROMPT.format(source_type="files", content=content)

    if platform:
        user_prompt += f"\n\nThe platform is: {platform}\n"

    # Call the API
    client = anthropic.Anthropic()
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=_ASSERTION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    response_text = message.content[0].text
    assertions_yaml = extract_yaml_block(response_text)

    # Validate
    _validate_assertions(assertions_yaml)

    return assertions_yaml


def merge_assertions(base: Path, additions: str) -> str:
    """Merge additional assertions into an existing assertions file.

    Merges by assertion id — additions with an id already in the base are skipped.
    Returns the merged assertions YAML string.
    """
    yaml = YAML(typ="rt")
    base_doc = yaml.load(base.read_text())
    add_doc = yaml.load(additions)

    if not isinstance(base_doc, dict) or not isinstance(add_doc, dict):
        msg = "Both files must be YAML mappings"
        raise ValueError(msg)

    base_items = base_doc.get("assertions", []) or []
    add_items = add_doc.get("assertions", []) or []

    existing_ids = {item["id"] for item in base_items if isinstance(item, dict) and "id" in item}
    for item in add_items:
        if isinstance(item, dict) and item.get("id") not in existing_ids:
            base_items.append(item)

    base_doc["assertions"] = base_items

    stream = StringIO()
    yaml.dump(base_doc, stream)
    return stream.getvalue()
