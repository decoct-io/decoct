"""YAML I/O helpers using ruamel.yaml round-trip mode."""

from __future__ import annotations

import io
from typing import Any

from ruamel.yaml import YAML


def yaml_dump(data: Any) -> str:
    """Serialize data to YAML string using round-trip mode."""
    yml = YAML(typ="rt")
    yml.default_flow_style = False
    stream = io.StringIO()
    yml.dump(data, stream)
    return stream.getvalue()


def yaml_load(text: str) -> Any:
    """Load YAML from string using round-trip mode."""
    yml = YAML(typ="rt")
    return yml.load(text)


def yaml_serialize(value: Any) -> str:
    """Serialize a value to YAML for token estimation."""
    if value is None:
        return "null"
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return yaml_dump(value)
