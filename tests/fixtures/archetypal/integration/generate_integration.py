#!/usr/bin/env python3
"""
Generate Level 2 integration test fixture for decoct.

Produces one combined file per router (10 routers, up to 15 sections each),
a single golden tier_b.yaml with all classes, per-host golden tier_c files,
and expected.yaml with scoring metadata.

Usage:
    cd tests/fixtures/archetypal
    python integration/generate_integration.py
"""

import argparse
import copy
import os
from collections import OrderedDict

import yaml


# ── YAML setup (matches generate_all.py conventions) ─────────────────
def _od_representer(dumper, data):
    return dumper.represent_mapping("tag:yaml.org,2002:map", data.items())
yaml.add_representer(OrderedDict, _od_representer)

def _none_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:null", "null")
yaml.add_representer(type(None), _none_representer)

class QuotedStr(str):
    pass
def _quoted_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="'")
yaml.add_representer(QuotedStr, _quoted_representer)

class DotKey(str):
    pass
def _dotkey_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="'")
yaml.add_representer(DotKey, _dotkey_representer)

OD = OrderedDict
NUM_HOSTS = 10
HOSTS = [f"rtr-{i:02d}" for i in range(NUM_HOSTS)]

# ── Absence matrix ───────────────────────────────────────────────────
# host -> set of sections ABSENT from that host
ABSENT = {
    "rtr-03": {"change_procedures"},
    "rtr-05": {"fabric_interfaces"},
    "rtr-06": {"change_procedures", "access_control"},
    "rtr-07": {"fabric_interfaces"},
    "rtr-09": {"access_control"},
}

def hosts_for(section):
    """Return list of hosts present for a section."""
    return [h for h in HOSTS if section not in ABSENT.get(h, set())]


def write_yaml(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, width=120)


# ═══════════════════════════════════════════════════════════════════════
# S1: system_base — Overlap (Set A mechanic)
# ═══════════════════════════════════════════════════════════════════════
def gen_system_base():
    section = "system_base"
    present = hosts_for(section)

    base = OD([
        ("ntp_primary", "10.100.1.1"), ("ntp_secondary", "10.100.1.2"),
        ("ntp_source", "Loopback0"), ("ntp_auth_enabled", True),
        ("ntp_auth_key_id", 42), ("ntp_auth_algo", "md5"),
        ("log_host", "10.100.2.1"), ("log_protocol", "tcp"),
        ("log_port", 514), ("log_facility", "local6"),
        ("log_severity", "informational"), ("log_buffer", 1048576),
        ("aaa_login", "RADIUS_AUTH"), ("aaa_enable", "LOCAL"),
        ("radius_host_1", "10.100.3.1"), ("snmp_community", "INTEG_RO"),
    ])

    inputs = {}
    tier_c = {}
    for h in present:
        idx = int(h.split("-")[1])
        loc = f"site-{idx:02d}"
        data = OD(base)
        data["snmp_location"] = loc
        inputs[h] = data
        tier_c[h] = OD([("_class", "SystemBase"), ("snmp_location", loc)])

    class_def = OD(base)
    class_def["_identity"] = ["snmp_location"]
    tier_b = OD([("SystemBase", class_def)])

    return section, inputs, tier_b, tier_c


# ═══════════════════════════════════════════════════════════════════════
# S2: access_control — Subtraction (Set B mechanic)
# ═══════════════════════════════════════════════════════════════════════
def gen_access_control():
    section = "access_control"
    present = hosts_for(section)  # 8 hosts (rtr-06, rtr-09 absent)

    all_fields = OD([
        ("policy_name", "BASELINE-FW"), ("default_action", "deny"),
        ("log_denied", True), ("rate_limit", "1000pps"),
        ("timeout", 30), ("icmp_allow", True), ("ssh_allow", True),
        ("snmp_allow", True), ("ntp_allow", True), ("bgp_allow", True),
        ("ldp_allow", True), ("rsvp_allow", True),
        ("bfd_allow", True), ("tacacs_allow", True),
    ])

    # Fields removed in order (from end of list)
    removal_order = [
        "tacacs_allow", "bfd_allow", "rsvp_allow", "ldp_allow",
        "bgp_allow", "ntp_allow", "snmp_allow",
    ]

    inputs = {}
    tier_c = {}
    for rank, h in enumerate(present):
        data = OD(all_fields)
        removals = removal_order[:rank]
        for f in removals:
            del data[f]
        inputs[h] = data

        tc = OD([("_class", "AccessPolicy")])
        if removals:
            tc["_remove"] = list(removals)
        tier_c[h] = tc

    tier_b = OD([("AccessPolicy", OD(all_fields))])

    return section, inputs, tier_b, tier_c


# ═══════════════════════════════════════════════════════════════════════
# S3: alert_targets — Addition (Set C mechanic)
# ═══════════════════════════════════════════════════════════════════════
def gen_alert_targets():
    section = "alert_targets"
    present = hosts_for(section)

    base = OD([
        ("polling_interval", 300), ("timeout", 10), ("retries", 3),
        ("threshold_warn", 75), ("threshold_crit", 95),
    ])

    extras_ordered = [
        ("threshold_info", 50), ("escalation_group", "tier2"),
        ("suppress_flap", True), ("correlation_id", "auto"),
        ("dependency_check", True), ("auto_ticket", True),
        ("severity_override", "major"), ("notification_channel", "slack"),
        ("runbook_url", "https://wiki.lab/alerts"),
    ]

    inputs = {}
    tier_c = {}
    for rank, h in enumerate(present):
        data = OD(base)
        additions = OD()
        for i in range(rank):
            k, v = extras_ordered[i]
            data[k] = v
            additions[k] = v
        inputs[h] = data

        tc = OD([("_class", "AlertTarget")])
        tc.update(additions)
        tier_c[h] = tc

    tier_b = OD([("AlertTarget", OD(base))])

    return section, inputs, tier_b, tier_c


# ═══════════════════════════════════════════════════════════════════════
# S4: loopback0 — Identity (Set D mechanic)
# ═══════════════════════════════════════════════════════════════════════
def gen_loopback0():
    section = "loopback0"
    present = hosts_for(section)

    base = OD([
        ("interface_type", "Loopback"), ("description", "Router-ID"),
        ("mtu", 1500), ("admin_state", "up"), ("vrf", "default"),
        ("isis_passive", True), ("isis_metric", 10),
        ("mpls_ldp", True), ("mpls_te", False), ("bfd_enabled", True),
    ])

    inputs = {}
    tier_c = {}
    for h in present:
        idx = int(h.split("-")[1])
        addr = f"10.255.0.{idx}"
        data = OD(base)
        data["ipv4_address"] = addr
        inputs[h] = data
        tier_c[h] = OD([("_class", "Loopback0Config"), ("ipv4_address", addr)])

    class_def = OD(base)
    class_def["_identity"] = ["ipv4_address"]
    tier_b = OD([("Loopback0Config", class_def)])

    return section, inputs, tier_b, tier_c


# ═══════════════════════════════════════════════════════════════════════
# S5: change_procedures — Ordered List (Set G mechanic)
# ═══════════════════════════════════════════════════════════════════════
def gen_change_procedures():
    section = "change_procedures"
    present = hosts_for(section)  # 8 hosts (rtr-03, rtr-06 absent)

    canonical = [
        "drain_traffic", "snapshot_config", "backup_database",
        "health_check_pre", "apply_patches", "restart_services",
        "validate_routing", "run_smoke_tests", "restore_traffic",
        "health_check_post", "notify_stakeholders", "close_ticket",
    ]

    def make_doc(steps):
        return OD([
            ("approval_required", True),
            ("max_duration_hours", 4),
            ("steps", steps),
        ])

    deviant_host = "rtr-05"
    deviant_steps = list(canonical)
    deviant_steps[4], deviant_steps[5] = deviant_steps[5], deviant_steps[4]

    inputs = {}
    tier_c = {}
    for h in present:
        if h == deviant_host:
            inputs[h] = make_doc(deviant_steps)
            tier_c[h] = make_doc(deviant_steps)  # raw, no _class
        else:
            inputs[h] = make_doc(list(canonical))
            tier_c[h] = OD([("_class", "ChangeProcedure")])

    tier_b = OD([("ChangeProcedure", make_doc(list(canonical)))])

    return section, inputs, tier_b, tier_c


# ═══════════════════════════════════════════════════════════════════════
# S6: fabric_interfaces — Instances (Set L mechanic)
# ═══════════════════════════════════════════════════════════════════════
def gen_fabric_interfaces():
    section = "fabric_interfaces"
    present = hosts_for(section)  # 8 hosts (rtr-05, rtr-07 absent)

    num_intfs = 4

    inputs = {}
    tier_c = {}
    for h in present:
        hi = int(h.split("-")[1])
        interfaces = []
        instances = []
        for port in range(num_intfs):
            iface = OD([
                ("name", f"HuGigE0/0/0/{port}"),
                ("ipv4_address", f"10.{10 + hi}.{port}.1"),
                ("mtu", 9216), ("speed", "100g"), ("duplex", "full"),
                ("admin_state", "up"), ("isis_metric", 10),
            ])
            inst = OD([
                ("name", f"HuGigE0/0/0/{port}"),
                ("ipv4_address", f"10.{10 + hi}.{port}.1"),
            ])
            # rtr-02 intf 2: speed override
            if h == "rtr-02" and port == 2:
                iface["speed"] = "10g"
                inst["speed"] = "10g"
            # rtr-08 intf 3: isis_metric removal
            if h == "rtr-08" and port == 3:
                del iface["isis_metric"]
                inst["_remove"] = ["isis_metric"]
            interfaces.append(iface)
            instances.append(inst)
        inputs[h] = interfaces
        tier_c[h] = OD([
            ("_class", "FabricInterface"),
            ("instances", instances),
        ])

    tier_b = OD([("FabricInterface", OD([
        ("mtu", 9216), ("speed", "100g"), ("duplex", "full"),
        ("admin_state", "up"), ("isis_metric", 10),
        ("_identity", ["name", "ipv4_address"]),
    ]))])

    return section, inputs, tier_b, tier_c

# ═══════════════════════════════════════════════════════════════════════
# S7: telemetry_stack — Dot Notation (Set M mechanic)
# ═══════════════════════════════════════════════════════════════════════
def gen_telemetry_stack():
    section = "telemetry_stack"
    present = hosts_for(section)

    def base_telem():
        return OD([
            ("global_interval", 30), ("retry", 3),
            ("transport", OD([
                ("protocol", "grpc"), ("port", 50051),
                ("tls", OD([("enabled", True), ("cipher", "aes-256-gcm")])),
            ])),
            ("collectors", ["10.200.0.1", "10.200.0.2"]),
            ("logging", OD([
                ("interval", 60), ("facility", "local7"), ("severity", "warning"),
            ])),
        ])

    inputs = {}
    tier_c = {}
    for h in present:
        data = base_telem()
        tc = OD([("_class", "TelemetryStack")])

        if h == "rtr-01":
            data["global_interval"] = 60
            tc[DotKey("global_interval")] = 60
        elif h == "rtr-02":
            data["transport"]["tls"]["cipher"] = "aes-128-gcm"
            tc[DotKey("transport.tls.cipher")] = "aes-128-gcm"
        elif h == "rtr-03":
            del data["logging"]
            tc["_remove"] = ["logging"]
        elif h == "rtr-04":
            data["global_interval"] = 60
            data["collectors"] = ["10.200.0.9"]
            del data["transport"]["tls"]["cipher"]
            tc[DotKey("global_interval")] = 60
            tc[DotKey("collectors")] = ["10.200.0.9"]
            tc["_remove"] = ["transport.tls.cipher"]

        inputs[h] = data
        tier_c[h] = tc

    tier_b = OD([("TelemetryStack", base_telem())])

    return section, inputs, tier_b, tier_c


# ═══════════════════════════════════════════════════════════════════════
# S8: routing_policy — Partial Classification (Set N mechanic)
# ═══════════════════════════════════════════════════════════════════════
def gen_routing_policy():
    section = "routing_policy"
    present = hosts_for(section)

    group_a = OD([
        ("asn", 65000), ("router_id_source", "loopback0"),
        ("address_family", "ipv4-unicast"),
        ("bestpath", "as-path-multipath-relax"),
        ("graceful_restart", True), ("graceful_restart_time", 120),
        ("max_paths_ebgp", 8), ("max_paths_ibgp", 8),
        ("default_originate", False),
    ])
    group_b = OD([
        ("asn", 65000), ("router_id_source", "loopback0"),
        ("address_family", "vpnv4-unicast"),
        ("bestpath", "compare-routerid"),
        ("graceful_restart", False), ("max_paths_ebgp", 2),
        ("confederation_id", 100),
        ("confederation_peers", [65001, 65002]),
        ("soo_enabled", True),
    ])
    outlier_06 = OD([
        ("asn", 65100), ("router_id_source", "loopback1"),
        ("address_family", "ipv6-unicast"),
        ("bestpath", "as-path-multipath-relax"),
        ("graceful_restart", True), ("graceful_restart_time", 300),
        ("max_paths_ebgp", 16), ("bfd_enabled", True), ("bfd_interval", 150),
    ])
    outlier_09 = OD([
        ("asn", 65200), ("router_id_source", "loopback2"),
        ("address_family", "l2vpn-evpn"),
        ("bestpath", "compare-routerid"),
        ("route_type_5", True), ("arp_suppress", True),
        ("mac_ip_routes", True), ("nd_suppress", True),
    ])

    assignment = {
        "rtr-00": ("RoutingPolicyCore", group_a),
        "rtr-01": ("RoutingPolicyCore", group_a),
        "rtr-02": ("RoutingPolicyCore", group_a),
        "rtr-03": ("RoutingPolicyCore", group_a),
        "rtr-04": ("RoutingPolicyVpn", group_b),
        "rtr-05": ("RoutingPolicyVpn", group_b),
        "rtr-06": (None, outlier_06),
        "rtr-07": ("RoutingPolicyVpn", group_b),
        "rtr-08": ("RoutingPolicyVpn", group_b),
        "rtr-09": (None, outlier_09),
    }

    inputs = {}
    tier_c = {}
    for h in present:
        cls_name, data = assignment[h]
        inputs[h] = OD(data)
        if cls_name:
            tier_c[h] = OD([("_class", cls_name)])
        else:
            tier_c[h] = OD(data)

    tier_b = OD([
        ("RoutingPolicyCore", OD(group_a)),
        ("RoutingPolicyVpn", OD(group_b)),
    ])

    return section, inputs, tier_b, tier_c


# ═══════════════════════════════════════════════════════════════════════
# S9: isis_config — Compound: Identity + Removal + Override
# ═══════════════════════════════════════════════════════════════════════
def gen_isis_config():
    section = "isis_config"
    present = hosts_for(section)

    base = OD([
        ("process_id", 1), ("is_type", "level-2-only"),
        ("metric_style", "wide"), ("net_area", "49.0001"),
        ("auth_type", "md5"), ("auth_password", "ISIS_KEY_1"),
        ("lsp_gen_interval", 5), ("lsp_refresh", 900),
        ("lsp_lifetime", 1200), ("spf_interval", 10),
        ("spf_initial_wait", 50), ("max_lsp_lifetime", 65535),
    ])

    inputs = {}
    tier_c = {}
    for h in present:
        idx = int(h.split("-")[1])
        net = f"49.0001.0100.0000.{idx:04d}.00"
        data = OD(base)
        data["net_address"] = net

        tc = OD([("_class", "IsisConfig"), ("net_address", net)])

        if h == "rtr-02":
            del data["auth_password"]
            tc["_remove"] = ["auth_password"]
        elif h == "rtr-03":
            data["metric_style"] = "narrow"
            tc["metric_style"] = "narrow"
        elif h == "rtr-06":
            del data["spf_interval"]
            del data["lsp_refresh"]
            tc["_remove"] = ["spf_interval", "lsp_refresh"]

        inputs[h] = data
        tier_c[h] = tc

    class_def = OD(base)
    class_def["_identity"] = ["net_address"]
    tier_b = OD([("IsisConfig", class_def)])

    return section, inputs, tier_b, tier_c


# ═══════════════════════════════════════════════════════════════════════
# S10: vrf_routing — Compound: Instances + Identity + Override + Removal
# ═══════════════════════════════════════════════════════════════════════
def gen_vrf_routing():
    section = "vrf_routing"
    present = hosts_for(section)

    vrf_names = ["CUST-A", "CUST-B", "MGMT"]

    inputs = {}
    tier_c = {}
    for h in present:
        hi = int(h.split("-")[1])
        vrfs_input = []
        vrfs_tc = []
        for vi, vname in enumerate(vrf_names):
            rd = f"65000:{hi * 100 + (vi + 1) * 100}"
            vrf = OD([
                ("vrf_name", vname), ("rd_value", rd),
                ("rd_format", "type0"), ("import_policy", "VRF-IMPORT"),
                ("export_policy", "VRF-EXPORT"),
                ("route_limit", 10000), ("route_warning_pct", 80),
            ])
            inst = OD([("vrf_name", vname), ("rd_value", rd)])

            # rtr-03, VRF 1 (CUST-B): route_limit override
            if h == "rtr-03" and vi == 1:
                vrf["route_limit"] = 5000
                inst["route_limit"] = 5000
            # rtr-04, VRF 2 (MGMT): route_warning_pct removal
            if h == "rtr-04" and vi == 2:
                del vrf["route_warning_pct"]
                inst["_remove"] = ["route_warning_pct"]

            vrfs_input.append(vrf)
            vrfs_tc.append(inst)

        inputs[h] = vrfs_input
        tier_c[h] = OD([
            ("_class", "VrfConfig"),
            ("instances", vrfs_tc),
        ])

    tier_b = OD([("VrfConfig", OD([
        ("rd_format", "type0"), ("import_policy", "VRF-IMPORT"),
        ("export_policy", "VRF-EXPORT"),
        ("route_limit", 10000), ("route_warning_pct", 80),
        ("_identity", ["vrf_name", "rd_value"]),
    ]))])

    return section, inputs, tier_b, tier_c


# ═══════════════════════════════════════════════════════════════════════
# S11: policy_maps — Compound: Dot Notation + Subtraction + Addition
# ═══════════════════════════════════════════════════════════════════════
def gen_policy_maps():
    section = "policy_maps"
    present = hosts_for(section)

    def base_policy():
        return OD([
            ("policy", OD([
                ("name", "CORE-RM"), ("default_action", "deny"),
                ("match", OD([
                    ("prefix_list", "CORE-PREFIXES"),
                    ("community", "CORE-COMM"),
                    ("as_path", "CORE-ASPATH"),
                ])),
                ("set", OD([
                    ("local_pref", 200), ("med", 100),
                    ("community", "65000:100"),
                ])),
            ])),
        ])

    inputs = {}
    tier_c = {}
    for h in present:
        data = base_policy()
        tc = OD([("_class", "PolicyMap")])

        if h == "rtr-01":
            data["policy"]["match"]["as_path"] = "EDGE-ASPATH"
            tc[DotKey("policy.match.as_path")] = "EDGE-ASPATH"
        elif h == "rtr-02":
            del data["policy"]["set"]["med"]
            data["policy"]["set"]["weight"] = 200
            tc["_remove"] = ["policy.set.med"]
            tc[DotKey("policy.set.weight")] = 200
        elif h == "rtr-04":
            data["policy"]["match"]["prefix_list"] = "EDGE-PREFIXES"
            data["policy"]["dampening"] = OD([
                ("half_life", 15), ("reuse", 750),
            ])
            tc[DotKey("policy.match.prefix_list")] = "EDGE-PREFIXES"
            tc[DotKey("policy.dampening.half_life")] = 15
            tc[DotKey("policy.dampening.reuse")] = 750
        elif h == "rtr-07":
            data["policy"]["default_action"] = "permit"
            data["policy"]["set"]["local_pref"] = 300
            del data["policy"]["set"]["community"]
            tc[DotKey("policy.default_action")] = "permit"
            tc[DotKey("policy.set.local_pref")] = 300
            tc["_remove"] = ["policy.set.community"]

        inputs[h] = data
        tier_c[h] = tc

    tier_b = OD([("PolicyMap", base_policy())])

    return section, inputs, tier_b, tier_c


# ═══════════════════════════════════════════════════════════════════════
# S12: bgp_neighbors — Compound: Instances + Dot Notation
# ═══════════════════════════════════════════════════════════════════════
def gen_bgp_neighbors():
    section = "bgp_neighbors"
    present = hosts_for(section)

    peer_names = ["PE-01", "PE-02", "PE-03"]

    def base_neighbor():
        return OD([
            ("remote_as", 65001),
            ("transport", OD([
                ("protocol", "tcp"), ("port", 179),
                ("md5_auth", True), ("ttl_security", 1),
            ])),
            ("timers", OD([
                ("keepalive", 30), ("hold", 90), ("connect_retry", 10),
            ])),
            ("afi", OD([
                ("ipv4_unicast", True), ("vpnv4", False),
            ])),
        ])

    exceptions = [
        ("rtr-01", 1, "override", "transport.md5_auth", False),
        ("rtr-02", 2, "remove", "timers.connect_retry", None),
        ("rtr-04", 0, "override", "afi.vpnv4", True),
        ("rtr-08", 1, "remove", "timers.hold", None),
    ]

    def _deep_set(d, path, val):
        keys = path.split(".")
        for k in keys[:-1]:
            d = d[k]
        d[keys[-1]] = val

    def _deep_del(d, path):
        keys = path.split(".")
        for k in keys[:-1]:
            d = d[k]
        del d[keys[-1]]

    inputs = {}
    tier_c = {}
    for h in present:
        hi = int(h.split("-")[1])
        neighbors_input = []
        neighbors_tc = []
        for pi, pname in enumerate(peer_names):
            addr = f"10.{10 + hi}.1.{pi + 1}"
            nbr = base_neighbor()
            nbr["peer_name"] = pname
            nbr["peer_address"] = addr
            nbr.move_to_end("peer_name", last=False)
            nbr.move_to_end("peer_address", last=False)

            inst = OD([("peer_name", pname), ("peer_address", addr)])

            for ex_host, ex_pi, ex_op, ex_path, ex_val in exceptions:
                if h == ex_host and pi == ex_pi:
                    if ex_op == "override":
                        _deep_set(nbr, ex_path, ex_val)
                        inst[DotKey(ex_path)] = ex_val
                    elif ex_op == "remove":
                        _deep_del(nbr, ex_path)
                        inst["_remove"] = inst.get("_remove", []) + [ex_path]

            neighbors_input.append(nbr)
            neighbors_tc.append(inst)

        inputs[h] = neighbors_input
        tier_c[h] = OD([
            ("_class", "BgpNeighborConfig"),
            ("instances", neighbors_tc),
        ])

    class_def = base_neighbor()
    class_def["_identity"] = ["peer_name", "peer_address"]
    tier_b = OD([("BgpNeighborConfig", class_def)])

    return section, inputs, tier_b, tier_c


# ═══════════════════════════════════════════════════════════════════════
# T1: auth_methods — Trap: Type Coercion
# ═══════════════════════════════════════════════════════════════════════
def gen_auth_methods():
    section = "auth_methods"
    present = hosts_for(section)

    host_data = {
        "rtr-00": OD([("mfa_enabled", True),              ("timeout", 30),              ("max_retries", 3),              ("method", "radius")]),
        "rtr-01": OD([("mfa_enabled", QuotedStr("true")), ("timeout", 30),              ("max_retries", 3),              ("method", "radius")]),
        "rtr-02": OD([("mfa_enabled", True),              ("timeout", QuotedStr("30")), ("max_retries", 3),              ("method", "radius")]),
        "rtr-03": OD([("mfa_enabled", 1),                 ("timeout", 30),              ("max_retries", QuotedStr("3")), ("method", "radius")]),
        "rtr-04": OD([("mfa_enabled", True),              ("timeout", 30),              ("max_retries", 3),              ("method", QuotedStr("RADIUS"))]),
        "rtr-05": OD([("mfa_enabled", QuotedStr("yes")),  ("timeout", 30),              ("max_retries", 3),              ("method", "radius")]),
        "rtr-06": OD([("mfa_enabled", True),              ("timeout", 30),              ("max_retries", 3),              ("method", "radius")]),
        "rtr-07": OD([("mfa_enabled", QuotedStr("on")),   ("timeout", 30),              ("max_retries", 3),              ("method", "radius")]),
        "rtr-08": OD([("mfa_enabled", True),              ("timeout", 30),              ("max_retries", 3),              ("method", "radius")]),
        "rtr-09": OD([("mfa_enabled", 0),                 ("timeout", 30),              ("max_retries", 3),              ("method", "radius")]),
    }

    inputs = {}
    tier_c = {}
    for h in present:
        inputs[h] = OD(host_data[h])
        tier_c[h] = OD(host_data[h])  # raw passthrough

    return section, inputs, OD(), tier_c


# ═══════════════════════════════════════════════════════════════════════
# T2: vendor_extensions — Trap: Heterogeneous
# ═══════════════════════════════════════════════════════════════════════
def gen_vendor_extensions():
    section = "vendor_extensions"
    present = hosts_for(section)

    schemas = {
        "rtr-00": OD([("host", "10.100.10.1"), ("port", 1812), ("secret_enc", "0F5A3E7C"), ("timeout", 5), ("retries", 3)]),
        "rtr-01": OD([("host", "10.100.10.2"), ("port", 49), ("key_enc", "A1B2C3D4"), ("timeout", 10)]),
        "rtr-02": OD([("host", "10.100.10.3"), ("port", 514), ("protocol", "tcp"), ("facility", "local6"), ("severity", "info")]),
        "rtr-03": OD([("key_id", 1), ("algorithm", "md5"), ("key_value", "NTP_AUTH_1"), ("trusted", True)]),
        "rtr-04": OD([("host", "10.100.10.5"), ("port", 162), ("community", "TRAP_RO"), ("version", "2c"), ("timeout", 5)]),
        "rtr-05": OD([("destination", "10.100.10.6"), ("port", 9995), ("version", 9), ("source_intf", "Loopback0")]),
        "rtr-06": OD([("server_ip", "10.100.10.7"), ("vrf", "MGMT"), ("circuit_id", True)]),
        "rtr-07": OD([("primary", "10.100.10.8"), ("secondary", "10.100.10.9"), ("domain_name", "archetypal.lab")]),
        "rtr-08": OD([("interval", 150), ("min_rx", 150), ("multiplier", 3)]),
        "rtr-09": OD([("holdtime", 120), ("timer", 30), ("reinit", 2)]),
    }

    inputs = {}
    tier_c = {}
    for h in present:
        inputs[h] = OD(schemas[h])
        tier_c[h] = OD(schemas[h])

    return section, inputs, OD(), tier_c


# ═══════════════════════════════════════════════════════════════════════
# T3: path_export — Trap: Same Children, Different Parents
# ═══════════════════════════════════════════════════════════════════════
def gen_path_export():
    section = "path_export"
    present = hosts_for(section)

    parent_keys = [
        "telemetry_export", "sflow_export", "netflow_export",
        "ipfix_export", "streaming_export", "tap_export",
        "mirror_export", "span_export", "erspan_export", "pcap_export",
    ]
    leaf = OD([("interval", 30), ("protocol", "grpc"), ("encoding", "gpb")])

    inputs = {}
    tier_c = {}
    for h in present:
        hi = int(h.split("-")[1])
        data = OD([("export_policy", OD([(parent_keys[hi], OD(leaf))]))])
        inputs[h] = data
        tier_c[h] = OD(data)

    return section, inputs, OD(), tier_c


# ═══════════════════════════════════════════════════════════════════════
# ASSEMBLY — combine all sections into per-host files
# ═══════════════════════════════════════════════════════════════════════

ALL_GENERATORS = [
    gen_system_base,        # S1
    gen_access_control,     # S2
    gen_alert_targets,      # S3
    gen_loopback0,          # S4
    gen_change_procedures,  # S5
    gen_fabric_interfaces,  # S6
    gen_telemetry_stack,    # S7
    gen_routing_policy,     # S8
    gen_isis_config,        # S9
    gen_vrf_routing,        # S10
    gen_policy_maps,        # S11
    gen_bgp_neighbors,      # S12
    gen_auth_methods,       # T1
    gen_vendor_extensions,  # T2
    gen_path_export,        # T3
]


def generate(out_dir):
    """Generate the complete integration fixture."""
    all_tier_b = OD()
    all_inputs = {h: OD() for h in HOSTS}
    all_tier_c = {h: OD() for h in HOSTS}

    for gen_fn in ALL_GENERATORS:
        section, inputs, tier_b, tier_c = gen_fn()
        all_tier_b.update(tier_b)
        for h in HOSTS:
            if h in inputs:
                all_inputs[h][section] = inputs[h]
            if h in tier_c:
                all_tier_c[h][section] = tier_c[h]

    # Write input files
    for h in HOSTS:
        write_yaml(os.path.join(out_dir, "input", f"{h}.yaml"), all_inputs[h])

    # Write golden Tier B
    write_yaml(os.path.join(out_dir, "golden", "tier_b.yaml"), all_tier_b)

    # Write golden Tier C
    for h in HOSTS:
        write_yaml(os.path.join(out_dir, "golden", "tier_c", f"{h}.yaml"), all_tier_c[h])

    # Write expected.yaml
    expected = build_expected()
    write_yaml(os.path.join(out_dir, "expected.yaml"), expected)

    # Stats
    print(f"  Integration fixture generated in {out_dir}/")
    print(f"  {len(HOSTS)} input files")
    print(f"  {len(all_tier_b)} classes in tier_b")
    for h in HOSTS:
        n_in = len(all_inputs[h])
        n_out = len(all_tier_c[h])
        absent = ABSENT.get(h, set())
        tag = f"  (absent: {', '.join(sorted(absent))})" if absent else ""
        print(f"    {h}: {n_in} sections{tag}")


def build_expected():
    positive = [
        "system_base", "access_control", "alert_targets", "loopback0",
        "change_procedures", "fabric_interfaces", "telemetry_stack",
        "routing_policy", "isis_config", "vrf_routing",
        "policy_maps", "bgp_neighbors",
    ]
    negative = ["auth_methods", "vendor_extensions", "path_export"]

    return OD([
        ("positive_sections", positive),
        ("negative_sections", negative),
        ("absent_sections", {
            "access_control": ["rtr-06", "rtr-09"],
            "change_procedures": ["rtr-03", "rtr-06"],
            "fabric_interfaces": ["rtr-05", "rtr-07"],
        }),
        ("classes", OD([
            ("system_base", {"class_name": "SystemBase", "class_count": 1,
                "static_field_count": 16, "identity_fields": ["snmp_location"],
                "hosts": HOSTS}),
            ("access_control", {"class_name": "AccessPolicy", "class_count": 1,
                "static_field_count": 14,
                "removal_progression": list(range(len(hosts_for("access_control")))),
                "hosts": hosts_for("access_control")}),
            ("alert_targets", {"class_name": "AlertTarget", "class_count": 1,
                "static_field_count": 5,
                "addition_progression": list(range(NUM_HOSTS)),
                "hosts": HOSTS}),
            ("loopback0", {"class_name": "Loopback0Config", "class_count": 1,
                "static_field_count": 10, "identity_fields": ["ipv4_address"],
                "hosts": HOSTS}),
            ("change_procedures", {"class_name": "ChangeProcedure", "class_count": 1,
                "hosts_matching": [h for h in hosts_for("change_procedures") if h != "rtr-05"],
                "hosts_raw": ["rtr-05"], "raw_reason": "list_reorder",
                "hosts": hosts_for("change_procedures")}),
            ("fabric_interfaces", {"class_name": "FabricInterface", "class_count": 1,
                "static_field_count": 5, "identity_fields": ["name", "ipv4_address"],
                "instance_count_per_host": 4,
                "overrides": [{"host": "rtr-02", "instance": 2, "field": "speed", "value": "10g"}],
                "removals": [{"host": "rtr-08", "instance": 3, "field": "isis_metric"}],
                "hosts": hosts_for("fabric_interfaces")}),
            ("telemetry_stack", {"class_name": "TelemetryStack", "class_count": 1,
                "hosts": HOSTS}),
            ("routing_policy", {"class_count": 2,
                "class_names": ["RoutingPolicyCore", "RoutingPolicyVpn"],
                "group_1": ["rtr-00", "rtr-01", "rtr-02", "rtr-03"],
                "group_2": ["rtr-04", "rtr-05", "rtr-07", "rtr-08"],
                "raw_hosts": ["rtr-06", "rtr-09"],
                "shared_fields_not_merged": ["asn", "router_id_source"],
                "hosts": HOSTS}),
            ("isis_config", {"class_name": "IsisConfig", "class_count": 1,
                "static_field_count": 12, "identity_fields": ["net_address"],
                "compound_operations": {
                    "rtr-02": "identity + removal",
                    "rtr-03": "identity + override",
                    "rtr-06": "identity + 2_removals"},
                "hosts": HOSTS}),
            ("vrf_routing", {"class_name": "VrfConfig", "class_count": 1,
                "static_field_count": 5, "identity_fields": ["vrf_name", "rd_value"],
                "instance_count_per_host": 3,
                "overrides": [{"host": "rtr-03", "instance": 1, "field": "route_limit", "value": 5000}],
                "removals": [{"host": "rtr-04", "instance": 2, "field": "route_warning_pct"}],
                "hosts": HOSTS}),
            ("policy_maps", {"class_name": "PolicyMap", "class_count": 1, "hosts": HOSTS}),
            ("bgp_neighbors", {"class_name": "BgpNeighborConfig", "class_count": 1,
                "static_field_count": 10, "identity_fields": ["peer_name", "peer_address"],
                "instance_count_per_host": 3,
                "instance_dot_overrides": [
                    {"host": "rtr-01", "instance": 1, "path": "transport.md5_auth", "value": False},
                    {"host": "rtr-04", "instance": 0, "path": "afi.vpnv4", "value": True}],
                "instance_dot_removals": [
                    {"host": "rtr-02", "instance": 2, "path": "timers.connect_retry"},
                    {"host": "rtr-08", "instance": 1, "path": "timers.hold"}],
                "hosts": HOSTS}),
        ])),
        ("traps", OD([
            ("auth_methods", {"expected_classes": 0, "reason": "type_coercion", "hosts": HOSTS}),
            ("vendor_extensions", {"expected_classes": 0, "reason": "heterogeneous",
                "incidental_overlap": ["host", "port", "timeout"], "hosts": HOSTS}),
            ("path_export", {"expected_classes": 0, "reason": "same_children_different_parents", "hosts": HOSTS}),
        ])),
    ])


def main():
    parser = argparse.ArgumentParser(description="Generate Level 2 integration fixture")
    parser.add_argument("--out-dir", default=".", help="Output directory (default: current dir)")
    args = parser.parse_args()
    generate(args.out_dir)


if __name__ == "__main__":
    main()
