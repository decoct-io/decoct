# 5G RAN Fixture — "SpectrumOne"

Fifth fixture corpus for the entity-graph pipeline. Represents a regional mobile operator's
5G Radio Access Network deployment across a metro area — a mix of macro, small-cell, and
indoor sites with disaggregated RAN architecture (O-RAN split), network slicing, and
5G core network functions.

## Operator: SpectrumOne

Regional mobile operator. 200 engineers, 5 years old. Serves a single large metro area
(pop ~4M). PLMN 310/260. Holds 100 MHz of n78 (3500 MHz) spectrum plus 40 MHz of n41
(2500 MHz) mid-band and 20 MHz of n77 (3700 MHz) C-band. Organic 5G SA buildout with
some legacy NSA sites still in transition.

**10 cell sites** across 3 tiers:

| Site ID | Type | Location | Sectors | TAC | Notes |
|---|---|---|---|---|---|
| `macro-north-01` | macro | Highway corridor N | 3 | 20001 | Primary macro, SA |
| `macro-north-02` | macro | Highway corridor N | 3 | 20001 | Primary macro, SA |
| `macro-north-03` | macro | Business park NE | 3 | 20002 | SA, higher power |
| `macro-north-04` | macro | Residential N | 3 | 20002 | Legacy NSA site |
| `small-downtown-01` | small-cell | Downtown core | 3 | 20003 | Lamppost mount |
| `small-downtown-02` | small-cell | Transit hub | 3 | 20003 | Utility pole mount |
| `small-downtown-03` | small-cell | Shopping district | 3 | 20003 | Wall mount |
| `indoor-enterprise-01` | indoor | Corporate campus A | 3 | 20004 | DAS, low power |
| `indoor-enterprise-02` | indoor | Hospital | 3 | 20004 | DAS, URLLC priority |
| `indoor-enterprise-03` | indoor | Convention center | 3 | 20005 | DAS, high capacity |

Each macro site has 3 sectors (alpha/beta/gamma) with 64T64R massive MIMO antennas.
Small-cell sites use 4T4R. Indoor sites use 2T2R DAS.

## Disaggregated RAN Architecture

SpectrumOne uses O-RAN 7.2x split:

| Component | Count | Role |
|---|---|---|
| gNB-DU (Distributed Unit) | 15 | Baseband processing, one per site + 5 planned/spare |
| gNB-CU (Centralized Unit) | 6 | RRC/PDCP, pooled across sites |
| Transport links | 12 | Fronthaul/midhaul/backhaul IP/MPLS links |

CU pools:
- `cu-pool-north` — serves macro-north-01..02
- `cu-pool-south` — serves small-downtown-01..02
- `cu-pool-central` — serves small-downtown-03, indoor-enterprise-01
- `cu-pool-east` — serves macro-north-03..04
- `cu-pool-west` — serves indoor-enterprise-02..03
- `cu-pool-backup` — disaster recovery, no active DUs

## Network Slicing

| Slice | SST | SD | Purpose | Max UE |
|---|---|---|---|---|
| `embb-default` | 1 | 000001 | Enhanced Mobile Broadband — general | 50000 |
| `embb-premium` | 1 | 000002 | eMBB premium — guaranteed 100 Mbps DL | 10000 |
| `urllc-industrial` | 2 | 000010 | Ultra-Reliable Low Latency — factory | 5000 |
| `urllc-medical` | 2 | 000011 | URLLC — hospital critical comms | 2000 |
| `mmtc-iot-01` | 3 | 000020 | Massive Machine Type — smart meters | 200000 |
| `mmtc-iot-02` | 3 | 000021 | mMTC — vehicle fleet telemetry | 100000 |

## RAN Policies

| Policy | Type | Notes |
|---|---|---|
| `handover-intra-freq` | handover | Intra-frequency A3 event |
| `handover-inter-freq` | handover | Inter-frequency A4/A5 events |
| `load-balance-01` | load-balancing | MLB between cells |
| `load-balance-02` | load-balancing | CU-level load redistribution |
| `power-control-01` | power-control | Uplink TPC for macro |
| `power-control-02` | power-control | Downlink EIRP limits for small-cell |
| `admission-ctrl-01` | admission-control | QoS-aware admission |
| `admission-ctrl-02` | admission-control | Slice-aware admission |

## 5G Core Functions

| Function | Count | Role |
|---|---|---|
| AMF | 4 | Access and Mobility Management |
| SMF | 4 | Session Management |

## Config Type Coverage

| Config Type | Format | Count | Description |
|---|---|---|---|
| gnodeb-cell | YAML | 30 | Per-cell radio configuration (10 sites x 3 sectors) |
| gnodeb-du | YAML | 15 | Distributed Unit configs (10 active + 5 spare) |
| gnodeb-cu | YAML | 6 | Centralized Unit pool configs |
| transport-link | JSON | 12 | Fronthaul/midhaul/backhaul transport |
| network-slice | YAML | 6 | Network slice definitions |
| ran-policy | YAML | 8 | RAN policy configs |
| core-amf | JSON | 4 | 5G Core AMF configs |
| core-smf | JSON | 4 | 5G Core SMF configs |
| site-metadata | YAML | 15 | Site physical/location metadata |

**Total: 100 files across 9 config types**

## The Mess (intentional inconsistencies)

- **gnodeb-cell:** macro-north-04 still configured for NSA (en-dc: true, sa: false)
  while all other sites are SA-only. PCI values were hand-assigned and some
  neighboring sectors have PCI mod-3 conflicts (cells 120/123 on adjacent sectors).
  indoor-enterprise-03 has tx_power_dbm accidentally set to 30 (macro-level power
  for an indoor cell). Some cells on n78, others on n41 or n77 — inconsistent
  band assignment across site tiers.
- **gnodeb-du:** Five spare DUs (du-spare-01..05) have firmware_version "4.1.0"
  while active DUs run "4.2.1" — firmware update not applied to spares. du-spare-03
  has cpu_cores set to 16 (old hardware) vs 32 for all others.
- **gnodeb-cu:** cu-pool-backup has n2_amf_ip pointing to the DR AMF (10.100.1.4)
  instead of production. cu-pool-east still references firmware "4.1.0" (upgrade
  deferred due to NSA dependency).
- **transport-link:** Fronthaul links have 25 Gbps bandwidth (eCPRI), midhaul links
  have 10 Gbps, backhaul varies. One backhaul link (transport-backhaul-04) has
  ipsec_enabled: false — a security gap. Latency values vary significantly
  (fronthaul <100us, midhaul <500us, backhaul 1-5ms).
- **network-slice:** urllc-medical slice has max_ue set to only 2000 (should be higher
  for hospital campus). embb-premium has bandwidth_guarantee_mbps inconsistent with
  its QoS profile.
- **ran-policy:** handover-inter-freq has a3_offset set to 3 dB (should be higher for
  inter-freq). power-control-02 references a non-existent cell group.
- **core-amf:** amf-03 has an extra TAI entry for TAC 20005 that other AMFs don't
  serve. amf-04 is the DR instance with different PLMN config (test MNC).
- **core-smf:** smf-04 has a DNN "enterprise" that other SMFs don't know about.
  smf-02 has session_ambr different from the others.
- **site-metadata:** GPS coordinates have varying precision (some 4 decimals, some 6).
  indoor-enterprise-03 has altitude_m set to 0 (should be building floor height).
  macro-north-04 has power_source "generator" (temporary, should be "grid+battery").

## Secrets (for secret masking testing)

- gnodeb-cell: oam_password per cell for O&M access
- gnodeb-du: oam_password for DU management interface
- gnodeb-cu: oam_password for CU management interface
- transport-link: ipsec_psk for IPsec tunnel pre-shared keys
- core-amf: oam_password for AMF management
- core-smf: oam_password for SMF management
- site-metadata: access_code for physical site access

## Generation

```bash
python tests/fixtures/telco-5g/generate/generate_configs.py
```
