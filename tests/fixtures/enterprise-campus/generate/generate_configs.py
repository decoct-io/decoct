#!/usr/bin/env python3
"""Generate enterprise campus test fixtures from CSV inputs + Jinja2 templates.

Produces ~185 mixed-format files (YAML + JSON + INI-like conf) spanning 33 config types
across 5 domains (SD-WAN, SD-Access, Firewalls, Datacentre, IoT Factory Floor).
Represents a Fortune 500 industrial conglomerate ("Meridian Manufacturing") with
HQ campus + 2 branch offices + 1 datacentre + 1 factory floor.

Requires: pip install jinja2  (NOT a project dependency)

Usage:
    python generate_configs.py                              # Generate all ~185 configs
    python generate_configs.py --config-type arista-leaf     # Generate one type only
    python generate_configs.py --dry-run                     # Show what would be generated
    python generate_configs.py --output-dir /tmp             # Custom output directory
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
    # ── SD-WAN (YAML + JSON) ──────────────────────────────────────────────────
    "sdwan-cedge": {"format": "yaml", "ext": ".yaml", "schema": None},
    "sdwan-vsmart": {"format": "yaml", "ext": ".yaml", "schema": None},
    "sdwan-vbond": {"format": "yaml", "ext": ".yaml", "schema": None},
    "sdwan-policy": {"format": "json", "ext": ".json", "schema": None},
    "sdwan-template": {"format": "json", "ext": ".json", "schema": None},
    # ── SD-Access (YAML + JSON) ───────────────────────────────────────────────
    "catalyst-switch": {"format": "yaml", "ext": ".yaml", "schema": None},
    "wlc-config": {"format": "json", "ext": ".json", "schema": None},
    "ap-group": {"format": "json", "ext": ".json", "schema": None},
    "ise-policy": {"format": "json", "ext": ".json", "schema": None},
    "sgt-matrix": {"format": "yaml", "ext": ".yaml", "schema": None},
    "dnac-template": {"format": "json", "ext": ".json", "schema": None},
    # ── Firewalls (YAML + JSON) ───────────────────────────────────────────────
    "paloalto-fw": {"format": "yaml", "ext": ".yaml", "schema": None},
    "paloalto-profile": {"format": "json", "ext": ".json", "schema": None},
    "fortinet-fw": {"format": "yaml", "ext": ".yaml", "schema": None},
    "fw-address-group": {"format": "json", "ext": ".json", "schema": None},
    "fw-nat-rule": {"format": "json", "ext": ".json", "schema": None},
    # ── Datacentre (YAML + JSON + INI) ────────────────────────────────────────
    "arista-leaf": {"format": "yaml", "ext": ".yaml", "schema": None},
    "arista-spine": {"format": "yaml", "ext": ".yaml", "schema": None},
    "server-bmc": {"format": "json", "ext": ".json", "schema": None},
    "server-netplan": {"format": "yaml", "ext": ".yaml", "schema": None},
    "server-sysctl": {"format": "ini", "ext": ".conf", "schema": None},
    "server-systemd": {"format": "ini", "ext": ".conf", "schema": None},
    "storage-array": {"format": "json", "ext": ".json", "schema": None},
    "db-config": {"format": "ini", "ext": ".conf", "schema": None},
    "redis-config": {"format": "ini", "ext": ".conf", "schema": None},
    "lb-config": {"format": "yaml", "ext": ".yaml", "schema": None},
    # ── IoT Factory Floor (YAML + JSON) ───────────────────────────────────────
    "mqtt-broker": {"format": "json", "ext": ".json", "schema": None},
    "opcua-server": {"format": "yaml", "ext": ".yaml", "schema": None},
    "plc-gateway": {"format": "json", "ext": ".json", "schema": None},
    "edge-compute": {"format": "yaml", "ext": ".yaml", "schema": None},
    "sensor-network": {"format": "yaml", "ext": ".yaml", "schema": None},
    "industrial-fw": {"format": "yaml", "ext": ".yaml", "schema": None},
    "historian-config": {"format": "json", "ext": ".json", "schema": None},
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


def _build_sdwan_cedge(row: dict[str, str]) -> dict:
    """Enrich SD-WAN cEdge context."""
    return {
        "tlocs": parse_semicolon_list(row.get("tlocs", "")),
        "vpns": parse_semicolon_list(row.get("vpns", "")),
    }


def _build_catalyst_switch(row: dict[str, str]) -> dict:
    """Enrich catalyst switch context."""
    return {
        "vlans": parse_semicolon_list(row.get("vlans", "")),
        "interfaces": parse_semicolon_list(row.get("interfaces", "")),
    }


def _build_paloalto_fw(row: dict[str, str]) -> dict:
    """Enrich Palo Alto firewall context."""
    return {
        "zones": parse_semicolon_list(row.get("zones", "")),
        "rules": parse_semicolon_list(row.get("rules", "")),
        "nat_rules": parse_semicolon_list(row.get("nat_rules", "")),
    }


def _build_fortinet_fw(row: dict[str, str]) -> dict:
    """Enrich FortiGate firewall context."""
    return {
        "policies": parse_semicolon_list(row.get("policies", "")),
        "vpn_tunnels": parse_semicolon_list(row.get("vpn_tunnels", "")),
    }


def _build_arista_leaf(row: dict[str, str]) -> dict:
    """Enrich Arista leaf switch context."""
    return {
        "vlans": parse_semicolon_list(row.get("vlans", "")),
        "port_channels": parse_semicolon_list(row.get("port_channels", "")),
    }


def _build_server_netplan(row: dict[str, str]) -> dict:
    """Enrich netplan context."""
    return {
        "bonds": parse_semicolon_list(row.get("bonds", "")),
        "vlans": parse_semicolon_list(row.get("vlans", "")),
    }


def _build_opcua_server(row: dict[str, str]) -> dict:
    """Enrich OPC-UA server context."""
    return {
        "nodes": parse_semicolon_list(row.get("nodes", "")),
    }


def _build_plc_gateway(row: dict[str, str]) -> dict:
    """Enrich PLC gateway context."""
    return {
        "registers": parse_semicolon_list(row.get("registers", "")),
        "mqtt_topics": parse_semicolon_list(row.get("mqtt_topics", "")),
    }


def _build_sensor_network(row: dict[str, str]) -> dict:
    """Enrich sensor network context."""
    return {
        "sensors": parse_semicolon_list(row.get("sensors", "")),
    }


def _build_edge_compute(row: dict[str, str]) -> dict:
    """Enrich edge compute context."""
    return {
        "models": parse_semicolon_list(row.get("models", "")),
    }


def _build_industrial_fw(row: dict[str, str]) -> dict:
    """Enrich industrial firewall context."""
    return {
        "rules": parse_semicolon_list(row.get("rules", "")),
    }


CONTEXT_BUILDERS: dict[str, callable] = {
    "sdwan-cedge": _build_sdwan_cedge,
    "catalyst-switch": _build_catalyst_switch,
    "paloalto-fw": _build_paloalto_fw,
    "fortinet-fw": _build_fortinet_fw,
    "arista-leaf": _build_arista_leaf,
    "server-netplan": _build_server_netplan,
    "opcua-server": _build_opcua_server,
    "plc-gateway": _build_plc_gateway,
    "sensor-network": _build_sensor_network,
    "edge-compute": _build_edge_compute,
    "industrial-fw": _build_industrial_fw,
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
    parser = argparse.ArgumentParser(description="Generate enterprise campus test fixtures")
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
