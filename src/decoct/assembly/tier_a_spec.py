"""Tier A spec loader and dumper (R4 — enhanced Tier A)."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from decoct.assembly.tier_a_models import (
    TierASpec,
    TierATypeDescription,
)


def load_tier_a_spec(path: str | Path) -> TierASpec:
    """Load and validate a Tier A spec from YAML.

    Raises:
        FileNotFoundError: if the spec file does not exist
        ValueError: if the spec is invalid
    """
    path = Path(path)
    yaml = YAML(typ="safe")
    raw: dict[str, Any] = yaml.load(path.read_text())

    if not isinstance(raw, dict):
        msg = f"Tier A spec must be a YAML mapping, got {type(raw).__name__}"
        raise ValueError(msg)

    # Validate version
    version = raw.get("version")
    if version != 1:
        msg = f"Unsupported Tier A spec version: {version!r} (expected 1)"
        raise ValueError(msg)

    corpus_description = raw.get("corpus_description")
    if not corpus_description or not isinstance(corpus_description, str):
        msg = "Tier A spec must have a non-empty 'corpus_description' string"
        raise ValueError(msg)

    generated_by = raw.get("generated_by", "claude-code")

    how_to_use: list[str] = list(raw.get("how_to_use", []))

    # Parse type_descriptions
    type_descriptions: dict[str, TierATypeDescription] = {}
    raw_descs = raw.get("type_descriptions", {})
    if not isinstance(raw_descs, dict):
        msg = "'type_descriptions' must be a mapping"
        raise ValueError(msg)

    for type_id, desc_raw in raw_descs.items():
        if not isinstance(desc_raw, dict):
            msg = f"type_descriptions['{type_id}'] must be a mapping"
            raise ValueError(msg)

        summary = desc_raw.get("summary")
        if not summary or not isinstance(summary, str):
            msg = f"type_descriptions['{type_id}'] must have a non-empty 'summary' string"
            raise ValueError(msg)

        key_differentiators = list(desc_raw.get("key_differentiators", []))
        type_descriptions[type_id] = TierATypeDescription(
            summary=summary,
            key_differentiators=key_differentiators,
        )

    return TierASpec(
        version=version,
        generated_by=generated_by,
        corpus_description=corpus_description,
        how_to_use=how_to_use,
        type_descriptions=type_descriptions,
    )


def dump_tier_a_spec(spec: TierASpec) -> str:
    """Serialize TierASpec to YAML string using ruamel.yaml round-trip."""
    yaml = YAML(typ="rt")
    yaml.default_flow_style = False

    doc: dict[str, Any] = {
        "version": spec.version,
        "generated_by": spec.generated_by,
        "corpus_description": spec.corpus_description,
    }

    if spec.how_to_use:
        doc["how_to_use"] = spec.how_to_use

    if spec.type_descriptions:
        doc["type_descriptions"] = {}
        for type_id, desc in sorted(spec.type_descriptions.items()):
            td: dict[str, Any] = {"summary": desc.summary}
            if desc.key_differentiators:
                td["key_differentiators"] = desc.key_differentiators
            doc["type_descriptions"][type_id] = td

    stream = StringIO()
    yaml.dump(doc, stream)
    return stream.getvalue()
