"""OutputStore: reads compressed output (tier_b.yaml + per-host YAML) and builds indexes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from decoct.reconstruct import unflatten_collapsed


def _unflatten_tier_b(tier_b: dict[str, Any]) -> dict[str, Any]:
    """Unflatten collapsed dot-notation in Tier B class bodies and list class bodies."""
    result: dict[str, Any] = {}
    for key, value in tier_b.items():
        if key == "_list_classes" and isinstance(value, dict):
            # Unflatten _body within each list class
            unflat_lc: dict[str, Any] = {}
            for lc_name, lc_def in value.items():
                if isinstance(lc_def, dict) and "_body" in lc_def:
                    lc_copy = dict(lc_def)
                    lc_copy["_body"] = unflatten_collapsed(lc_def["_body"])
                    unflat_lc[lc_name] = lc_copy
                else:
                    unflat_lc[lc_name] = lc_def
            result[key] = unflat_lc
        elif isinstance(value, dict):
            result[key] = unflatten_collapsed(value)
        else:
            result[key] = value
    return result


def _unflatten_tier_c(tier_c_host: dict[str, Any]) -> dict[str, Any]:
    """Unflatten collapsed dot-notation in passthrough sections of Tier C.

    Sections with ``_class`` or ``_list_class`` use dot-notation by design
    (delta overrides), so they are left as-is.  Only raw passthrough sections
    are unflattened.
    """
    result: dict[str, Any] = {}
    for section, value in tier_c_host.items():
        if section == "_class_instances":
            result[section] = value
        elif isinstance(value, dict) and ("_class" in value or "_list_class" in value):
            result[section] = value
        else:
            result[section] = unflatten_collapsed(value)
    return result


class OutputStore:
    """Reads and caches compressed output for the API."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.tier_b: dict[str, Any] = {}
        self.tier_c: dict[str, dict[str, Any]] = {}
        self.hostnames: list[str] = []

        # Projections index: type_id -> list of subject names
        self.projection_index: dict[str, list[str]] = {}

    def load(self) -> None:
        """Load all output files and build indexes."""
        yaml = YAML(typ="safe")

        # Load Tier B
        tier_b_path = self.output_dir / "tier_b.yaml"
        if tier_b_path.exists():
            self.tier_b = yaml.load(tier_b_path.read_text()) or {}

        # Unflatten collapsed dot-notation in class bodies
        self.tier_b = _unflatten_tier_b(self.tier_b)

        # Load per-host Tier C files
        for f in sorted(self.output_dir.iterdir()):
            if f.is_file() and f.suffix == ".yaml" and f.name != "tier_b.yaml":
                hostname = f.stem
                self.hostnames.append(hostname)
                raw = yaml.load(f.read_text()) or {}
                self.tier_c[hostname] = _unflatten_tier_c(raw)

        # Scan projections
        self._scan_projections()

    def _scan_projections(self) -> None:
        """Scan projections/ subdirectory for available projection YAML files."""
        proj_dir = self.output_dir / "projections"
        if not proj_dir.is_dir():
            return
        for type_dir in sorted(proj_dir.iterdir()):
            if not type_dir.is_dir():
                continue
            subjects: list[str] = []
            for f in sorted(type_dir.iterdir()):
                if f.suffix in (".yaml", ".yml") and f.stem != "projection_spec":
                    subjects.append(f.stem)
            if subjects:
                self.projection_index[type_dir.name] = subjects

    def load_projection(self, type_id: str, subject: str) -> dict[str, Any] | None:
        """Load a specific projection YAML file."""
        proj_file = self.output_dir / "projections" / type_id / f"{subject}.yaml"
        if not proj_file.exists():
            return None
        yaml = YAML(typ="safe")
        result = yaml.load(proj_file.read_text())
        return result if isinstance(result, dict) else {}

    def has_host(self, hostname: str) -> bool:
        return hostname in self.tier_c
