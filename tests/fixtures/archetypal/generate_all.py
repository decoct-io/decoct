#!/usr/bin/env python3
"""
Generate per-set archetypal test fixtures for decoct.

Each set gets its own directory with:
  input/rtr-XX.yaml    — Tier A raw data (what decoct receives)
  golden/tier_b.yaml   — expected class extraction
  golden/tier_c/       — expected per-host output
  expected.yaml        — test metadata (class counts, scoring criteria)

Usage:
    python generate_all.py [--out-dir .]
"""

import argparse
import os
from collections import OrderedDict

import yaml


# ── YAML setup ──────────────────────────────────────────────────────────
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
NUM_FILES = 5
HOSTS = [f"rtr-{i:02d}" for i in range(NUM_FILES)]


def write_yaml(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, width=120)


# ═══════════════════════════════════════════════════════════════════════
# SET A — Overlap + Trap 1 (Type Coercion)
# ═══════════════════════════════════════════════════════════════════════
def gen_set_a(out_dir):
    set_dir = os.path.join(out_dir, "set_a")
    locations = ["site-A", "site-B", "site-C", "site-D", "site-E"]

    for fi in range(NUM_FILES):
        # Input
        doc = OD([
            ("base_infra", OD([
                ("ntp_primary", "10.100.1.1"),
                ("ntp_secondary", "10.100.1.2"),
                ("ntp_source", "Loopback0"),
                ("ntp_auth_enabled", True),
                ("ntp_auth_key_id", 42),
                ("ntp_auth_algo", "md5"),
                ("log_host", "10.100.2.1"),
                ("log_protocol", "tcp"),
                ("log_port", 514),
                ("log_facility", "local6"),
                ("log_severity", "informational"),
                ("log_buffer", 1048576),
                ("aaa_login", "RADIUS_AUTH"),
                ("aaa_enable", "LOCAL"),
                ("aaa_authz", "RADIUS_AUTH"),
                ("aaa_acct", "RADIUS_ACCT"),
                ("radius_host_1", "10.100.3.1"),
                ("radius_host_2", "10.100.3.2"),
                ("radius_timeout", 5),
                ("snmp_community", "ARCHETYPAL_RO"),
                ("snmp_location", locations[fi]),
                ("snmp_contact", "noc@archetypal.lab"),
            ])),
        ])
        # Trap 1 adjacent
        trap_variants = [
            OD([("snmp_auth_enabled", True), ("snmp_encrypt", True), ("snmp_version", 3)]),
            OD([("snmp_auth_enabled", QuotedStr("true")), ("snmp_encrypt", True), ("snmp_version", 3)]),
            OD([("snmp_auth_enabled", True), ("snmp_encrypt", QuotedStr("yes")), ("snmp_version", QuotedStr("3"))]),
            OD([("snmp_auth_enabled", 1), ("snmp_encrypt", True), ("snmp_version", 3)]),
            OD([("snmp_auth_enabled", QuotedStr("on")), ("snmp_encrypt", QuotedStr("true")), ("snmp_version", 3)]),
        ]
        doc["snmp_security"] = trap_variants[fi]
        write_yaml(os.path.join(set_dir, "input", f"{HOSTS[fi]}.yaml"), doc)

    # Golden Tier B
    tier_b = OD([
        ("BaseInfra", OD([
            ("ntp_primary", "10.100.1.1"),
            ("ntp_secondary", "10.100.1.2"),
            ("ntp_source", "Loopback0"),
            ("ntp_auth_enabled", True),
            ("ntp_auth_key_id", 42),
            ("ntp_auth_algo", "md5"),
            ("log_host", "10.100.2.1"),
            ("log_protocol", "tcp"),
            ("log_port", 514),
            ("log_facility", "local6"),
            ("log_severity", "informational"),
            ("log_buffer", 1048576),
            ("aaa_login", "RADIUS_AUTH"),
            ("aaa_enable", "LOCAL"),
            ("aaa_authz", "RADIUS_AUTH"),
            ("aaa_acct", "RADIUS_ACCT"),
            ("radius_host_1", "10.100.3.1"),
            ("radius_host_2", "10.100.3.2"),
            ("radius_timeout", 5),
            ("snmp_community", "ARCHETYPAL_RO"),
            ("snmp_contact", "noc@archetypal.lab"),
            ("_identity", ["snmp_location"]),
        ])),
    ])
    write_yaml(os.path.join(set_dir, "golden", "tier_b.yaml"), tier_b)

    # Golden Tier C
    trap_c = [
        OD([("snmp_auth_enabled", True), ("snmp_encrypt", True), ("snmp_version", 3)]),
        OD([("snmp_auth_enabled", QuotedStr("true")), ("snmp_encrypt", True), ("snmp_version", 3)]),
        OD([("snmp_auth_enabled", True), ("snmp_encrypt", QuotedStr("yes")), ("snmp_version", QuotedStr("3"))]),
        OD([("snmp_auth_enabled", 1), ("snmp_encrypt", True), ("snmp_version", 3)]),
        OD([("snmp_auth_enabled", QuotedStr("on")), ("snmp_encrypt", QuotedStr("true")), ("snmp_version", 3)]),
    ]
    for fi in range(NUM_FILES):
        tc = OD([
            ("base_infra", OD([
                ("_class", "BaseInfra"),
                ("snmp_location", locations[fi]),
            ])),
            ("snmp_security", trap_c[fi]),
        ])
        write_yaml(os.path.join(set_dir, "golden", "tier_c", f"{HOSTS[fi]}.yaml"), tc)

    # Expected metadata
    expected = {
        "positive_sections": ["base_infra"],
        "negative_sections": ["snmp_security"],
        "classes": {
            "base_infra": {
                "class_name": "BaseInfra",
                "class_count": 1,
                "static_field_count": 21,
                "identity_fields": ["snmp_location"],
                "override_fields": ["snmp_location"],
            },
        },
        "traps": {
            "snmp_security": {
                "expected_classes": 0,
                "reason": "type_coercion",
            },
        },
    }
    write_yaml(os.path.join(set_dir, "expected.yaml"), expected)


# ═══════════════════════════════════════════════════════════════════════
# SET B — Subtraction
# ═══════════════════════════════════════════════════════════════════════
def gen_set_b(out_dir):
    set_dir = os.path.join(out_dir, "set_b")

    full = OD([
        ("policy_name", "CORE-QOS"), ("bandwidth_pct", 20), ("priority", True),
        ("dscp", "ef"), ("police_rate", "100mbps"), ("burst", "50ms"),
        ("queue_limit", 512), ("wred_min", 64), ("wred_max", 256),
        ("ecn", True), ("shaping_rate", "1gbps"),
    ])
    removals = {
        0: [], 1: ["burst"], 2: ["burst", "wred_min", "wred_max"],
        3: ["burst", "wred_min", "wred_max", "ecn"],
        4: ["burst", "wred_min", "wred_max", "ecn", "shaping_rate", "queue_limit"],
    }

    for fi in range(NUM_FILES):
        drop = set(removals[fi])
        doc = OD([("qos_policy", OD((k, v) for k, v in full.items() if k not in drop))])
        write_yaml(os.path.join(set_dir, "input", f"{HOSTS[fi]}.yaml"), doc)

    # Tier B
    write_yaml(os.path.join(set_dir, "golden", "tier_b.yaml"),
               OD([("QosPolicy", OD(full))]))

    # Tier C
    for fi in range(NUM_FILES):
        tc = OD([("_class", "QosPolicy")])
        if removals[fi]:
            tc["_remove"] = removals[fi]
        write_yaml(os.path.join(set_dir, "golden", "tier_c", f"{HOSTS[fi]}.yaml"),
                   OD([("qos_policy", tc)]))

    write_yaml(os.path.join(set_dir, "expected.yaml"), {
        "positive_sections": ["qos_policy"],
        "negative_sections": [],
        "classes": {
            "qos_policy": {
                "class_name": "QosPolicy",
                "class_count": 1,
                "static_field_count": 11,
                "removal_progression": [0, 1, 3, 4, 6],
            },
        },
    })


# ═══════════════════════════════════════════════════════════════════════
# SET C — Addition + Trap 2 (Low Jaccard)
# ═══════════════════════════════════════════════════════════════════════
def gen_set_c(out_dir):
    set_dir = os.path.join(out_dir, "set_c")

    base = OD([
        ("polling_interval", 300), ("timeout", 10), ("retries", 3),
        ("threshold_warn", 75), ("threshold_crit", 95),
    ])
    extras = {
        0: [],
        1: [("threshold_info", 50)],
        2: [("threshold_info", 50), ("escalation_group", "tier2")],
        3: [("threshold_info", 50), ("escalation_group", "tier2"), ("suppress_flap", True)],
        4: [("threshold_info", 50), ("escalation_group", "tier2"), ("suppress_flap", True),
            ("correlation_id", "auto"), ("dependency_check", True)],
    }
    trap2_variants = {
        0: ("telemetry", OD([("interval", 30), ("protocol", "grpc"), ("encoding", "gpb")])),
        1: ("sflow", OD([("sample_rate", 1024), ("collector", "10.0.1.1"), ("port", 6343)])),
        2: ("netflow", OD([("version", 9), ("exporter", "10.0.2.1"), ("template_timeout", 600)])),
        3: ("streaming", OD([("sensor_group", "ENVMON"), ("destination", "10.0.3.1"), ("cadence", 10000)])),
        4: ("snmp_polling", OD([("community", "MONITOR_RO"), ("interval", 300), ("target", "10.0.4.1")])),
    }

    for fi in range(NUM_FILES):
        monitor = OD(base)
        for k, v in extras[fi]:
            monitor[k] = v
        child_key, child_data = trap2_variants[fi]
        doc = OD([
            ("monitor_target", monitor),
            ("service_policy", OD([(child_key, child_data)])),
        ])
        write_yaml(os.path.join(set_dir, "input", f"{HOSTS[fi]}.yaml"), doc)

    # Tier B
    write_yaml(os.path.join(set_dir, "golden", "tier_b.yaml"),
               OD([("MonitorTarget", OD(base))]))

    # Tier C
    for fi in range(NUM_FILES):
        tc_monitor = OD([("_class", "MonitorTarget")])
        for k, v in extras[fi]:
            tc_monitor[k] = v
        child_key, child_data = trap2_variants[fi]
        tc = OD([
            ("monitor_target", tc_monitor),
            ("service_policy", OD([(child_key, child_data)])),
        ])
        write_yaml(os.path.join(set_dir, "golden", "tier_c", f"{HOSTS[fi]}.yaml"), tc)

    write_yaml(os.path.join(set_dir, "expected.yaml"), {
        "positive_sections": ["monitor_target"],
        "negative_sections": ["service_policy"],
        "classes": {
            "monitor_target": {
                "class_name": "MonitorTarget",
                "class_count": 1,
                "static_field_count": 5,
                "addition_progression": [0, 1, 2, 3, 5],
            },
        },
        "traps": {
            "service_policy": {
                "expected_classes": 0,
                "reason": "low_jaccard_disguised",
            },
        },
    })


# ═══════════════════════════════════════════════════════════════════════
# SET D — Identity + Trap 3 (Structural Nesting)
# ═══════════════════════════════════════════════════════════════════════
def gen_set_d(out_dir):
    set_dir = os.path.join(out_dir, "set_d")

    static = OD([
        ("interface_type", "Loopback"), ("description", "Router-ID"),
        ("mtu", 1500), ("admin_state", "up"), ("vrf", "default"),
        ("isis_passive", True), ("isis_metric", 10),
        ("mpls_ldp", True), ("mpls_te", False),
    ])

    trap3_variants = [
        OD([("dns_server", "10.100.1.1"), ("dns_search", "archetypal.lab")]),                          # flat
        OD([("dns", OD([("server", "10.100.1.1"), ("search", "archetypal.lab")]))]),                    # nested dns
        OD([("dns_server", "10.100.1.1"), ("dns_search", "archetypal.lab")]),                          # flat
        OD([("dns", OD([("server", "10.100.1.1"), ("search", "archetypal.lab")]))]),                    # nested dns
        OD([("dns_config", OD([("primary_server", "10.100.1.1"), ("search_domain", "archetypal.lab")]))]),  # dns_config
    ]

    for fi in range(NUM_FILES):
        loopback = OD(static)
        loopback["ipv4_address"] = f"10.0.0.{fi}"
        doc = OD([
            ("loopback_interface", loopback),
            ("dns_resolution", trap3_variants[fi]),
        ])
        write_yaml(os.path.join(set_dir, "input", f"{HOSTS[fi]}.yaml"), doc)

    # Tier B
    tier_b_class = OD(static)
    tier_b_class["_identity"] = ["ipv4_address"]
    write_yaml(os.path.join(set_dir, "golden", "tier_b.yaml"),
               OD([("LoopbackInterface", tier_b_class)]))

    # Tier C
    for fi in range(NUM_FILES):
        tc = OD([
            ("loopback_interface", OD([
                ("_class", "LoopbackInterface"),
                ("ipv4_address", f"10.0.0.{fi}"),
            ])),
            ("dns_resolution", trap3_variants[fi]),
        ])
        write_yaml(os.path.join(set_dir, "golden", "tier_c", f"{HOSTS[fi]}.yaml"), tc)

    write_yaml(os.path.join(set_dir, "expected.yaml"), {
        "positive_sections": ["loopback_interface"],
        "negative_sections": ["dns_resolution"],
        "classes": {
            "loopback_interface": {
                "class_name": "LoopbackInterface",
                "class_count": 1,
                "static_field_count": 9,
                "identity_fields": ["ipv4_address"],
            },
        },
        "traps": {
            "dns_resolution": {
                "expected_classes": 0,
                "max_classes": 2,
                "reason": "structural_nesting",
                "note": "0 classes (all raw) or at most 2 (flat pair + nested pair). Never 1.",
            },
        },
    })


# ═══════════════════════════════════════════════════════════════════════
# SET E — Heterogeneous
# ═══════════════════════════════════════════════════════════════════════
def gen_set_e(out_dir):
    set_dir = os.path.join(out_dir, "set_e")

    variants = [
        OD([("protocol", "bgp"), ("neighbor", "10.1.0.0"), ("remote_as", 65100),
            ("family", "ipv4-unicast"), ("graceful_restart", True), ("timeout", 30)]),
        OD([("type", "static_route"), ("prefix", "10.99.0.0/24"),
            ("next_hop", "10.1.0.1"), ("ad", 200), ("tag", 100)]),
        OD([("acl_name", "PROTECT-RE"), ("seq", 10), ("action", "permit"),
            ("protocol", "tcp"), ("src", "10.100.0.0/24"), ("dst", "any")]),
        OD([("tunnel_id", 1), ("destination", "10.0.0.99"),
            ("bandwidth", "1g"), ("path_type", "dynamic"), ("timeout", 30)]),
        OD([("host", "10.100.4.0"), ("port", 49),
            ("key_encrypted", "0F5A3E7C"), ("timeout", 10)]),
    ]

    for fi in range(NUM_FILES):
        doc = OD([("config_block", variants[fi])])
        write_yaml(os.path.join(set_dir, "input", f"{HOSTS[fi]}.yaml"), doc)

    # Tier B — empty
    write_yaml(os.path.join(set_dir, "golden", "tier_b.yaml"), OD())

    # Tier C — raw passthrough
    for fi in range(NUM_FILES):
        tc = OD([("config_block", variants[fi])])
        write_yaml(os.path.join(set_dir, "golden", "tier_c", f"{HOSTS[fi]}.yaml"), tc)

    write_yaml(os.path.join(set_dir, "expected.yaml"), {
        "positive_sections": [],
        "negative_sections": ["config_block"],
        "classes": {},
        "traps": {
            "config_block": {
                "expected_classes": 0,
                "reason": "heterogeneous",
                "incidental_overlap": ["timeout", "protocol"],
            },
        },
    })


# ═══════════════════════════════════════════════════════════════════════
# SET G — Ordered List
# ═══════════════════════════════════════════════════════════════════════
def gen_set_g(out_dir):
    set_dir = os.path.join(out_dir, "set_g")

    canonical = ["drain_traffic", "snapshot_config", "backup_database",
                 "apply_patches", "restart_services", "validate_health",
                 "run_smoke_tests", "restore_traffic", "notify_stakeholders",
                 "close_ticket"]

    for fi in range(NUM_FILES):
        steps = list(canonical)
        if fi == 3:
            steps[3], steps[4] = steps[4], steps[3]
        doc = OD([("maintenance_schedule", OD([
            ("approval_required", True),
            ("steps", steps),
        ]))])
        write_yaml(os.path.join(set_dir, "input", f"{HOSTS[fi]}.yaml"), doc)

    # Tier B
    write_yaml(os.path.join(set_dir, "golden", "tier_b.yaml"),
               OD([("MaintenanceSchedule", OD([
                   ("approval_required", True),
                   ("steps", canonical),
               ]))]))

    # Tier C
    for fi in range(NUM_FILES):
        if fi == 3:
            swapped = list(canonical)
            swapped[3], swapped[4] = swapped[4], swapped[3]
            tc = OD([("maintenance_schedule", OD([
                ("approval_required", True),
                ("steps", swapped),
            ]))])
        else:
            tc = OD([("maintenance_schedule", OD([("_class", "MaintenanceSchedule")]))])
        write_yaml(os.path.join(set_dir, "golden", "tier_c", f"{HOSTS[fi]}.yaml"), tc)

    write_yaml(os.path.join(set_dir, "expected.yaml"), {
        "positive_sections": ["maintenance_schedule"],
        "negative_sections": [],
        "classes": {
            "maintenance_schedule": {
                "class_name": "MaintenanceSchedule",
                "class_count": 1,
                "hosts_matching": ["rtr-00", "rtr-01", "rtr-02", "rtr-04"],
                "hosts_raw": ["rtr-03"],
                "raw_reason": "list_reorder",
            },
        },
    })


# ═══════════════════════════════════════════════════════════════════════
# SET L — Repeating Entities (Interfaces)
# ═══════════════════════════════════════════════════════════════════════
def gen_set_l(out_dir):
    set_dir = os.path.join(out_dir, "set_l")

    for fi in range(NUM_FILES):
        interfaces = []
        for port in range(8):
            iface = OD([
                ("name", f"GigE0/0/0/{port}"),
                ("ipv4_address", f"10.0.{fi}.{port + 1}"),
                ("mtu", 9000), ("speed", "10g"), ("duplex", "full"),
                ("admin_state", "up"), ("isis_metric", 10), ("mpls_ldp", True),
            ])
            if fi == 2 and port == 6:
                iface["speed"] = "1g"
            if fi == 3 and port == 7:
                del iface["mpls_ldp"]
            interfaces.append(iface)
        doc = OD([("interfaces", interfaces)])
        write_yaml(os.path.join(set_dir, "input", f"{HOSTS[fi]}.yaml"), doc)

    # Tier B
    write_yaml(os.path.join(set_dir, "golden", "tier_b.yaml"),
               OD([("InterfaceConfig", OD([
                   ("mtu", 9000), ("speed", "10g"), ("duplex", "full"),
                   ("admin_state", "up"), ("isis_metric", 10), ("mpls_ldp", True),
                   ("_identity", ["name", "ipv4_address"]),
               ]))]))

    # Tier C
    for fi in range(NUM_FILES):
        instances = []
        for port in range(8):
            inst = OD([("name", f"GigE0/0/0/{port}"),
                       ("ipv4_address", f"10.0.{fi}.{port + 1}")])
            if fi == 2 and port == 6:
                inst["speed"] = "1g"
            if fi == 3 and port == 7:
                inst["_remove"] = ["mpls_ldp"]
            instances.append(inst)
        tc = OD([("interfaces", OD([
            ("_class", "InterfaceConfig"),
            ("instances", instances),
        ]))])
        write_yaml(os.path.join(set_dir, "golden", "tier_c", f"{HOSTS[fi]}.yaml"), tc)

    write_yaml(os.path.join(set_dir, "expected.yaml"), {
        "positive_sections": ["interfaces"],
        "negative_sections": [],
        "classes": {
            "interfaces": {
                "class_name": "InterfaceConfig",
                "class_count": 1,
                "static_field_count": 6,
                "identity_fields": ["name", "ipv4_address"],
                "instance_count_per_host": 8,
                "overrides": [{"host": "rtr-02", "instance": 6, "field": "speed", "value": "1g"}],
                "removals": [{"host": "rtr-03", "instance": 7, "field": "mpls_ldp"}],
            },
        },
    })


# ═══════════════════════════════════════════════════════════════════════
# SET M — Nested Overrides + Trap 4 (Same Children Different Parents)
# ═══════════════════════════════════════════════════════════════════════
def gen_set_m(out_dir):
    set_dir = os.path.join(out_dir, "set_m")

    base_sp = lambda: OD([
        ("interval", 30), ("retry", 3),
        ("telemetry", OD([("interval", 30), ("protocol", "grpc"),
                          ("encoding", "gpb"), ("collectors", ["10.0.0.1", "10.0.0.2"])])),
        ("logging", OD([("interval", 60), ("facility", "local6"),
                        ("severity", "informational")])),
    ])

    trap4_parents = ["telemetry", "sflow", "netflow", "streaming", "diagnostics"]

    inputs = []
    # rtr-00: matches base exactly
    sp0 = base_sp()
    inputs.append(sp0)
    # rtr-01: scalar override + list replace
    sp1 = base_sp()
    sp1["interval"] = 60
    sp1["telemetry"]["collectors"] = ["10.0.0.3", "10.0.0.4", "10.0.0.5"]
    inputs.append(sp1)
    # rtr-02: multi-depth + new subtree
    sp2 = base_sp()
    sp2["interval"] = 60
    sp2["telemetry"]["encoding"] = "json"
    sp2["telemetry"]["auth"] = OD([("method", "certificate"),
                                    ("ca", "/etc/pki/ca.pem"), ("verify", True)])
    inputs.append(sp2)
    # rtr-03: subtree removal
    sp3 = base_sp()
    del sp3["logging"]
    inputs.append(sp3)
    # rtr-04: combo
    sp4 = base_sp()
    sp4["interval"] = 60
    del sp4["telemetry"]["encoding"]
    sp4["telemetry"]["collectors"] = ["10.0.0.9"]
    sp4["logging"]["interval"] = 120
    inputs.append(sp4)

    for fi in range(NUM_FILES):
        trap4_child = OD([("interval", 30), ("protocol", "grpc"), ("encoding", "gpb")])
        doc = OD([
            ("service_config", OD([("service_policy", inputs[fi])])),
            ("export_policy", OD([("service_policy", OD([(trap4_parents[fi], trap4_child)]))])),
        ])
        write_yaml(os.path.join(set_dir, "input", f"{HOSTS[fi]}.yaml"), doc)

    # Tier B
    write_yaml(os.path.join(set_dir, "golden", "tier_b.yaml"),
               OD([("ServiceConfig", OD([("service_policy", base_sp())]))]))

    # Tier C
    tier_c_data = [
        OD([("_class", "ServiceConfig")]),
        OD([(  "_class", "ServiceConfig"),
            (DotKey("service_policy.interval"), 60),
            (DotKey("service_policy.telemetry.collectors"), ["10.0.0.3", "10.0.0.4", "10.0.0.5"])]),
        OD([("_class", "ServiceConfig"),
            (DotKey("service_policy.interval"), 60),
            (DotKey("service_policy.telemetry.encoding"), "json"),
            (DotKey("service_policy.telemetry.auth.method"), "certificate"),
            (DotKey("service_policy.telemetry.auth.ca"), "/etc/pki/ca.pem"),
            (DotKey("service_policy.telemetry.auth.verify"), True)]),
        OD([("_class", "ServiceConfig"),
            ("_remove", ["service_policy.logging"])]),
        OD([("_class", "ServiceConfig"),
            (DotKey("service_policy.interval"), 60),
            (DotKey("service_policy.logging.interval"), 120),
            (DotKey("service_policy.telemetry.collectors"), ["10.0.0.9"]),
            ("_remove", ["service_policy.telemetry.encoding"])]),
    ]

    for fi in range(NUM_FILES):
        trap4_child = OD([("interval", 30), ("protocol", "grpc"), ("encoding", "gpb")])
        tc = OD([
            ("service_config", tier_c_data[fi]),
            ("export_policy", OD([("service_policy", OD([(trap4_parents[fi], trap4_child)]))])),
        ])
        write_yaml(os.path.join(set_dir, "golden", "tier_c", f"{HOSTS[fi]}.yaml"), tc)

    write_yaml(os.path.join(set_dir, "expected.yaml"), {
        "positive_sections": ["service_config"],
        "negative_sections": ["export_policy"],
        "classes": {
            "service_config": {
                "class_name": "ServiceConfig",
                "class_count": 1,
                "dot_notation_operations": {
                    "rtr-00": "none",
                    "rtr-01": "scalar_override + list_replace",
                    "rtr-02": "multi_depth_override + subtree_add",
                    "rtr-03": "subtree_remove",
                    "rtr-04": "scalar_override + list_replace + field_remove",
                },
            },
        },
        "traps": {
            "export_policy": {
                "expected_classes": 0,
                "reason": "same_children_different_parents",
            },
        },
    })


# ═══════════════════════════════════════════════════════════════════════
# SET N — Partial Classification
# ═══════════════════════════════════════════════════════════════════════
def gen_set_n(out_dir):
    set_dir = os.path.join(out_dir, "set_n")

    group1 = OD([
        ("asn", 65000), ("router_id_source", "loopback0"),
        ("address_family", "ipv4-unicast"), ("bestpath", "as-path-multipath-relax"),
        ("graceful_restart", True), ("graceful_restart_time", 120),
        ("max_paths_ebgp", 8), ("max_paths_ibgp", 8),
    ])
    group2 = OD([
        ("asn", 65000), ("router_id_source", "loopback0"),
        ("address_family", "vpnv4-unicast"), ("bestpath", "compare-routerid"),
        ("graceful_restart", False), ("max_paths_ebgp", 2),
        ("confederation_id", 100), ("confederation_peers", [65001, 65002]),
    ])
    outlier = OD([
        ("asn", 65100), ("router_id_source", "loopback1"),
        ("address_family", "ipv6-unicast"), ("bestpath", "as-path-multipath-relax"),
        ("graceful_restart", True), ("graceful_restart_time", 300),
        ("max_paths_ebgp", 16), ("bfd_enabled", True), ("bfd_interval", 150),
    ])
    assignments = [group1, group1, group2, group2, outlier]

    for fi in range(NUM_FILES):
        doc = OD([("bgp_policy", OD(assignments[fi]))])
        write_yaml(os.path.join(set_dir, "input", f"{HOSTS[fi]}.yaml"), doc)

    # Tier B — two classes
    write_yaml(os.path.join(set_dir, "golden", "tier_b.yaml"),
               OD([("BgpPolicyCore", OD(group1)),
                   ("BgpPolicyVpn", OD(group2))]))

    # Tier C
    class_map = ["BgpPolicyCore", "BgpPolicyCore", "BgpPolicyVpn", "BgpPolicyVpn", None]
    for fi in range(NUM_FILES):
        if class_map[fi]:
            tc = OD([("bgp_policy", OD([("_class", class_map[fi])]))])
        else:
            tc = OD([("bgp_policy", OD(outlier))])
        write_yaml(os.path.join(set_dir, "golden", "tier_c", f"{HOSTS[fi]}.yaml"), tc)

    write_yaml(os.path.join(set_dir, "expected.yaml"), {
        "positive_sections": ["bgp_policy"],
        "negative_sections": [],
        "classes": {
            "bgp_policy": {
                "class_count": 2,
                "class_names": ["BgpPolicyCore", "BgpPolicyVpn"],
                "group_1": ["rtr-00", "rtr-01"],
                "group_2": ["rtr-02", "rtr-03"],
                "raw_hosts": ["rtr-04"],
                "shared_fields_not_merged": ["asn", "router_id_source"],
            },
        },
    })


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════
GENERATORS = [
    ("set_a", gen_set_a),
    ("set_b", gen_set_b),
    ("set_c", gen_set_c),
    ("set_d", gen_set_d),
    ("set_e", gen_set_e),
    ("set_g", gen_set_g),
    ("set_l", gen_set_l),
    ("set_m", gen_set_m),
    ("set_n", gen_set_n),
]


def main():
    parser = argparse.ArgumentParser(description="Generate per-set archetypal fixtures")
    parser.add_argument("--out-dir", default=".", help="Output directory")
    args = parser.parse_args()

    for name, gen_fn in GENERATORS:
        gen_fn(args.out_dir)
        # Count files
        input_dir = os.path.join(args.out_dir, name, "input")
        golden_dir = os.path.join(args.out_dir, name, "golden")
        n_input = len([f for f in os.listdir(input_dir) if f.endswith(".yaml")])
        n_golden_c = len([f for f in os.listdir(os.path.join(golden_dir, "tier_c")) if f.endswith(".yaml")])
        print(f"  {name:10s}  {n_input} input files, tier_b + {n_golden_c} tier_c files")

    print(f"\n  {len(GENERATORS)} sets generated in {args.out_dir}/")


if __name__ == "__main__":
    main()
