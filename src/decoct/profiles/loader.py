"""Profile data model and loader."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML


@dataclass
class Profile:
    """Named bundle of schema ref, assertion refs, and pass configuration."""

    name: str | None = None
    schema_ref: str | None = None
    assertion_refs: list[str] = field(default_factory=list)
    passes: dict[str, dict[str, Any]] = field(default_factory=dict)


def load_profile(path: str | Path) -> Profile:
    """Load and validate a profile YAML file."""
    path = Path(path)
    yaml = YAML(typ="safe")
    data = yaml.load(path)

    if not isinstance(data, dict):
        msg = f"Profile file must be a YAML mapping: {path}"
        raise ValueError(msg)

    passes_data = data.get("passes", {})
    if not isinstance(passes_data, dict):
        msg = f"Profile 'passes' must be a mapping: {path}"
        raise ValueError(msg)

    passes: dict[str, dict[str, Any]] = {}
    for name, config in passes_data.items():
        if config is None:
            passes[str(name)] = {}
        elif isinstance(config, dict):
            passes[str(name)] = dict(config)
        else:
            msg = f"Profile pass '{name}' config must be a mapping or null: {path}"
            raise ValueError(msg)

    assertion_refs = data.get("assertions", [])
    if not isinstance(assertion_refs, list):
        msg = f"Profile 'assertions' must be a list: {path}"
        raise ValueError(msg)

    return Profile(
        name=data.get("name"),
        schema_ref=data.get("schema"),
        assertion_refs=[str(r) for r in assertion_refs],
        passes=passes,
    )
