# Enterprise Campus Fixture — "Meridian Manufacturing"

Fifth fixture corpus for the entity-graph pipeline. Represents a Fortune 500 industrial
conglomerate's converged campus + branch + datacentre + factory floor network — the
largest and most heterogeneous fixture set, ideal for testing cross-domain type discovery
across SD-WAN, SD-Access, firewalls, DC fabric, and IoT.

## Company: Meridian Manufacturing

Fortune 500 industrial conglomerate. 18,000 employees, $6.2B revenue. Headquarters in
Detroit, Michigan. Primary business: automotive components (body panels, powertrain
assemblies, brake systems). Secondary: industrial automation equipment.

**History:** Founded 1947 as "Meridian Stamping & Tool." Grew through acquisition —
bought CompuForge (factory automation, 2008), bought DataAxis (IT services, 2015).
Publicly traded (NYSE: MRDN) since 1986.

**Network transformation:** In 2024, Meridian began migrating from a legacy MPLS WAN
(AT&T contract, 12 sites) to Cisco SD-WAN (Viptela). Simultaneously deploying SD-Access
(DNA Center + ISE) on the campus. Migration is 70% complete — some sites still run
legacy MPLS with EIGRP, creating a dual-stack mess. The factory floor runs a completely
separate OT network following the Purdue model, converging at L3.5 via industrial
firewalls.

## Sites

| Site Code | Name | Location | Type | WAN |
|---|---|---|---|---|
| `hq` | HQ Campus | Detroit, MI | Campus (3 buildings) | SD-WAN + legacy MPLS |
| `bra` | Branch Austin | Austin, TX | Branch office | SD-WAN |
| `brb` | Branch Boston | Boston, MA | Branch office | SD-WAN + legacy MPLS stub |
| `dc1` | DC East | Ashburn, VA | Datacentre | Direct connect |
| `fac` | Factory Floor | Detroit, MI (adjacent) | Manufacturing | Air-gapped OT + IT DMZ |

## Domain 1: SD-WAN (~25 files)

Cisco SD-WAN (Viptela) overlay. 3 transport circuits per site (MPLS, Internet-1, Internet-2).

| Config Type | Format | Count | Description |
|---|---|---|---|
| sdwan-cedge | YAML | 8 | cEdge routers at each site — VPN templates, OMP, BFD, TLOC |
| sdwan-vsmart | YAML | 3 | vSmart controllers — OMP policy, route filters, control policy |
| sdwan-vbond | YAML | 2 | vBond orchestrators — enrollment, certificate authority config |
| sdwan-policy | JSON | 6 | Centralised policies — app-aware routing, QoS maps, data policy |
| sdwan-template | JSON | 6 | Feature templates — VPN, security, banner, system settings |

**Inconsistencies:**
- HQ cEdges still have legacy EIGRP redistributed into OMP (migration incomplete)
- Branch Boston has an old MPLS TLOC that should have been removed
- One vSmart has debug logging enabled from a troubleshooting session
- SD-WAN policies reference app-lists that don't exist in all templates (stale config)
- Two cEdges use IKEv1 for IPsec (should be IKEv2 — legacy tunnel holdover)

## Domain 2: SD-Access (~35 files)

Cisco SD-Access fabric with DNA Center. Campus uses LISP + VXLAN. ISE for policy.

| Config Type | Format | Count | Description |
|---|---|---|---|
| catalyst-switch | YAML | 12 | Catalyst 9300/9500 — border, edge, control-plane nodes per site |
| wlc-config | JSON | 4 | Cisco 9800 wireless controllers — SSIDs, RF profiles, AP groups |
| ap-group | JSON | 8 | AP group configs — channel plans, power levels, SSID mapping |
| ise-policy | JSON | 6 | ISE policy sets — authZ/authN rules, SGT assignments, profiling |
| sgt-matrix | YAML | 3 | TrustSec SGT-to-SGT egress policy matrix |
| dnac-template | JSON | 2 | DNA Center provisioning templates — day-0 and day-N |

**Inconsistencies:**
- HQ edge switches still have manual VLAN configs alongside SDA fabric (migration)
- Branch Austin ISE policy references an SGT (Plant_OT, tag 50) from factory that
  shouldn't be in campus policy
- Two AP groups have conflicting channel plans (channels 36-48 vs 149-161)
- One WLC still runs 17.3 firmware while others are on 17.9 — different feature set
- Border nodes at HQ have both LISP and legacy EIGRP running (dual-stack transition)

## Domain 3: Firewalls (~25 files)

Mixed-vendor firewalls: Palo Alto at HQ/DC, FortiGate at branches, plus shared objects.

| Config Type | Format | Count | Description |
|---|---|---|---|
| paloalto-fw | YAML | 8 | PA-5260/PA-820 — zones, NAT, security policies, GlobalProtect |
| paloalto-profile | JSON | 6 | Security profiles — URL filtering, threat prevention, decryption |
| fortinet-fw | YAML | 5 | FortiGate 60F/200F — branch FW policies, SD-WAN integration, VPN |
| fw-address-group | JSON | 4 | Shared address objects and groups (cross-referenced) |
| fw-nat-rule | JSON | 2 | NAT rule sets for DC ingress and HQ internet breakout |

**Inconsistencies:**
- Palo Alto uses zone-based policy; FortiGate uses policy-based — different paradigm
- Address group "RFC1918" defined differently on PA (10/8 + 172.16/12 + 192.168/16)
  vs FortiGate (single 10.0.0.0/8 — missing two ranges)
- One PA firewall still has a "trust/untrust" zone pair from initial deployment
  (should be renamed to corp-internal/corp-external)
- FortiGate branch Boston has VPN tunnels to old MPLS PE routers (should be removed)
- Decryption profile enabled on HQ PA but disabled on DC PA (policy mismatch)

## Domain 4: Datacentre (~60 files)

Arista EVPN-VXLAN leaf-spine fabric + bare-metal Linux servers + storage + databases.

| Config Type | Format | Count | Description |
|---|---|---|---|
| arista-leaf | YAML | 12 | Arista 7050X3 leaf switches — EVPN-VXLAN, port-channels |
| arista-spine | YAML | 4 | Arista 7500R spine switches — BGP underlay, ECMP |
| server-bmc | JSON | 8 | Dell iDRAC / HPE iLO — IPMI configs, fan policy, alerts |
| server-netplan | YAML | 8 | Ubuntu netplan — bonds, VLANs, MTU, DNS |
| server-sysctl | INI .conf | 8 | Kernel tuning — TCP, VM, fs parameters |
| server-systemd | INI .conf | 6 | Systemd service units — app services, monitoring agents |
| storage-array | JSON | 4 | NetApp ONTAP / Pure Storage — volumes, LUNs, snapshots |
| db-config | INI .conf | 4 | PostgreSQL + MariaDB — tuning, replication, auth |
| redis-config | INI .conf | 3 | Redis sentinel + cluster configs — persistence, auth |
| lb-config | YAML | 3 | F5 BIG-IP / HAProxy — VIPs, pools, health monitors |

**Inconsistencies:**
- Half the leaf switches use BGP ASN 65001; the other half use 65002 (two-ASN mistake)
- Server BMC configs: Dell hosts use iDRAC9; HPE hosts use iLO5 — different schema shape
- Two servers have MTU 1500 while rest use 9000 (jumbo frames misconfigured)
- One PostgreSQL instance has `ssl = off` (should be on — compliance violation)
- Redis cluster nodes disagree on `maxmemory-policy` (allkeys-lru vs volatile-lru)
- Storage arrays: NetApp uses ONTAP REST API format; Pure uses Purity API format

## Domain 5: IoT Factory Floor (~40 files)

Automotive assembly line — welding robots, paint booth, conveyors, vision inspection.
Follows Purdue model: L0 (sensors) → L1 (PLCs) → L2 (SCADA/HMI) → L3 (MES/historians).

| Config Type | Format | Count | Description |
|---|---|---|---|
| mqtt-broker | JSON | 4 | Mosquitto/EMQX brokers — listeners, ACL, bridge to cloud |
| opcua-server | YAML | 6 | OPC-UA server endpoints — weld cells, paint booth, assembly |
| plc-gateway | JSON | 8 | PLC gateways — Modbus TCP/EtherNet/IP → MQTT translation |
| edge-compute | YAML | 6 | Edge inference nodes — defect detection, predictive maintenance |
| sensor-network | YAML | 8 | Sensor configs — vibration, temperature, torque, pressure |
| industrial-fw | YAML | 4 | Purdue model firewalls — L0-L2 ↔ L3-L5 segmentation |
| historian-config | JSON | 4 | InfluxDB/Kepware — tag databases, retention policies |

**Inconsistencies:**
- Two PLC gateways use Modbus RTU (serial) while rest use Modbus TCP (Ethernet)
- OPC-UA security: weld cells use Sign+Encrypt, paint booth uses None (misconfigured)
- Edge compute nodes disagree on inference model version (v2.1 vs v2.3)
- One MQTT broker has anonymous access enabled (security risk)
- Sensor sample rates vary: vibration at 1kHz, temperature at 1Hz, torque at 100Hz
- Industrial firewall at L2/L3 boundary allows Telnet (should be SSH only)
- Historian retention: InfluxDB uses 90 days; Kepware uses 365 days (inconsistent)

## Secrets (for secret masking testing)

### SD-WAN
- cEdge: IPsec pre-shared keys (`ipsec_psk`), OMP key (`omp_key`)
- vSmart: admin password (`admin_password`), certificate private key path
- vBond: enrollment token (`enrollment_token`), root CA private key reference
- Policy: RADIUS shared secret in embedded AAA config
- Template: SNMP community strings, NTP auth keys

### SD-Access
- Catalyst: enable secret (`enable_secret`), RADIUS shared secret (`radius_key`)
- WLC: management password (`mgmt_password`), AP join passphrase
- ISE: RADIUS shared secrets, TACACS+ keys, admin API token
- DNAC: API bearer tokens, device credentials

### Firewalls
- Palo Alto: admin password hash, GlobalProtect pre-shared key, API key
- Palo Alto profiles: decryption CA private key password
- FortiGate: admin password, VPN pre-shared keys, FortiGuard license key
- Address groups: none (data-only)
- NAT rules: none (data-only)

### Datacentre
- Arista: enable secret, BGP MD5 passwords, SNMP community strings
- BMC: IPMI admin password, SNMP community, alert email credentials
- Netplan: none (network config only, but references WPA keys on one host)
- Sysctl: none (kernel params only)
- Systemd: embedded environment variables with DB connection strings
- Storage: API access tokens, CHAP initiator secrets
- Database: PostgreSQL superuser password, replication password, SSL key passphrase
- Redis: requirepass, masterauth, sentinel auth-pass

### Factory IoT
- MQTT: broker auth tokens, bridge connection passwords, TLS client cert passwords
- OPC-UA: security certificate passwords, user tokens
- PLC gateway: Modbus device passwords, MQTT publish tokens
- Edge compute: model signing keys, API auth tokens
- Sensor: none (read-only configs)
- Industrial FW: admin passwords, VPN tunnel pre-shared keys
- Historian: database auth tokens, Kepware API keys, InfluxDB admin tokens

## File Count Summary

| Domain | Files |
|---|---|
| SD-WAN | 25 |
| SD-Access | 35 |
| Firewalls | 25 |
| Datacentre | 60 |
| IoT Factory Floor | 40 |
| **Total** | **185** |

## Generation

```bash
python tests/fixtures/enterprise-campus/generate/generate_configs.py
```
