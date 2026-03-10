#!/usr/bin/env python3
"""Generate IOS-XR test fixture configs from CSV inputs + Jinja2 templates.

Requires: pip install jinja2  (NOT a project dependency)

Usage:
    python generate_configs.py                    # Generate all 86 configs
    python generate_configs.py --role p           # Generate P routers only
    python generate_configs.py --dry-run          # Show what would be generated
    python generate_configs.py --output-dir /tmp  # Custom output directory
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    print("ERROR: jinja2 is required. Install with: pip install jinja2", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
TEMPLATES_DIR = SCRIPT_DIR / "templates"
INPUTS_DIR = SCRIPT_DIR / "inputs"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR.parent / "configs"

ROLES = ["p", "rr", "access-pe", "bng", "services-pe"]

# Confederation peer AS numbers (all sub-AS values except the device's own)
ALL_SUB_AS = {65001, 65002, 65003, 65004, 65005, 65006}


def parse_p2p_interfaces(raw: str) -> list[dict[str, str]]:
    """Parse compound p2p_interfaces field: 'intf:ip:remote;...' -> list of dicts."""
    interfaces = []
    for entry in raw.split(";"):
        parts = entry.strip().split(":")
        if len(parts) == 3:
            interfaces.append({"name": parts[0], "ip": parts[1], "remote": parts[2]})
    return interfaces


def parse_bridge_domains(raw: str) -> list[dict[str, str]]:
    """Parse bridge domains: 'name:vlan;...' -> list of dicts."""
    domains = []
    for entry in raw.split(";"):
        parts = entry.strip().split(":")
        if len(parts) == 2:
            domains.append({"name": parts[0], "vlan": parts[1]})
    return domains


def parse_rr_client_groups(raw: str) -> list[dict[str, str | list[str]]]:
    """Parse RR client groups: 'GROUP:peer1|peer2;...' -> list of dicts."""
    groups = []
    for entry in raw.split(";"):
        parts = entry.strip().split(":")
        if len(parts) == 2:
            groups.append({"name": parts[0], "peers": parts[1].split("|")})
    return groups


def parse_ebgp_peers(raw: str) -> list[dict[str, str]]:
    """Parse eBGP peers: 'ip:asn:description;...' -> list of dicts."""
    peers = []
    for entry in raw.split(";"):
        parts = entry.strip().split(":")
        if len(parts) == 3:
            peers.append({"ip": parts[0], "remote_as": parts[1], "description": parts[2]})
    return peers


def parse_l3vpn_vrfs(raw: str) -> list[dict[str, str]]:
    """Parse L3VPN VRFs: 'name:rd:network;...' -> list of dicts."""
    vrfs = []
    for entry in raw.split(";"):
        parts = entry.strip().split(":")
        if len(parts) == 3:
            vrfs.append({"name": parts[0], "rd": parts[1], "network": parts[2]})
    return vrfs


def build_context(row: dict[str, str], role: str) -> dict:
    """Build Jinja2 template context from a CSV row."""
    ctx: dict = dict(row)
    ctx["p2p_interfaces"] = parse_p2p_interfaces(row["p2p_interfaces"])

    # Confederation peers: all sub-AS values except this device's own
    own_as = int(row["sub_as"])
    ctx["confederation_peers"] = sorted(ALL_SUB_AS - {own_as})

    if role == "access-pe":
        ctx["evpn_vni_base"] = int(row["evpn_vni_base"])
        ctx["evpn_instance_count"] = int(row["evpn_instance_count"])
        ctx["bridge_domains"] = parse_bridge_domains(row["l2vpn_bridge_domains"])
        # BGP neighbors: RR peers
        rr_ips = row["bgp_rr_neighbors"].split(";")
        ctx["bgp_neighbors"] = [
            {"ip": ip, "remote_as": row["sub_as"], "description": f"RR-{i + 1}", "rr_client": False}
            for i, ip in enumerate(rr_ips)
        ]
        ctx["bgp_address_families"] = ["vpnv4-unicast", "l2vpn-evpn"]

    elif role == "rr":
        ctx["rr_cluster_id"] = row["rr_cluster_id"]
        ctx["bgp_address_families"] = row["rr_address_families"].split(";")
        # Build BGP neighbors from RR client groups
        neighbors = []
        # Add peer RR connections
        for intf in ctx["p2p_interfaces"]:
            if intf["remote"].startswith("RR-"):
                neighbors.append({
                    "ip": intf["ip"].split("/")[0],
                    "remote_as": row["sub_as"],
                    "description": intf["remote"],
                    "rr_client": False,
                })
        # RR client groups reference hostnames - we use loopback IPs as placeholders
        client_groups = parse_rr_client_groups(row["rr_client_groups"])
        base_ip_counter = 1
        for group in client_groups:
            for peer_name in group["peers"]:
                neighbors.append({
                    "ip": f"10.0.10.{base_ip_counter}",
                    "remote_as": row["sub_as"],
                    "description": f"{group['name']}-{peer_name}",
                    "rr_client": True,
                })
                base_ip_counter += 1
        ctx["bgp_neighbors"] = neighbors

    elif role == "p":
        ctx["isis_overload_timeout"] = row.get("isis_overload_timeout", "")
        ctx["mpls_te_enabled"] = row.get("mpls_te_enabled", "").lower() == "true"
        # P routers: minimal BGP (iBGP to RRs only)
        ctx["bgp_neighbors"] = []

    elif role == "bng":
        ctx["subscriber_pool_name"] = row["subscriber_pool_name"]
        ctx["subscriber_pool_network"] = row["subscriber_pool_network"]
        ctx["pppoe_bba_group"] = row["pppoe_bba_group"]
        ctx["radius_server"] = row["radius_server"]
        ctx["radius_key"] = row["radius_key"]
        ctx["policy_map_name"] = row["policy_map_name"]
        ctx["dynamic_template"] = row["dynamic_template"]
        ctx["bgp_neighbors"] = []

    elif role == "services-pe":
        ctx["ebgp_peers"] = parse_ebgp_peers(row["ebgp_peers"])
        ctx["l3vpn_vrfs"] = parse_l3vpn_vrfs(row["l3vpn_vrfs"])
        ctx["peering_policy"] = row["peering_policy"]
        ctx["bgp_neighbors"] = []

    return ctx


def generate(role: str, env: Environment, output_dir: Path, dry_run: bool) -> int:
    """Generate configs for a single role. Returns count of files generated."""
    csv_path = INPUTS_DIR / f"{role}.csv"
    if not csv_path.exists():
        print(f"WARNING: {csv_path} not found, skipping", file=sys.stderr)
        return 0

    template = env.get_template(f"{role}.j2")

    count = 0
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            hostname = row["hostname"]
            ctx = build_context(row, role)
            output_file = output_dir / f"{hostname}.cfg"

            if dry_run:
                print(f"  Would generate: {output_file}")
            else:
                rendered = template.render(**ctx)
                output_file.write_text(rendered)
            count += 1

    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate IOS-XR test fixture configs")
    parser.add_argument("--role", choices=ROLES, help="Generate configs for a specific role only")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be generated without writing files")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory for .cfg files")
    args = parser.parse_args()

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )

    if not args.dry_run:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    roles = [args.role] if args.role else ROLES
    total = 0

    for role in roles:
        print(f"Generating {role} configs...")
        count = generate(role, env, args.output_dir, args.dry_run)
        print(f"  {count} configs {'would be ' if args.dry_run else ''}generated")
        total += count

    print(f"\nTotal: {total} configs {'would be ' if args.dry_run else ''}generated in {args.output_dir}")


if __name__ == "__main__":
    main()
