"""LLM-assisted ingestion spec inference — identify unknown platform types.

Workflow: run partial pipeline (canonicalise + type seeding) -> identify
``unknown-N`` clusters -> send representative file samples to LLM per cluster
-> assemble IngestionSpec YAML.

LLM provider: OpenAI SDK with configurable ``--base-url`` (defaults to
OpenRouter). Works with any OpenAI-compatible endpoint.
"""

from __future__ import annotations

import os
import warnings
from collections.abc import Callable
from io import StringIO
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from decoct.adapters.ingestion_models import (
    CompositePathSpec,
    IngestionEntry,
    IngestionSpec,
)
from decoct.core.types import Entity
from decoct.llm_utils import extract_yaml_block

_MAX_CHARS_PER_CLUSTER = 50_000
_MAX_SAMPLES_PER_CLUSTER = 3
_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_API_KEY_ENV = "OPENROUTER_API_KEY"

_SYSTEM_PROMPT = """\
You are a platform identification assistant for decoct, an infrastructure \
compression tool. You will be given sample configuration files from an \
unknown platform cluster.

## Task
1. Identify the platform.
2. Identify composite paths (most configs have ZERO — that is fine).

## Output format

If there are NO composite paths (the common case):
```yaml
platform: <platform-name-kebab-case>
description: <one-line description>
```

If there ARE genuine composite paths:
```yaml
platform: <platform-name-kebab-case>
description: <one-line description>
composite_paths:
- path: <key>
  kind: <map|list>
  reason: <one sentence>
```

## Platform naming
- Lowercase kebab-case (e.g., ``docker-compose``, ``postgresql``)
- NEVER output "unknown" — always pick a descriptive name

## What IS a composite path
A key whose value is a HOMOGENEOUS COLLECTION of interchangeable instances:
- ``services`` in docker-compose → each child is a service with same schema
- ``dependencies`` in package.json → each child is ``name: version``
- ``features`` → each child is ``flag-name: boolean``
- ``hosts`` in Ansible inventory → each child is ``hostname: {vars}``

## What is NOT a composite path (do NOT include these)
- Config sections with named settings: ``database: {host, port, name}`` or \
``auth: {jwt_secret, token_expiry}`` — each child has a unique role
- INI sections: ``[Unit]``, ``[Service]``, ``[Install]``, ``[mysqld]``
- Flat scalar namespaces: ``kernel.*``, ``net.ipv4.*``, ``vm.*``, ``fs.*``
- PostgreSQL categories: ``Logging``, ``Replication``, ``Autovacuum``
- Simple scalar arrays: ``dns: [8.8.8.8]``, ``origins: [url1, url2]``

## Rules
- Most platforms have zero composites. Only ``package.json``, \
``docker-compose``, Ansible inventory, and feature-flag configs typically do.
- Use wildcard patterns, not enumeration: ``all.children.*.hosts`` not \
``all.children.app_servers.hosts``, ``all.children.web_servers.hosts``, etc.
- Maximum 3 composite paths per entry.
"""

_USER_PROMPT = """\
Below are {sample_count} sample file(s) from a cluster of similarly-structured \
configuration files. The entity IDs (file stems) in this cluster are: \
{entity_ids}

Identify the platform and any composite paths. Remember: a composite is a \
homogeneous collection of interchangeable instances (like services, hosts, \
dependencies), NOT a config section with named settings (like database, auth, \
logging).

{file_contents}
"""


def _build_stem_map(input_dir: Path) -> dict[str, Path]:
    """Build ``{file_stem: full_path}`` lookup for input directory."""
    stem_map: dict[str, Path] = {}
    for child in sorted(input_dir.iterdir()):
        if child.is_file():
            stem_map[child.stem] = child
    return stem_map


def _select_samples(
    entities: list[Entity],
    stem_map: dict[str, Path],
    max_samples: int = _MAX_SAMPLES_PER_CLUSTER,
    max_chars: int = _MAX_CHARS_PER_CLUSTER,
) -> list[tuple[str, str]]:
    """Pick entities with most attributes. Read file content. Proportional truncation.

    Returns list of ``(entity_id, file_content)`` pairs.
    """
    # Sort by attribute count descending to pick the most representative
    ranked = sorted(entities, key=lambda e: len(e.attributes), reverse=True)
    selected: list[tuple[str, str]] = []

    for entity in ranked[:max_samples]:
        path = stem_map.get(entity.id)
        if path is None:
            continue
        try:
            content = path.read_text()
        except OSError:
            continue
        selected.append((entity.id, content))

    if not selected:
        return selected

    # Proportional truncation if total exceeds max_chars
    total = sum(len(c) for _, c in selected)
    if total > max_chars:
        ratio = max_chars / total
        selected = [
            (eid, content[:max(100, int(len(content) * ratio))])
            for eid, content in selected
        ]

    return selected


def _infer_file_pattern(entity_ids: list[str]) -> str:
    """Longest common prefix -> trim to last '-'/'_' -> append '*'.

    Single entity -> exact match. No common prefix -> '*'.
    Empty list -> '*'.
    """
    if not entity_ids:
        return "*"
    if len(entity_ids) == 1:
        return entity_ids[0]

    # Find longest common prefix
    prefix = os.path.commonprefix(entity_ids)
    if not prefix:
        return "*"

    # Trim to last separator
    last_sep = max(prefix.rfind("-"), prefix.rfind("_"))
    if last_sep >= 0:
        prefix = prefix[: last_sep + 1]

    # If prefix is the entire string of all ids, they're identical — exact match
    if all(eid == prefix for eid in entity_ids):
        return prefix

    return f"{prefix}*"


def _call_llm(
    entity_ids: list[str],
    file_samples: list[tuple[str, str]],
    model: str,
    base_url: str,
    api_key_env: str,
) -> dict[str, Any]:
    """Lazy import openai. Build prompt. Call API. Extract YAML block.

    Validate response. Return parsed dict.
    """
    try:
        from openai import OpenAI
    except ImportError:
        msg = (
            "The openai SDK is required for ingestion spec inference. "
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

    # Build user prompt
    file_contents = "\n".join(
        f"### {eid}\n```\n{content}\n```\n"
        for eid, content in file_samples
    )
    user_prompt = _USER_PROMPT.format(
        sample_count=len(file_samples),
        entity_ids=", ".join(entity_ids),
        file_contents=file_contents,
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
    """Parse YAML. Require 'platform' string. Validate composite_paths kinds."""
    yaml = YAML(typ="safe")
    doc = yaml.load(yaml_str)
    if not isinstance(doc, dict):
        msg = "LLM response is not a YAML mapping"
        raise ValueError(msg)
    if "platform" not in doc or not isinstance(doc["platform"], str):
        msg = "LLM response missing required 'platform' string"
        raise ValueError(msg)

    # Validate composite_paths if present
    for i, cp in enumerate(doc.get("composite_paths", []) or []):
        if not isinstance(cp, dict):
            msg = f"composite_paths[{i}] must be a mapping"
            raise ValueError(msg)
        kind = cp.get("kind", "")
        if kind not in ("map", "list"):
            msg = f"composite_paths[{i}].kind must be 'map' or 'list', got {kind!r}"
            raise ValueError(msg)

    return dict(doc)


def _build_entry(entity_ids: list[str], llm_result: dict[str, Any]) -> IngestionEntry:
    """Combine ``_infer_file_pattern()`` + LLM result -> IngestionEntry."""
    composite_paths: list[CompositePathSpec] = []
    for cp in llm_result.get("composite_paths", []) or []:
        composite_paths.append(CompositePathSpec(
            path=cp["path"],
            kind=cp["kind"],
            reason=cp.get("reason", ""),
        ))

    return IngestionEntry(
        file_pattern=_infer_file_pattern(entity_ids),
        platform=llm_result["platform"],
        description=llm_result.get("description", ""),
        composite_paths=composite_paths,
    )


def infer_ingestion_spec(
    input_dir: Path,
    adapter_name: str = "hybrid-infra",
    model: str = "google/gemini-2.5-flash-lite",
    base_url: str = _DEFAULT_BASE_URL,
    api_key_env: str = _DEFAULT_API_KEY_ENV,
    on_progress: Callable[[str], None] | None = None,
) -> IngestionSpec:
    """Orchestrator: canonicalise -> type seed -> LLM per unknown cluster -> assemble spec.

    ``on_progress`` callback for status messages. Skips cluster on LLM error
    with warning.
    """
    from decoct.adapters.hybrid_infra import HybridInfraAdapter
    from decoct.core.config import EntityGraphConfig
    from decoct.core.entity_graph import EntityGraph
    from decoct.discovery.type_seeding import seed_types_from_hints

    def _progress(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    # Step 1: Canonicalise
    _progress("Canonicalising input files...")
    adapter = HybridInfraAdapter()
    graph = EntityGraph()
    input_path = Path(input_dir)

    sources: list[str] = []
    for child in sorted(input_path.iterdir()):
        if child.is_file():
            sources.append(str(child))

    for source in sources:
        parsed = adapter.parse(source)
        adapter.extract_entities(parsed, graph)

    # Step 2: Type seeding
    _progress("Running type seeding...")
    config = EntityGraphConfig()
    type_map = seed_types_from_hints(graph.entities, config)

    # Step 3: Identify unknown clusters
    unknown_clusters: dict[str, list[Entity]] = {}
    for type_id, entities in type_map.items():
        if type_id.startswith("unknown-"):
            unknown_clusters[type_id] = entities

    _progress(
        f"Found {len(type_map)} types: "
        f"{len(type_map) - len(unknown_clusters)} auto-detected, "
        f"{len(unknown_clusters)} unknown"
    )

    # Step 4: Build stem map for file content lookup
    stem_map = _build_stem_map(input_path)

    # Step 5: LLM call per unknown cluster
    entries: list[IngestionEntry] = []
    for cluster_id in sorted(unknown_clusters):
        cluster_entities = unknown_clusters[cluster_id]
        entity_ids = [e.id for e in cluster_entities]
        _progress(f"Inferring platform for {cluster_id} ({len(entity_ids)} entities)...")

        samples = _select_samples(cluster_entities, stem_map)
        if not samples:
            _progress(f"  Skipping {cluster_id}: no readable files")
            continue

        try:
            llm_result = _call_llm(entity_ids, samples, model, base_url, api_key_env)
            entry = _build_entry(entity_ids, llm_result)
            entries.append(entry)
            _progress(f"  -> platform={entry.platform}, pattern={entry.file_pattern}")
        except Exception as exc:  # noqa: BLE001
            warnings.warn(
                f"LLM call failed for {cluster_id}: {exc}",
                stacklevel=2,
            )
            _progress(f"  Skipping {cluster_id}: {exc}")

    _progress(f"Assembled spec with {len(entries)} entries")

    return IngestionSpec(
        version=1,
        adapter=adapter_name,
        generated_by="decoct-infer",
        entries=entries,
    )


def dump_ingestion_spec(spec: IngestionSpec) -> str:
    """Serialize IngestionSpec to YAML string using ruamel.yaml round-trip."""
    yaml = YAML(typ="rt")
    yaml.default_flow_style = False

    doc: dict[str, Any] = {
        "version": spec.version,
        "adapter": spec.adapter,
        "generated_by": spec.generated_by,
        "entries": [],
    }
    for entry in spec.entries:
        entry_dict: dict[str, Any] = {
            "file_pattern": entry.file_pattern,
            "platform": entry.platform,
            "description": entry.description,
        }
        if entry.composite_paths:
            entry_dict["composite_paths"] = [
                {
                    "path": cp.path,
                    "kind": cp.kind,
                    "reason": cp.reason,
                }
                for cp in entry.composite_paths
            ]
        doc["entries"].append(entry_dict)

    stream = StringIO()
    yaml.dump(doc, stream)
    return stream.getvalue()
