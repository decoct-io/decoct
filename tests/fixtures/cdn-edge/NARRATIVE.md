# Edge/CDN PoP Network Fixture — "ArcticCache"

Fourth fixture corpus for the entity-graph pipeline. Represents a CDN startup's global
PoP (Point of Presence) network — highly uniform configs with regional tuning, ideal
for testing high class-reuse compression scenarios.

## Company: ArcticCache

CDN startup. 30 engineers, 2 years old. Seed + Series A funded. ~400 enterprise customers.

**8 global PoPs** spanning 4 continents:

| PoP Code | City | Region | Tier | Upstream |
|---|---|---|---|---|
| `ams` | Amsterdam | EU | primary | fra |
| `fra` | Frankfurt | EU | primary | ams |
| `lhr` | London | EU | secondary | fra |
| `iad` | Ashburn | NA | primary | sjc |
| `sjc` | San Jose | NA | primary | iad |
| `nrt` | Tokyo | APAC | primary | sin |
| `syd` | Sydney | APAC | secondary | sin |
| `sin` | Singapore | APAC | primary | nrt |

Each PoP has identical topology: nginx frontends, haproxy L4 balancers, varnish cache
layer, local DNS resolver, prometheus monitoring, edge-compute workers (Wasm), and
keepalived for HA. Regional tuning covers cache sizes, upstream pools, bandwidth caps,
and TLS certificate paths.

## PoP Topology (per site)

| Component | Purpose | Notes |
|---|---|---|
| nginx (×2) | Frontend HTTP/HTTPS | Static asset serving + API reverse proxy |
| haproxy | L4 load balancer | Backend pools vary by PoP capacity |
| varnish | HTTP cache | Cache size scales with PoP tier |
| dns-resolver | Local DNS | Authoritative for PoP zone + recursive |
| prometheus | Monitoring | Scrape all local services |
| edge-compute | Wasm workers | A/B testing, geo-redirect, image resize |
| keepalived | HA/VRRP | Floating VIP for nginx pair |
| ssl-config | TLS certificates | Cert paths, cipher suites, OCSP |
| pop-metadata | Site metadata | Capacity, coordinates, tier, links |

## Config Type Coverage

| Config Type | Format | Count | Description |
|---|---|---|---|
| nginx-site | conf (INI-like) | 16 | 2 per PoP (static + API proxy) |
| haproxy | conf (INI-like) | 8 | 1 per PoP, backend pools vary |
| varnish-params | YAML | 8 | Cache sizes, TTLs, purge ACLs |
| dns-zone | conf (INI-like) | 8 | SOA/NS/A records per PoP |
| ssl-config | JSON | 8 | Cert paths, ciphers, OCSP |
| prometheus | YAML | 8 | Scrape targets, alert thresholds |
| edge-compute | YAML | 8 | Wasm worker configs, routing rules |
| pop-metadata | JSON | 8 | PoP capacity, coordinates, tier |
| keepalived | conf (INI-like) | 8 | VRRP configs for HA |

**Total: 80 files across 9 config types**

## The Mess (intentional inconsistencies)

- **nginx:** Primary PoPs use `worker_processes auto`; secondary PoPs hardcode
  `worker_processes 4` (old template). LHR still has HTTP/2 push directives
  (deprecated). SJC has extra rate-limiting config from a DDoS incident.
- **haproxy:** EU PoPs use `nbthread 4`, APAC uses `nbthread 8` (different hardware).
  IAD has a legacy `option httpchk GET /` while others use `option httpchk GET /health`.
- **varnish:** Cache sizes range from 2GB (secondary) to 16GB (primary). SYD has an
  extra purge ACL for Australian compliance. NRT has shorter TTLs for Japanese
  content regulations.
- **dns-zone:** SOA serial numbers vary (some auto-increment, some manual). LHR has
  extra CNAME records for legacy domains.
- **ssl-config:** EU PoPs use ECDSA certs; NA/APAC use RSA (migration in progress).
  SJC still has TLS 1.0 enabled (legacy client support).
- **prometheus:** Primary PoPs scrape every 15s; secondary every 30s. NRT has extra
  scrape targets for Japanese compliance metrics.
- **edge-compute:** Some PoPs have 3 workers, some have 5. Different Wasm module
  versions across regions.
- **keepalived:** Priority values differ by PoP (100 for primary, 50 for secondary).
  IAD has a custom notify script.
- **pop-metadata:** Capacity values vary: primary tier has 100Gbps, secondary 40Gbps.

## Secrets (for secret masking testing)

- nginx: `proxy_set_header X-API-Key` values, upstream auth headers
- haproxy: stats auth passwords, backend server check passwords
- ssl-config: private key paths, OCSP responder tokens
- varnish-params: purge ACL tokens
- prometheus: remote_write auth tokens
- edge-compute: Wasm signing keys
- keepalived: VRRP auth passwords
- dns-zone: TSIG keys for zone transfers
- pop-metadata: API management tokens

## Generation

```bash
python tests/fixtures/cdn-edge/generate/generate_configs.py
```
