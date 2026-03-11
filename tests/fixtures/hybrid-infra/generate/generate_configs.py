#!/usr/bin/env python3
"""Generate hybrid infrastructure test fixtures from CSV inputs + Jinja2 templates.

Produces ~100 mixed-format files (YAML + JSON + INI) spanning 8+ platform types
across all three supported input formats. Represents a realistic SaaS deployment
("Ridgeline Data") with intentional inconsistencies and embedded secrets.

Requires: pip install jinja2  (NOT a project dependency)

Usage:
    python generate_configs.py                              # Generate all ~100 configs
    python generate_configs.py --config-type postgresql      # Generate one type only
    python generate_configs.py --dry-run                     # Show what would be generated
    python generate_configs.py --output-dir /tmp             # Custom output directory
"""

from __future__ import annotations

import argparse
import configparser
import csv
import json
import re
import sys
from collections import defaultdict
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
# Each entry: (csv_name, template_name, output_format, output_ext, grouped_by)
# grouped_by: if set, multiple CSV rows produce one output file grouped by that column

CONFIG_TYPES: dict[str, dict] = {
    # INI types
    "postgresql": {"format": "ini", "ext": ".conf", "schema": "postgresql"},
    "mariadb": {"format": "ini", "ext": ".cnf", "schema": "mariadb-mysql"},
    "sshd": {"format": "ini", "ext": ".conf", "schema": "sshd-config"},
    "systemd": {"format": "ini", "ext": ".conf", "schema": None},
    "sysctl": {"format": "ini", "ext": ".conf", "schema": None},
    # YAML types
    "docker-compose": {"format": "yaml", "ext": ".yaml", "schema": "docker-compose", "grouped_by": "compose_file"},
    "ansible-playbook": {"format": "yaml", "ext": ".yaml", "schema": "ansible-playbook"},
    "ansible-inventory": {"format": "yaml", "ext": ".yaml", "schema": None},
    "ansible-vars": {"format": "yaml", "ext": ".yaml", "schema": None},
    "cloud-init": {"format": "yaml", "ext": ".yaml", "schema": "cloud-init"},
    "traefik": {"format": "yaml", "ext": ".yaml", "schema": "traefik"},
    "prometheus": {"format": "yaml", "ext": ".yaml", "schema": "prometheus"},
    "yaml-app-config": {"format": "yaml", "ext": ".yaml", "schema": None},
    # JSON types
    "tfvars": {"format": "json", "ext": ".json", "schema": None},
    "package-json": {"format": "json", "ext": ".json", "schema": None},
    "docker-daemon": {"format": "json", "ext": ".json", "schema": None},
    "app-config-json": {"format": "json", "ext": ".json", "schema": None},
}

ALL_CONFIG_TYPES = list(CONFIG_TYPES.keys())


# ── Helpers ────────────────────────────────────────────────────────────────────


def slugify(name: str) -> str:
    """Convert a name to a filesystem-safe slug."""
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def parse_string(raw: str | None, default: str = "") -> str:
    """Parse string, treating 'none' as empty."""
    if not raw or raw.strip().lower() == "none":
        return default
    return raw.strip()


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
    # Strip whitespace from all values
    for k, v in ctx.items():
        if isinstance(v, str):
            ctx[k] = v.strip()

    # Remove None keys (from trailing CSV commas)
    ctx = {k: v for k, v in ctx.items() if k is not None}

    # Parse semicolon lists for known compound fields
    for key in list(ctx.keys()):
        if key.endswith("_list") or key == "tasks" or key == "packages":
            ctx[key] = parse_semicolon_list(ctx[key])
        elif key.endswith("_bool"):
            ctx[key] = parse_bool(ctx[key])

    # Type-specific context enrichment
    builder = CONTEXT_BUILDERS.get(config_type)
    if builder:
        ctx.update(builder(row))

    return ctx


def _build_docker_compose(row: dict[str, str]) -> dict:
    """Enrich docker-compose context — parse env vars, ports, volumes."""
    return {
        "env_vars": parse_key_value_pairs(row.get("env_vars", "")),
        "ports": parse_semicolon_list(row.get("ports", "")),
        "volumes": parse_semicolon_list(row.get("volumes", "")),
        "depends_on": parse_semicolon_list(row.get("depends_on", "")),
        "labels": parse_key_value_pairs(row.get("labels", "")),
        "networks": parse_semicolon_list(row.get("networks", "")),
    }


def _build_ansible_playbook(row: dict[str, str]) -> dict:
    """Enrich ansible-playbook context — parse task list for section includes."""
    return {
        "tasks": parse_semicolon_list(row.get("tasks", "")),
        "vars_list": parse_key_value_pairs(row.get("vars", "")),
        "handlers": parse_semicolon_list(row.get("handlers", "")),
    }


def _build_cloud_init(row: dict[str, str]) -> dict:
    """Enrich cloud-init context."""
    return {
        "packages": parse_semicolon_list(row.get("packages", "")),
        "users": parse_semicolon_list(row.get("users", "")),
        "write_files": parse_key_value_pairs(row.get("write_files", "")),
        "runcmd": parse_semicolon_list(row.get("runcmd", "")),
        "ntp_servers": parse_semicolon_list(row.get("ntp_servers", "")),
    }


def _build_prometheus(row: dict[str, str]) -> dict:
    """Enrich prometheus context — parse scrape targets."""
    return {
        "scrape_targets": parse_key_value_pairs(row.get("scrape_targets", "")),
        "rule_files": parse_semicolon_list(row.get("rule_files", "")),
        "alertmanagers": parse_semicolon_list(row.get("alertmanagers", "")),
    }


def _build_traefik(row: dict[str, str]) -> dict:
    """Enrich traefik context — keep raw strings for template-side splitting."""
    return {}


def _build_package_json(row: dict[str, str]) -> dict:
    """Enrich package.json context."""
    return {
        "dependencies": parse_key_value_pairs(row.get("dependencies", "")),
        "dev_dependencies": parse_key_value_pairs(row.get("dev_dependencies", "")),
        "scripts": parse_key_value_pairs(row.get("scripts", "")),
    }


CONTEXT_BUILDERS: dict[str, callable] = {
    "docker-compose": _build_docker_compose,
    "ansible-playbook": _build_ansible_playbook,
    "cloud-init": _build_cloud_init,
    "prometheus": _build_prometheus,
    "traefik": _build_traefik,
    "package-json": _build_package_json,
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
    """Validate rendered INI is parseable (sectioned or flat key=value)."""
    if re.search(r"^\[.+\]", rendered, re.MULTILINE):
        # Use RawConfigParser with STRICT=False to allow duplicate keys (systemd units)
        parser = configparser.RawConfigParser(strict=False)
        parser.read_string(rendered)
    else:
        # Flat key=value — just check lines are parseable
        for i, line in enumerate(rendered.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith(";"):
                continue
            if "=" not in stripped and " " not in stripped:
                print(f"WARNING: {filename}:{i}: line doesn't look like key=value: {stripped}", file=sys.stderr)


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
    grouped_by = type_info.get("grouped_by")
    template = env.get_template(f"{config_type}.j2")

    count = 0

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if grouped_by:
        # Group rows by the grouping column (e.g., compose_file)
        groups: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            key = row[grouped_by].strip()
            groups[key].append(build_context(row, config_type))

        for group_name, contexts in groups.items():
            filename = f"{group_name}{ext}"
            output_file = output_dir / filename

            if dry_run:
                print(f"  Would generate: {output_file} ({len(contexts)} services)")
            else:
                rendered = template.render(services=contexts, group_name=group_name)
                if fmt == "yaml":
                    validate_yaml(rendered, filename)
                elif fmt == "json":
                    rendered = validate_json(rendered, filename)
                elif fmt == "ini":
                    validate_ini(rendered, filename)
                output_file.write_text(rendered)
            count += 1
    else:
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
    parser = argparse.ArgumentParser(description="Generate hybrid infrastructure test fixtures")
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
