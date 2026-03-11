#!/usr/bin/env python3
"""Generate 5G RAN test fixtures from CSV inputs + Jinja2 templates.

Produces 100 mixed-format files (YAML + JSON) spanning 9 config types
across a metro 5G deployment. Represents a regional mobile operator ("SpectrumOne")
with disaggregated RAN architecture, network slicing, and 5G SA/NSA sites.

Requires: pip install jinja2  (NOT a project dependency)

Usage:
    python generate_configs.py                              # Generate all 100 configs
    python generate_configs.py --config-type gnodeb-cell    # Generate one type only
    python generate_configs.py --dry-run                    # Show what would be generated
    python generate_configs.py --output-dir /tmp            # Custom output directory
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import yaml

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    print("ERROR: jinja2 is required. Install with: pip install jinja2", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
TEMPLATES_DIR = SCRIPT_DIR / "templates"
INPUTS_DIR = SCRIPT_DIR / "inputs"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR.parent / "configs"

# ── Config type definitions ────────────────────────────────────────────────────

CONFIG_TYPES: dict[str, dict] = {
    # YAML types
    "gnodeb-cell": {"format": "yaml", "ext": ".yaml", "schema": None},
    "gnodeb-du": {"format": "yaml", "ext": ".yaml", "schema": None},
    "gnodeb-cu": {"format": "yaml", "ext": ".yaml", "schema": None},
    "network-slice": {"format": "yaml", "ext": ".yaml", "schema": None},
    "ran-policy": {"format": "yaml", "ext": ".yaml", "schema": None},
    "site-metadata": {"format": "yaml", "ext": ".yaml", "schema": None},
    # JSON types
    "transport-link": {"format": "json", "ext": ".json", "schema": None},
    "core-amf": {"format": "json", "ext": ".json", "schema": None},
    "core-smf": {"format": "json", "ext": ".json", "schema": None},
}

ALL_CONFIG_TYPES = list(CONFIG_TYPES.keys())


# ── Helpers ────────────────────────────────────────────────────────────────────


def parse_semicolon_list(raw: str) -> list[str]:
    """Parse semicolon-separated list, filtering empty strings."""
    if not raw or raw.strip().lower() == "none":
        return []
    return [item.strip() for item in raw.split(";") if item.strip()]


def parse_bool(raw: str) -> bool:
    """Parse string to boolean."""
    return raw.strip().lower() in ("true", "1", "yes")


def parse_int(raw: str, default: int = 0) -> int:
    """Parse string to int with default."""
    try:
        return int(raw.strip())
    except (ValueError, AttributeError):
        return default


# ── Context Builders ───────────────────────────────────────────────────────────


def build_context(row: dict[str, str], config_type: str) -> dict:
    """Build Jinja2 template context from a CSV row."""
    ctx: dict = dict(row)
    for k, v in ctx.items():
        if isinstance(v, str):
            ctx[k] = v.strip()

    ctx = {k: v for k, v in ctx.items() if k is not None}

    builder = CONTEXT_BUILDERS.get(config_type)
    if builder:
        ctx.update(builder(row))

    return ctx


def _build_gnodeb_du(row: dict[str, str]) -> dict:
    """Enrich DU context — parse connected cells list."""
    return {
        "connected_cells": parse_semicolon_list(row.get("connected_cells", "")),
    }


def _build_gnodeb_cu(row: dict[str, str]) -> dict:
    """Enrich CU context — parse connected DUs list."""
    return {
        "connected_dus": parse_semicolon_list(row.get("connected_dus", "")),
    }


def _build_transport_link(row: dict[str, str]) -> dict:
    """Enrich transport link context."""
    return {}


def _build_core_amf(row: dict[str, str]) -> dict:
    """Enrich AMF context — parse TAI list."""
    return {
        "tai_list": parse_semicolon_list(row.get("tai_list", "")),
    }


def _build_core_smf(row: dict[str, str]) -> dict:
    """Enrich SMF context — parse UPF associations and DNN list."""
    return {
        "upf_associations": parse_semicolon_list(row.get("upf_associations", "")),
        "dnn_list": parse_semicolon_list(row.get("dnn_list", "")),
    }


CONTEXT_BUILDERS: dict[str, callable] = {
    "gnodeb-du": _build_gnodeb_du,
    "gnodeb-cu": _build_gnodeb_cu,
    "transport-link": _build_transport_link,
    "core-amf": _build_core_amf,
    "core-smf": _build_core_smf,
}


# ── Validation ─────────────────────────────────────────────────────────────────


def validate_yaml(rendered: str, filename: str) -> None:
    """Validate rendered YAML is parseable."""
    try:
        yaml.safe_load(rendered)
    except yaml.YAMLError as e:
        print(f"ERROR: Invalid YAML for {filename}: {e}", file=sys.stderr)
        print(f"  Rendered output:\n{rendered[:500]}", file=sys.stderr)
        sys.exit(1)


def validate_json(rendered: str, filename: str) -> str:
    """Validate and reformat rendered JSON."""
    try:
        parsed = json.loads(rendered)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON for {filename}: {e}", file=sys.stderr)
        print(f"  Rendered output:\n{rendered[:500]}", file=sys.stderr)
        sys.exit(1)
    return json.dumps(parsed, indent=2) + "\n"


VALIDATORS = {
    "yaml": validate_yaml,
    "json": validate_json,
}


# ── Generation ─────────────────────────────────────────────────────────────────


def generate(config_type: str, env: Environment, output_dir: Path, dry_run: bool) -> int:
    """Generate configs for a single type. Returns count of files generated."""
    csv_path = INPUTS_DIR / f"{config_type}.csv"
    if not csv_path.exists():
        print(f"WARNING: {csv_path} not found, skipping", file=sys.stderr)
        return 0

    type_info = CONFIG_TYPES[config_type]
    fmt = type_info["format"]
    ext = type_info["ext"]
    template = env.get_template(f"{config_type}.j2")

    count = 0

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    for row in rows:
        ctx = build_context(row, config_type)
        filename = f"{ctx['filename']}{ext}"
        output_file = output_dir / filename

        if dry_run:
            print(f"  Would generate: {output_file}")
        else:
            rendered = template.render(**ctx)
            if fmt == "yaml":
                validate_yaml(rendered, filename)
            elif fmt == "json":
                rendered = validate_json(rendered, filename)
            output_file.write_text(rendered)
        count += 1

    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate 5G RAN test fixtures")
    parser.add_argument(
        "--config-type",
        choices=ALL_CONFIG_TYPES,
        help="Generate configs for a specific type only",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be generated without writing files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory for generated files",
    )
    args = parser.parse_args()

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )

    if not args.dry_run:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    types = [args.config_type] if args.config_type else ALL_CONFIG_TYPES
    total = 0

    for ct in types:
        print(f"Generating {ct} configs...")
        count = generate(ct, env, args.output_dir, args.dry_run)
        print(f"  {count} configs {'would be ' if args.dry_run else ''}generated")
        total += count

    print(f"\nTotal: {total} configs {'would be ' if args.dry_run else ''}generated in {args.output_dir}")


if __name__ == "__main__":
    main()
