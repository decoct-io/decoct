0. Generation Sanity

 Generator exits cleanly with no errors
 Output reports: 10 input files, 13 classes in tier_b
 Absence report matches:

rtr-03: 14 sections (absent: change_procedures)
rtr-05: 14 sections (absent: fabric_interfaces)
rtr-06: 13 sections (absent: access_control, change_procedures)
rtr-07: 14 sections (absent: fabric_interfaces)
rtr-09: 14 sections (absent: access_control)
All others: 15 sections


 Directory structure exists:

input/rtr-00.yaml through input/rtr-09.yaml
golden/tier_b.yaml
golden/tier_c/rtr-00.yaml through golden/tier_c/rtr-09.yaml
expected.yaml




1. Global Structural Checks
1.1 Input files

 rtr-00 input has exactly 15 top-level keys
 rtr-06 input has exactly 13 top-level keys
 access_control key is absent from rtr-06 and rtr-09 input files
 change_procedures key is absent from rtr-03 and rtr-06 input files
 fabric_interfaces key is absent from rtr-05 and rtr-07 input files
 Every input file has all 3 trap sections: auth_methods, vendor_extensions, path_export
 List-type sections (fabric_interfaces, vrf_routing, bgp_neighbors) are YAML lists of dicts in input
 All other sections are YAML dicts

1.2 Tier B

 Tier B has exactly 13 top-level keys (class definitions)
 Class names: SystemBase, AccessPolicy, AlertTarget, Loopback0Config, ChangeProcedure, FabricInterface, TelemetryStack, RoutingPolicyCore, RoutingPolicyVpn, IsisConfig, VrfConfig, PolicyMap, BgpNeighborConfig
 No duplicate class names
 No class name collides with a section name

1.3 Tier C

 rtr-00 tier_c has exactly 15 top-level keys
 rtr-06 tier_c has exactly 13 top-level keys
 Every section present in a host's input is also present in that host's tier_c
 No section appears in tier_c that is absent from input
 Positive sections in tier_c have _class (or are raw where expected)
 Negative sections in tier_c have NO _class

1.4 Round-trip reconstruction

 For every host × every section present: reconstruct(tier_b, tier_c) == input
 Total: 144 host×section checks, 0 failures


2. S1: system_base — Overlap
Expected: 1 class SystemBase, 16 static fields, _identity: [snmp_location]
Tier B checks

 Class SystemBase exists in tier_b
 Has exactly 16 fields (excluding _identity)
 _identity: [snmp_location] is present
 snmp_location is NOT among the 16 static fields
 Fields include: ntp_primary, ntp_secondary, ntp_source, ntp_auth_enabled, ntp_auth_key_id, ntp_auth_algo, log_host, log_protocol, log_port, log_facility, log_severity, log_buffer, aaa_login, aaa_enable, radius_host_1, snmp_community

Tier C checks

 All 10 hosts have system_base._class: SystemBase
 Each host has snmp_location with a unique value
 rtr-00: snmp_location: site-00
 rtr-09: snmp_location: site-09
 No other fields present in any host's tier_c for this section (only _class + snmp_location)

Reconstruction

 rtr-00: reconstruct gives 17 fields (16 static + snmp_location)
 rtr-05: reconstruct gives identical static fields, different snmp_location


3. S2: access_control — Subtraction
Expected: 1 class AccessPolicy, 14 fields, progressive _remove
Tier B checks

 Class AccessPolicy exists with exactly 14 fields
 Fields include: policy_name, default_action, log_denied, rate_limit, timeout, icmp_allow, ssh_allow, snmp_allow, ntp_allow, bgp_allow, ldp_allow, rsvp_allow, bfd_allow, tacacs_allow
 timeout value is 30 (integer, not string)

Tier C checks

 Section absent from rtr-06 and rtr-09 tier_c files
 8 remaining hosts all have _class: AccessPolicy
 rtr-00: no _remove (exact class match)
 rtr-01: _remove: [tacacs_allow] (1 removal)
 rtr-02: _remove: [tacacs_allow, bfd_allow] (2 removals)
 rtr-03: 3 removals
 rtr-04: 4 removals
 rtr-05: 5 removals
 rtr-07: 6 removals
 rtr-08: 7 removals (removes half the class)
 Each host's _remove is a superset of the previous host's

Reconstruction

 rtr-00 reconstructs to 14 fields
 rtr-08 reconstructs to 7 fields (14 − 7)
 rtr-04 reconstructs to 10 fields (14 − 4)


4. S3: alert_targets — Addition
Expected: 1 class AlertTarget, 5 static fields, progressive additions
Tier B checks

 Class AlertTarget with exactly 5 fields
 Fields: polling_interval (300), timeout (10), retries (3), threshold_warn (75), threshold_crit (95)
 timeout value is 10 (NOT 30 — cross-section isolation from access_control)

Tier C checks

 All 10 hosts have _class: AlertTarget
 rtr-00: _class only (0 additions)
 rtr-01: _class + threshold_info: 50 (1 addition)
 rtr-04: 4 extra fields
 rtr-09: 9 extra fields
 Each host's extras are a superset of the previous host's
 Extra fields include (progressively): threshold_info, escalation_group, suppress_flap, correlation_id, dependency_check, auto_ticket, severity_override, notification_channel, runbook_url

Reconstruction

 rtr-00: 5 fields
 rtr-09: 14 fields (5 + 9)


5. S4: loopback0 — Identity
Expected: 1 class Loopback0Config, 10 static fields, _identity: [ipv4_address]
Tier B checks

 Class Loopback0Config with 10 fields + _identity: [ipv4_address]
 Fields include: interface_type (Loopback), description (Router-ID), mtu (1500), admin_state (up), vrf (default), isis_passive (true), isis_metric (10), mpls_ldp (true), mpls_te (false), bfd_enabled (true)

Tier C checks

 All 10 hosts have _class: Loopback0Config
 Each host has ipv4_address with unique value
 rtr-00: ipv4_address: 10.255.0.0
 rtr-09: ipv4_address: 10.255.0.9
 No two hosts share an ipv4_address
 Only _class + ipv4_address in tier_c (no extra fields)


6. S5: change_procedures — Ordered List
Expected: 1 class ChangeProcedure, 7 match, 1 deviant (rtr-05), 2 absent
Tier B checks

 Class ChangeProcedure exists
 Has approval_required: true
 Has max_duration_hours: 4
 Has steps list with 12 items in canonical order
 Steps 5 and 6 are apply_patches then restart_services

Tier C checks

 Section absent from rtr-03 and rtr-06
 rtr-00, rtr-01, rtr-02, rtr-04, rtr-07, rtr-08, rtr-09: _class: ChangeProcedure (7 hosts)
 rtr-05: NO _class key — full raw data inline
 rtr-05 raw data has approval_required: true and steps list
 rtr-05 steps have restart_services BEFORE apply_patches (positions 4 and 5 swapped)
 rtr-05 raw data is complete (all fields present, not a partial)

Reconstruction

 rtr-00: matches class exactly
 rtr-05: raw data matches input exactly (swap preserved)


7. S6: fabric_interfaces — Instances
Expected: 1 class FabricInterface, 5 static fields, _identity: [name, ipv4_address], 32 instances
Tier B checks

 Class FabricInterface with 5 fields: mtu (9216), speed (100g), duplex (full), admin_state (up), isis_metric (10)
 _identity: [name, ipv4_address]

Tier C checks

 Section absent from rtr-05 and rtr-07
 8 remaining hosts all have _class: FabricInterface + instances list
 Each host has exactly 4 instances
 Each instance has name and ipv4_address (identity fields)
 rtr-00 instance 0: name: HuGigE0/0/0/0, ipv4_address: 10.10.0.1
 rtr-02 instance 2: has speed: 10g (override — class has 100g)
 rtr-08 instance 3: has _remove: [isis_metric] (removal)
 All other instances have ONLY identity fields (no overrides, no removals)
 Count: 30 identity-only instances + 1 with override + 1 with removal = 32 total

Reconstruction

 rtr-02 instance 2: reconstructed has speed: 10g (not 100g)
 rtr-08 instance 3: reconstructed has no isis_metric field
 rtr-00 instance 0: reconstructed has all 7 fields (5 static + 2 identity)


8. S7: telemetry_stack — Dot Notation
Expected: 1 class TelemetryStack, 6 matching hosts, 4 with dot-notation ops
Tier B checks

 Class TelemetryStack exists with nested structure
 Top-level keys: global_interval (30), retry (3), transport, collectors, logging
 transport.tls.cipher is aes-256-gcm
 collectors is a 2-element list: ["10.200.0.1", "10.200.0.2"]
 logging.interval is 60

Tier C checks — matching hosts

 rtr-00, rtr-05, rtr-06, rtr-07, rtr-08, rtr-09: _class: TelemetryStack only (no overrides)

Tier C checks — override hosts

 rtr-01: has dot-key global_interval: 60 (depth-1 scalar override)
 rtr-02: has dot-key transport.tls.cipher: aes-128-gcm (depth-3 override)
 rtr-03: has _remove: [logging] (entire subtree removal)
 rtr-04: has global_interval: 60 + collectors: ["10.200.0.9"] + _remove: [transport.tls.cipher]

Key assertions

 Dot-notation keys are YAML strings with dots in them (e.g. 'transport.tls.cipher'), NOT nested YAML
 rtr-03 removal targets logging (subtree), not individual fields within logging
 rtr-04 combines override, list replacement, and removal in one entry

Reconstruction

 rtr-01: global_interval is 60 (not 30), everything else matches class
 rtr-02: transport.tls.cipher is aes-128-gcm, everything else matches
 rtr-03: no logging key in reconstruction at all
 rtr-04: global_interval: 60, collectors: ["10.200.0.9"], no transport.tls.cipher


9. S8: routing_policy — Partial Classification
Expected: 2 classes, 4-4-2 split (group A, group B, outliers)
Tier B checks

 RoutingPolicyCore exists with 9 fields
 RoutingPolicyVpn exists with 9 fields
 Both share asn: 65000 and router_id_source: loopback0 — these are NOT the reason they're separate classes
 RoutingPolicyCore: address_family: ipv4-unicast, graceful_restart: true
 RoutingPolicyVpn: address_family: vpnv4-unicast, graceful_restart: false

Tier C checks

 rtr-00, rtr-01, rtr-02, rtr-03: _class: RoutingPolicyCore (group A)
 rtr-04, rtr-05, rtr-07, rtr-08: _class: RoutingPolicyVpn (group B)
 rtr-06: NO _class — raw data inline, has asn: 65100, address_family: ipv6-unicast
 rtr-09: NO _class — raw data inline, has asn: 65200, address_family: l2vpn-evpn
 No host has any overrides within routing_policy (all group members match class exactly)

Outlier checks

 rtr-06 raw data has 9 fields (different schema from both groups)
 rtr-09 raw data has 8 fields (yet another different schema)
 Neither outlier has confederation_id or max_paths_ibgp


10. S9: isis_config — Compound: Identity + Removal + Override
Expected: 1 class IsisConfig, 12 static fields, _identity: [net_address], compound ops
Tier B checks

 Class IsisConfig with 12 fields + _identity: [net_address]
 Fields include: process_id (1), is_type (level-2-only), metric_style (wide), net_area (49.0001), auth_type (md5), auth_password (ISIS_KEY_1), lsp_gen_interval (5), lsp_refresh (900), lsp_lifetime (1200), spf_interval (10), spf_initial_wait (50), max_lsp_lifetime (65535)

Tier C checks — identity-only hosts

 rtr-00, rtr-01, rtr-04, rtr-05, rtr-07, rtr-08, rtr-09: _class: IsisConfig + net_address only (7 hosts)
 Each net_address is unique (49.0001.0100.0000.XXXX.00 pattern)

Tier C checks — compound hosts

 rtr-02: _class + net_address + _remove: [auth_password] — identity AND removal
 rtr-03: _class + net_address + metric_style: narrow — identity AND override
 rtr-06: _class + net_address + _remove: [spf_interval, lsp_refresh] — identity AND 2 removals

Reconstruction

 rtr-02: has all fields EXCEPT auth_password (12 static − 1 removal + 1 identity = 12 fields)
 rtr-03: has all 13 fields but metric_style is narrow (not wide)
 rtr-06: has all fields EXCEPT spf_interval and lsp_refresh (12 − 2 + 1 = 11 fields)
 rtr-00: has all 13 fields with class defaults


11. S10: vrf_routing — Compound: Instances + Identity + Override + Removal
Expected: 1 class VrfConfig, 5 static, _identity: [vrf_name, rd_value], 30 instances
Tier B checks

 Class VrfConfig with 5 fields: rd_format (type0), import_policy (VRF-IMPORT), export_policy (VRF-EXPORT), route_limit (10000), route_warning_pct (80)
 _identity: [vrf_name, rd_value]

Tier C checks

 All 10 hosts have _class: VrfConfig + instances list
 Each host has exactly 3 instances
 Each instance has vrf_name and rd_value (identity fields)
 VRF names are CUST-A, CUST-B, MGMT on every host
 rd_value is unique per host-VRF combination

Per-instance exception checks

 rtr-03 instance 1 (CUST-B): has route_limit: 5000 (override, class has 10000)
 rtr-04 instance 2 (MGMT): has _remove: [route_warning_pct] (removal)
 All other 28 instances: identity fields ONLY

Reconstruction

 rtr-03 CUST-B: route_limit is 5000 (not 10000)
 rtr-04 MGMT: no route_warning_pct field at all
 rtr-00 CUST-A: all 7 fields (5 static + 2 identity)


12. S11: policy_maps — Compound: Dot Notation + Subtraction + Addition
Expected: 1 class PolicyMap, nested structure, 6 matching + 4 with ops
Tier B checks

 Class PolicyMap exists with nested policy structure
 policy.name: CORE-RM
 policy.match has: prefix_list, community, as_path
 policy.set has: local_pref (200), med (100), community (65000:100)

Tier C checks — matching hosts

 rtr-00, rtr-03, rtr-05, rtr-06, rtr-08, rtr-09: _class: PolicyMap only

Tier C checks — operation hosts

 rtr-01: policy.match.as_path: EDGE-ASPATH (dot override)
 rtr-02: _remove: [policy.set.med] + policy.set.weight: 200 (dot removal + dot addition)
 rtr-04: policy.match.prefix_list: EDGE-PREFIXES + policy.dampening.half_life: 15 + policy.dampening.reuse: 750 (override + subtree addition)
 rtr-07: policy.default_action: permit + policy.set.local_pref: 300 + _remove: [policy.set.community] (3 operations combined)

Key assertions

 rtr-02 has BOTH a removal and an addition in the same host entry
 rtr-04's policy.dampening.* keys are additions (not in class at all) — this is subtree creation via per-leaf dot keys
 rtr-07 has 3 different operation types in one entry

Reconstruction

 rtr-01: policy.match.as_path is EDGE-ASPATH, everything else matches class
 rtr-02: policy.set has no med, has new weight: 200
 rtr-04: policy.match.prefix_list is EDGE-PREFIXES, policy.dampening subtree exists with 2 fields
 rtr-07: policy.default_action is permit, policy.set.local_pref is 300, policy.set has no community


13. S12: bgp_neighbors — Compound: Instances + Dot Notation
Expected: 1 class BgpNeighborConfig, nested class structure, 30 instances, dot-notation within instances
Tier B checks

 Class BgpNeighborConfig exists with nested structure
 Top-level groups: remote_as (65001), transport, timers, afi
 transport.md5_auth: true
 timers.connect_retry: 10
 timers.hold: 90
 afi.vpnv4: false
 _identity: [peer_name, peer_address]

Tier C checks

 All 10 hosts have _class: BgpNeighborConfig + instances
 Each host has 3 instances (PE-01, PE-02, PE-03)
 peer_address values are unique per host

Instance dot-notation override checks

 rtr-01, instance 1 (PE-02): has transport.md5_auth: false as a dot-key (NOT nested YAML)
 rtr-04, instance 0 (PE-01): has afi.vpnv4: true as a dot-key

Instance dot-notation removal checks

 rtr-02, instance 2 (PE-03): has _remove: [timers.connect_retry]
 rtr-08, instance 1 (PE-02): has _remove: [timers.hold]

Key assertions

 Dot-notation keys within instances are YAML strings containing dots (e.g. 'transport.md5_auth': false), not nested structures
 Dot-notation removals within instances reference paths (e.g. timers.connect_retry), not flat field names
 26 out of 30 instances are identity-only (no overrides, no removals)

Reconstruction

 rtr-01 PE-02: transport subtree has md5_auth=false, everything else matches class
 rtr-02 PE-03: timers subtree has no connect_retry, keepalive and hold still present
 rtr-04 PE-01: afi subtree has vpnv4=true (not false)
 rtr-08 PE-02: timers subtree has no hold, keepalive and connect_retry still present
 rtr-00 PE-01: all fields match class + identity fields present


14. T1: auth_methods — Trap: Type Coercion
Expected: 0 classes, raw passthrough, type diversity preserved
Structural checks

 No class references anywhere in this section across all 10 hosts
 Every host's tier_c for auth_methods is identical to its input

Type preservation (check exact Python types after yaml.safe_load)

 rtr-00.mfa_enabled: True (bool)
 rtr-01.mfa_enabled: "true" (str)
 rtr-02.timeout: "30" (str, not int)
 rtr-03.mfa_enabled: 1 (int, not bool)
 rtr-03.max_retries: "3" (str, not int)
 rtr-04.method: "RADIUS" (str, uppercase — different from "radius" on other hosts)
 rtr-05.mfa_enabled: "yes" (str)
 rtr-07.mfa_enabled: "on" (str)
 rtr-09.mfa_enabled: 0 (int)

False-positive check

 rtr-00, rtr-06, rtr-08 are byte-identical — verify no class was extracted from this 3-host subset


15. T2: vendor_extensions — Trap: Heterogeneous
Expected: 0 classes, raw passthrough, different schemas per host
Structural checks

 No class references anywhere in this section
 Every host's tier_c matches input exactly

Schema diversity

 rtr-00: has secret_enc field (RADIUS schema)
 rtr-01: has key_enc field (TACACS schema)
 rtr-03: has algorithm field (NTP auth schema)
 rtr-07: has primary, secondary fields (DNS schema)
 rtr-08: has min_rx field (BFD schema)

Incidental overlap verification

 host appears in rtr-00, rtr-01, rtr-02, rtr-04 (4 hosts) — did NOT trigger class extraction
 port appears in rtr-00, rtr-01, rtr-02, rtr-04, rtr-05 (5 hosts) — did NOT trigger
 timeout appears in rtr-00, rtr-01, rtr-04 (3 hosts) — did NOT trigger


16. T3: path_export — Trap: Same Children, Different Parents
Expected: 0 classes, raw passthrough
Structural checks

 No class references anywhere in this section
 Every host's tier_c matches input exactly

Leaf/path verification

 All 10 hosts have identical leaf values: interval: 30, protocol: grpc, encoding: gpb
 All 10 hosts have DIFFERENT parent keys under export_policy:

rtr-00: telemetry_export
rtr-01: sflow_export
rtr-02: netflow_export
rtr-03: ipfix_export
rtr-04: streaming_export
rtr-05: tap_export
rtr-06: mirror_export
rtr-07: span_export
rtr-08: erspan_export
rtr-09: pcap_export


 Leaf-level Jaccard would be 1.0 but full-path Jaccard is 0.0 — no compression triggered


17. Cross-Section Isolation
17.1 Field name collision: timeout

 AccessPolicy.timeout = 30 (in tier_b)
 AlertTarget.timeout = 10 (in tier_b)
 These are in different classes with different values — no cross-contamination
 timeout also appears in auth_methods (trap, value 30) — did NOT merge with access_control
 timeout also appears in vendor_extensions (trap, values 5/10) — stayed raw

17.2 Overlapping group membership

 rtr-03: group A for routing_policy, identity+override for isis_config, instance override for vrf_routing — three different roles
 rtr-06: raw outlier for routing_policy, identity+2removals for isis_config, class match for telemetry — three different roles
 rtr-05: deviant (raw) for change_procedures, group B for routing_policy, class match for telemetry — three different roles
 Verify: no host's class assignment in one section affects its assignment in another

17.3 Adjacent positive + negative

 system_base (positive, compressed) and auth_methods (trap, raw) coexist in every host file
 auth_methods type diversity did NOT infect system_base class extraction
 system_base successful compression did NOT cause auth_methods to be compressed

17.4 Absent section neighbours

 rtr-05: absent from fabric_interfaces, but all other 14 sections are correct
 rtr-06: absent from 2 sections, remaining 13 all correct
 No "phantom" sections appear in tier_c for absent sections


18. Optimality Verification
18.1 No Tier C redundancy
For each positive section, every field in a host's tier_c (excluding _class, _remove, instances) must genuinely differ from the class:

 Pick 3 random host×section pairs — verify no field in tier_c duplicates a class value
 Specifically check: rtr-00 system_base has only _class + snmp_location (not any of the 16 static fields repeated)

18.2 No Tier B redundancy
Every field in a class must appear with that value on ≥2 hosts:

 SystemBase: 16 fields, all appear on all 10 hosts → each appears 10× ✓
 AccessPolicy: 14 fields, rtr-08 removes 7 → even the most-removed field (tacacs_allow) appears on 1 host unreduced — CHECK: does tacacs_allow appear on ≥2 hosts with the class value? rtr-00 has it. Who else? rtr-01 removes only tacacs_allow... wait, rtr-01 removes tacacs_allow too. Verify: at least rtr-00 keeps all 14 → only 1 host retains tacacs_allow unreduced. Is this a problem? No — the class is the superset; _remove handles the rest. The Tier B redundancy check is: does the field VALUE match on ≥2 hosts. rtr-00 has tacacs_allow=true. The class has tacacs_allow=true. So at least 1 host inherits the value. Actually the check should be: ≥2 hosts where the field is not removed and not overridden. For tacacs_allow, that's only rtr-00. Flag this for review.
 IsisConfig: auth_password appears on all hosts except rtr-02 (removed) → 9 hosts retain it ✓

18.3 No missed extraction

 No group of ≥3 hosts in any negative section shares ≥5 identical fields
 auth_methods: rtr-00/06/08 share 4 fields identically — below threshold ✓
 vendor_extensions: max shared fields between any 3 hosts is ~2 (host, port) — well below ✓


19. expected.yaml Verification

 positive_sections lists exactly 12 sections
 negative_sections lists exactly 3 sections
 absent_sections maps match the actual absent hosts
 Every class entry has correct class_name and class_count
 routing_policy entry has class_count: 2 and both class names
 All hosts lists match actual present hosts
 removal_progression for access_control: [0, 1, 2, 3, 4, 5, 6, 7]
 addition_progression for alert_targets: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
 instance_dot_overrides and instance_dot_removals for bgp_neighbors list all 4 exceptions


20. File Size / Compression Ratio

 Total input lines: ~2200 (all 10 files)
 Total tier_b lines: ~170
 Total tier_c lines: ~780 (all 10 files)
 Compression ratio: input / (tier_b + tier_c) ≈ 2.3×
 tier_c files for full-coverage hosts (~67 lines) are significantly smaller than input files (~233 lines)
 tier_c files for absent-section hosts are even smaller


Summary
CheckExpectedActualPass?Generation clean10 files, 13 classesRound-trip (144 checks)0 failuresS1 overlap1 class, 16 fieldsS2 subtraction1 class, progression [0..7]S3 addition1 class, progression [0..9]S4 identity1 class, _identityS5 ordered list1 class, 1 deviantS6 instances1 class, 32 instancesS7 dot notation1 class, 4 dot-notation hostsS8 partial classification2 classes, 2 outliersS9 compound id+rm+ovrd1 class, 3 compound hostsS10 compound inst+id+ovrd+rm1 class, 30 instancesS11 compound dot+sub+add1 class, 4 operation hostsS12 compound inst+dot1 class, 4 instance exceptionsT1 type coercion0 classesT2 heterogeneous0 classesT3 same children diff parents0 classesCross-section timeoutno leakCross-section groupsper-section assignmentAdjacent pos+negno infectionAbsent section isolationno phantoms