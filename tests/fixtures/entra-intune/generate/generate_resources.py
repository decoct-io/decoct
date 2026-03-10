#!/usr/bin/env python3
"""Generate Entra ID + Intune test fixture JSON from CSV inputs + Jinja2 templates.

Requires: pip install jinja2  (NOT a project dependency)

Usage:
    python generate_resources.py                              # Generate all 88 resources
    python generate_resources.py --resource-type group        # Generate groups only
    python generate_resources.py --dry-run                    # Show what would be generated
    python generate_resources.py --output-dir /tmp            # Custom output directory
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import uuid
from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    print("ERROR: jinja2 is required. Install with: pip install jinja2", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
TEMPLATES_DIR = SCRIPT_DIR / "templates"
INPUTS_DIR = SCRIPT_DIR / "inputs"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR.parent / "resources"

RESOURCE_TYPES = [
    "conditional-access",
    "app-registration",
    "group",
    "compliance-policy",
    "device-config",
    "app-protection",
    "named-location",
    "cross-tenant-access",
]

# Type prefix for output filenames
PREFIX_MAP = {
    "conditional-access": "ca",
    "app-registration": "app",
    "group": "grp",
    "compliance-policy": "compliance",
    "device-config": "devconfig",
    "app-protection": "appprotect",
    "named-location": "namedloc",
    "cross-tenant-access": "cta",
}

# Deterministic namespace for UUID generation
NAMESPACE = uuid.NAMESPACE_DNS

# Fixed timestamps for deterministic output
CREATED_DATE = "2024-06-15T10:30:00Z"
MODIFIED_DATE = "2024-11-20T14:45:00Z"


# ── Helpers ────────────────────────────────────────────────────────────────────


def deterministic_uuid(name: str) -> str:
    """Generate a deterministic UUID v5 from a display name."""
    return str(uuid.uuid5(NAMESPACE, name))


def slugify(name: str) -> str:
    """Convert display name to filesystem-safe slug."""
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


def parse_key_value_list(raw: str) -> list[dict[str, str]]:
    """Parse 'key:value;...' into list of dicts."""
    if not raw or raw.strip().lower() == "none":
        return []
    result = []
    for entry in raw.split(";"):
        parts = entry.strip().split(":", 1)
        if len(parts) == 2:
            result.append({"key": parts[0].strip(), "value": parts[1].strip()})
    return result


def parse_assignments(raw: str) -> list[dict[str, str]]:
    """Parse 'target_type:target_id;...' into assignment list."""
    if not raw or raw.strip().lower() == "none":
        return []
    result = []
    for entry in raw.split(";"):
        parts = entry.strip().split(":", 1)
        if len(parts) == 2:
            result.append({"target": parts[0].strip(), "groupId": deterministic_uuid(parts[1].strip())})
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


def build_context(row: dict[str, str], resource_type: str) -> dict:
    """Build Jinja2 template context from a CSV row."""
    display_name = row["display_name"].strip()
    ctx: dict = {
        "display_name": display_name,
        "id": deterministic_uuid(display_name),
        "created_date": CREATED_DATE,
        "modified_date": MODIFIED_DATE,
    }

    builder = {
        "conditional-access": _build_conditional_access,
        "app-registration": _build_app_registration,
        "group": _build_group,
        "compliance-policy": _build_compliance_policy,
        "device-config": _build_device_config,
        "app-protection": _build_app_protection,
        "named-location": _build_named_location,
        "cross-tenant-access": _build_cross_tenant_access,
    }
    ctx.update(builder[resource_type](row))
    return ctx


def _build_conditional_access(row: dict[str, str]) -> dict:
    return {
        "state": row["state"].strip(),
        "include_users": parse_semicolon_list(row["include_users"]),
        "exclude_users": parse_semicolon_list(row["exclude_users"]),
        "include_groups": parse_semicolon_list(row["include_groups"]),
        "exclude_groups": parse_semicolon_list(row["exclude_groups"]),
        "include_applications": parse_semicolon_list(row["include_applications"]),
        "exclude_applications": parse_semicolon_list(row["exclude_applications"]),
        "include_platforms": parse_semicolon_list(row["include_platforms"]),
        "include_locations": parse_semicolon_list(row["include_locations"]),
        "client_app_types": parse_semicolon_list(row["client_app_types"]),
        "grant_operator": row["grant_operator"].strip() or "OR",
        "grant_controls": parse_semicolon_list(row["grant_controls"]),
        "session_sign_in_frequency": row.get("session_sign_in_frequency", "").strip(),
        "session_persistent_browser": row.get("session_persistent_browser", "").strip(),
        "disable_resilience_defaults": parse_bool(row.get("disable_resilience_defaults", "false")),
        "user_risk_levels": parse_semicolon_list(row.get("user_risk_levels", "")),
        "sign_in_risk_levels": parse_semicolon_list(row.get("sign_in_risk_levels", "")),
        "client_secret": row.get("client_secret", "").strip(),
    }


def _build_app_registration(row: dict[str, str]) -> dict:
    display_name = row["display_name"].strip()
    return {
        "app_id": deterministic_uuid(display_name + "-appid"),
        "publisher_domain": "contoso.com",
        "sign_in_audience": row.get("sign_in_audience", "AzureADMyOrg").strip(),
        "is_fallback_public_client": parse_bool(row.get("is_fallback_public_client", "false")),
        "is_device_only_auth_supported": parse_bool(row.get("is_device_only_auth_supported", "false")),
        "oauth2_required_post_response": False,
        "web_redirect_uris": parse_semicolon_list(row.get("web_redirect_uris", "")),
        "spa_redirect_uris": parse_semicolon_list(row.get("spa_redirect_uris", "")),
        "api_scopes": parse_semicolon_list(row.get("api_scopes", "")),
        "required_resource_access": parse_key_value_list(row.get("required_resource_access", "")),
        "identifier_uris": parse_semicolon_list(row.get("identifier_uris", "")),
        "key_credentials": parse_string(row.get("key_credentials", "")),
        "password_credentials": parse_string(row.get("password_credentials", "")),
        "optional_claims": parse_string(row.get("optional_claims", "")),
    }


def _build_group(row: dict[str, str]) -> dict:
    return {
        "description": row.get("description", "").strip(),
        "mail_enabled": parse_bool(row.get("mail_enabled", "false")),
        "mail_nickname": row.get("mail_nickname", "").strip(),
        "security_enabled": parse_bool(row.get("security_enabled", "true")),
        "group_types": parse_semicolon_list(row.get("group_types", "")),
        "membership_rule": parse_string(row.get("membership_rule", "")),
        "membership_rule_processing_state": "On" if parse_string(row.get("membership_rule", "")) else "Paused",
        "allow_external_senders": parse_bool(row.get("allow_external_senders", "false")),
        "auto_subscribe_new_members": parse_bool(row.get("auto_subscribe_new_members", "false")),
        "hide_from_address_lists": parse_bool(row.get("hide_from_address_lists", "false")),
        "hide_from_outlook_clients": parse_bool(row.get("hide_from_outlook_clients", "false")),
        "is_assignable_to_role": parse_bool(row.get("is_assignable_to_role", "false")),
        "is_subscribed_by_mail": True,  # Always true (schema default)
    }


def _build_compliance_policy(row: dict[str, str]) -> dict:
    platform = row["platform"].strip().lower()
    return {
        "platform": platform,
        "description": row.get("description", "").strip(),
        "password_required": parse_bool(row.get("password_required", "false")),
        "password_block_simple": parse_bool(row.get("password_block_simple", "false")),
        "password_min_length": parse_int(row.get("password_min_length", "0")),
        "password_required_type": row.get("password_required_type", "deviceDefault").strip(),
        "security_block_jailbroken": parse_bool(row.get("security_block_jailbroken", "false")),
        "device_threat_protection_enabled": parse_bool(row.get("device_threat_protection_enabled", "false")),
        "device_threat_protection_level": row.get("device_threat_protection_level", "unavailable").strip(),
        "storage_require_encryption": parse_bool(row.get("storage_require_encryption", "false")),
        "bitlocker_enabled": parse_bool(row.get("bitlocker_enabled", "false")),
        "secure_boot_enabled": parse_bool(row.get("secure_boot_enabled", "false")),
        "code_integrity_enabled": parse_bool(row.get("code_integrity_enabled", "false")),
        "firewall_enabled": parse_bool(row.get("firewall_enabled", "false")),
        "firewall_block_all_incoming": parse_bool(row.get("firewall_block_all_incoming", "false")),
        "system_integrity_protection": parse_bool(row.get("system_integrity_protection", "false")),
        "scheduled_actions": row.get("scheduled_actions", "").strip(),
        "assignments": parse_assignments(row.get("assignments", "")),
    }


def _build_device_config(row: dict[str, str]) -> dict:
    platform = row["platform"].strip().lower()
    return {
        "platform": platform,
        "description": row.get("description", "").strip(),
        "camera_blocked": parse_bool(row.get("camera_blocked", "false")),
        "screen_capture_blocked": parse_bool(row.get("screen_capture_blocked", "false")),
        "bluetooth_blocked": parse_bool(row.get("bluetooth_blocked", "false")),
        "nfc_blocked": parse_bool(row.get("nfc_blocked", "false")),
        "wifi_blocked": parse_bool(row.get("wifi_blocked", "false")),
        "location_services_blocked": parse_bool(row.get("location_services_blocked", "false")),
        "factory_reset_blocked": parse_bool(row.get("factory_reset_blocked", "false")),
        "password_required": parse_bool(row.get("password_required", "false")),
        "password_required_type": row.get("password_required_type", "deviceDefault").strip(),
        "password_min_length": parse_int(row.get("password_min_length", "0")),
        "web_browser_cookie_settings": row.get("web_browser_cookie_settings", "browserDefault").strip(),
        "storage_require_device_encryption": parse_bool(row.get("storage_require_device_encryption", "false")),
        "compliant_app_list_type": row.get("compliant_app_list_type", "none").strip(),
        "wifi_psk": parse_string(row.get("wifi_psk", "")),
        "assignments": parse_assignments(row.get("assignments", "")),
    }


def _build_app_protection(row: dict[str, str]) -> dict:
    platform = row["platform"].strip().lower()
    return {
        "platform": platform,
        "description": row.get("description", "").strip(),
        "pin_required": parse_bool(row.get("pin_required", "true")),
        "minimum_pin_length": parse_int(row.get("minimum_pin_length", "4")),
        "simple_pin_blocked": parse_bool(row.get("simple_pin_blocked", "false")),
        "fingerprint_blocked": parse_bool(row.get("fingerprint_blocked", "false")),
        "data_backup_blocked": parse_bool(row.get("data_backup_blocked", "false")),
        "contact_sync_blocked": parse_bool(row.get("contact_sync_blocked", "false")),
        "print_blocked": parse_bool(row.get("print_blocked", "false")),
        "save_as_blocked": parse_bool(row.get("save_as_blocked", "false")),
        "device_compliance_required": parse_bool(row.get("device_compliance_required", "true")),
        "managed_browser_required": parse_bool(row.get("managed_browser_required", "false")),
        "period_offline_before_wipe": row.get("period_offline_before_wipe", "P90D").strip(),
        "period_offline_before_access_check": row.get("period_offline_before_access_check", "PT720M").strip(),
        "period_online_before_access_check": row.get("period_online_before_access_check", "PT30M").strip(),
        "apps": parse_semicolon_list(row.get("apps", "")),
        "assignments": parse_assignments(row.get("assignments", "")),
    }


def _build_named_location(row: dict[str, str]) -> dict:
    location_type = row["location_type"].strip().lower()
    return {
        "location_type": location_type,
        "is_trusted": parse_bool(row.get("is_trusted", "false")),
        "ip_ranges": parse_semicolon_list(row.get("ip_ranges", "")),
        "countries_and_regions": parse_semicolon_list(row.get("countries_and_regions", "")),
        "include_unknown_countries": parse_bool(row.get("include_unknown_countries", "false")),
    }


def _build_cross_tenant_access(row: dict[str, str]) -> dict:
    return {
        "tenant_id": row.get("tenant_id", "").strip(),
        "is_service_default": parse_bool(row.get("is_service_default", "false")),
        "b2b_collab_inbound_access_type": row.get("b2b_collab_inbound_access_type", "allowed").strip(),
        "b2b_collab_outbound_access_type": row.get("b2b_collab_outbound_access_type", "allowed").strip(),
        "b2b_direct_inbound_access_type": row.get("b2b_direct_inbound_access_type", "blocked").strip(),
        "b2b_direct_outbound_access_type": row.get("b2b_direct_outbound_access_type", "blocked").strip(),
        "inbound_trust_mfa": parse_bool(row.get("inbound_trust_mfa", "false")),
        "inbound_trust_compliant_device": parse_bool(row.get("inbound_trust_compliant_device", "false")),
        "inbound_trust_hybrid_joined": parse_bool(row.get("inbound_trust_hybrid_joined", "false")),
    }


# ── Generation ─────────────────────────────────────────────────────────────────


def generate(resource_type: str, env: Environment, output_dir: Path, dry_run: bool) -> int:
    """Generate resources for a single type. Returns count of files generated."""
    csv_path = INPUTS_DIR / f"{resource_type}.csv"
    if not csv_path.exists():
        print(f"WARNING: {csv_path} not found, skipping", file=sys.stderr)
        return 0

    template = env.get_template(f"{resource_type}.j2")

    count = 0
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ctx = build_context(row, resource_type)
            slug = slugify(ctx["display_name"])
            prefix = PREFIX_MAP.get(resource_type, resource_type)
            filename = f"{prefix}-{slug}.json"
            output_file = output_dir / filename

            if dry_run:
                print(f"  Would generate: {output_file}")
            else:
                rendered = template.render(**ctx)
                # Validate and reformat JSON
                try:
                    parsed = json.loads(rendered)
                except json.JSONDecodeError as e:
                    print(f"ERROR: Invalid JSON for {filename}: {e}", file=sys.stderr)
                    print(f"  Rendered output:\n{rendered[:500]}", file=sys.stderr)
                    sys.exit(1)
                output_file.write_text(json.dumps(parsed, indent=2) + "\n")
            count += 1

    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Entra ID + Intune test fixture JSON")
    parser.add_argument(
        "--resource-type",
        choices=RESOURCE_TYPES,
        help="Generate resources for a specific type only",
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
        help="Output directory for .json files",
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

    types = [args.resource_type] if args.resource_type else RESOURCE_TYPES
    total = 0

    for rt in types:
        print(f"Generating {rt} resources...")
        count = generate(rt, env, args.output_dir, args.dry_run)
        print(f"  {count} resources {'would be ' if args.dry_run else ''}generated")
        total += count

    print(f"\nTotal: {total} resources {'would be ' if args.dry_run else ''}generated in {args.output_dir}")


if __name__ == "__main__":
    main()
