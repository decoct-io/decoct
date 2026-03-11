#!/usr/bin/env python3
"""Generate CDN edge PoP test fixtures from CSV inputs + Jinja2 templates.

Produces ~80 mixed-format files (YAML + JSON + INI-like conf) spanning 9 config types
across 8 global PoPs. Represents a realistic CDN startup deployment ("ArcticCache")
with near-identical per-PoP configs and regional tuning.

Requires: pip install jinja2  (NOT a project dependency)

Usage:
    python generate_configs.py                              # Generate all ~80 configs
    python generate_configs.py --config-type haproxy        # Generate one type only
    python generate_configs.py --dry-run                    # Show what would be generated
    python generate_configs.py --output-dir /tmp            # Custom output directory
"""

from __future__ import annotations

import argparse
import csv
import json
import re
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
    # INI-like conf types
    "nginx-site": {"format": "ini", "ext": ".conf", "schema": None},
    "haproxy": {"format": "ini", "ext": ".conf", "schema": None},
    "dns-zone": {"format": "ini", "ext": ".conf", "schema": None},
    "keepalived": {"format": "ini", "ext": ".conf", "schema": None},
    # YAML types
    "varnish-params": {"format": "yaml", "ext": ".yaml", "schema": None},
    "prometheus": {"format": "yaml", "ext": ".yaml", "schema": "prometheus"},
    "edge-compute": {"format": "yaml", "ext": ".yaml", "schema": None},
    # JSON types
    "ssl-config": {"format": "json", "ext": ".json", "schema": None},
    "pop-metadata": {"format": "json", "ext": ".json", "schema": None},
}

ALL_CONFIG_TYPES = list(CONFIG_TYPES.keys())


# ── Helpers ────────────────────────────────────────────────────────────────────


def slugify(name: str) -> str:
    """Convert a name to a filesystem-safe slug."""
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def parse_semicolon_list(raw: str) -> list[str]:
    """Parse semicolon-separated list, filtering empty strings."""
    if not raw or raw.strip().lower() == "none":
        return []
    return [item.strip() for item in raw.split(";") if item.strip()]


def parse_key_value_pairs(raw: str) -> list[dict[str, str]]:
    """Parse 'key:value;...' into list of dicts."""
    if not raw or raw.strip().lower() == "none":
        return []
    result = []
    for entry in raw.split(";"):
        parts = entry.strip().split(":", 1)
        if len(parts) == 2:
            result.append({"key": parts[0].strip(), "value": parts[1].strip()})
    return result


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


def _build_haproxy(row: dict[str, str]) -> dict:
    """Enrich haproxy context — parse backend servers."""
    return {
        "backend_servers": parse_semicolon_list(row.get("backend_servers", "")),
    }


def _build_prometheus(row: dict[str, str]) -> dict:
    """Enrich prometheus context — parse scrape targets."""
    return {
        "scrape_targets": parse_semicolon_list(row.get("scrape_targets", "")),
    }


def _build_nginx_site(row: dict[str, str]) -> dict:
    """Enrich nginx site context."""
    return {
        "extra_headers": row.get("extra_headers", ""),
    }


def _build_dns_zone(row: dict[str, str]) -> dict:
    """Enrich DNS zone context — parse records."""
    return {
        "ns_records": parse_semicolon_list(row.get("ns_records", "")),
        "a_records": parse_semicolon_list(row.get("a_records", "")),
        "cname_records": parse_semicolon_list(row.get("cname_records", "")),
    }


def _build_edge_compute(row: dict[str, str]) -> dict:
    """Enrich edge compute context — parse modules and routing."""
    return {
        "modules": parse_semicolon_list(row.get("modules", "")),
        "routing_rules": parse_semicolon_list(row.get("routing_rules", "")),
    }


def _build_pop_metadata(row: dict[str, str]) -> dict:
    """Enrich pop metadata context."""
    return {
        "peering_exchanges": row.get("peering_exchanges", ""),
    }


CONTEXT_BUILDERS: dict[str, callable] = {
    "haproxy": _build_haproxy,
    "prometheus": _build_prometheus,
    "nginx-site": _build_nginx_site,
    "dns-zone": _build_dns_zone,
    "edge-compute": _build_edge_compute,
    "pop-metadata": _build_pop_metadata,
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


def validate_ini(rendered: str, filename: str) -> None:
    """Validate rendered INI/conf is not empty."""
    if not rendered.strip():
        print(f"ERROR: Empty output for {filename}", file=sys.stderr)
        sys.exit(1)


VALIDATORS = {
    "yaml": validate_yaml,
    "json": validate_json,
    "ini": validate_ini,
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
            elif fmt == "ini":
                validate_ini(rendered, filename)
            output_file.write_text(rendered)
        count += 1

    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate CDN edge PoP test fixtures")
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
