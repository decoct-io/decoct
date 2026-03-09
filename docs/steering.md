# Steering Document — decoct Phase 2

This document consolidates all research into a single reference for Phase 2 planning.
Phase 1 is complete: 183 tests, 95% coverage, 8 passes, full CLI.

---

## 1. External Data Source Inventory

| Platform | Schema Source | Quality | Extraction Method | Est. Defaults | Effort | Tier |
|----------|-------------|---------|-------------------|---------------|--------|------|
| Docker Compose | [Compose spec](https://github.com/compose-spec/compose-spec) + compose-go source | Authoritative | Manual curation from spec + Go struct tags | ~40 | Medium | 2 (spec + curation) |
| cloud-init | [cloud-init JSON Schema](https://github.com/canonical/cloud-init) | Authoritative | Direct JSON Schema import | ~30 | Low | 1 (direct import) |
| Ansible | `ansible-doc --metadata-dump` | Authoritative | CLI extraction per module | ~20/module | Medium | 1 (direct import) |
| SSH (sshd) | `sshd -T` (compiled defaults) | Authoritative | CLI snapshot, diff against config | ~50 | Low | 1 (direct import) |
| Terraform | Provider schemas (`terraform providers schema -json`) | Authoritative | JSON import, envelope fields curated | ~15 envelope + varies/provider | High | 2 (schema + curation) |
| Netplan | netplan.io YAML spec | Medium | Manual curation | ~15 | Medium | 3 (snapshot) |
| systemd | `systemd-analyze dump` / man pages | Medium | Snapshot + manual curation | ~30 | High | 3 (snapshot) |
| sysctl | `sysctl -a` (kernel defaults) | High | Snapshot, diff against custom | ~20 relevant | Low | 3 (snapshot) |

**Tier definitions:**
- **Tier 1 — Direct import:** Schema available in machine-readable format, minimal curation needed
- **Tier 2 — Schema + curation:** Schema exists but needs human curation for default extraction
- **Tier 3 — Snapshot:** No formal schema; defaults captured via runtime snapshot

---

## 2. Live Data Assessment

Source: `enable-infra` repository — production infrastructure for Enable Network Services.

### What decoct can process today

| Data Type | Files | Format | Status |
|-----------|-------|--------|--------|
| Docker Compose | 11 config + 4 templates | YAML | Fully supported |
| Ansible vars | `group_vars/*.yml`, `host_vars/*.yml` | YAML | Supported (generic passes) |
| cloud-init user-data | `templates/cloud-init/` | YAML | Supported (generic passes) |

### What decoct cannot process today

| Data Type | Files | Format | Blocker |
|-----------|-------|--------|---------|
| Terraform state | `tofu/terraform.tfstate` | JSON | No JSON input support |
| Terraform HCL | `tofu/*.tf` | HCL | No HCL parser |
| Jinja2 templates | `templates/**/*.j2` | Jinja2+YAML | Template syntax breaks YAML parser |
| Ansible playbooks | `*.yml` with Jinja2 | YAML+Jinja2 | Jinja2 expressions in values |
| nftables rules | `templates/nftables/*.nft` | Custom | No parser |

### Docker Compose coverage

11 deployed compose files across 2 hosts:

| Stack | Services | Highlights |
|-------|----------|------------|
| hairtrigger (app-01) | 6 (redis, rabbitmq, django, celery-worker, celery-beat, nginx) | Full standards compliance, resource limits, healthchecks |
| tps (app-01) | 6 (api, worker, beat, redis, flower, legacy) | Multiple networks, profile-gated services |
| mautic (app-01) | 3 (web, worker, cron) | Shared image, varied healthchecks |
| wiki (app-01) | 1 (bookstack) | LinuxServer.io image, simple stack |
| traefik-internal (app-01) | 1 | Macvlan networking, CAP_ADD |
| grafana (host-01) | 1 | Single service, init: true, extra_hosts |
| loki (host-01) | 3 (loki, syslog-ng, alloy) | Missing restart policies, docker.sock mount |
| zabbix (host-01) | 2 (server, web) | Runtime secret injection, missing resource limits |
| dns (host-01) | 1 (technitium) | Sysctls, CAP_ADD, missing resource limits |
| infisical (host-01) | 3 (postgres, redis, infisical) | env_file usage, missing container_names |
| traefik-mgmt (host-01) | 1 | Management-bound ports, static IP |

---

## 3. Gap Analysis

| Gap | Impact | Priority | Complexity | Phase |
|-----|--------|----------|------------|-------|
| Comprehensive Docker Compose schema | Only 6 defaults today; ~40 available | Critical | Medium | 2.1 |
| Deployment standards as assertions | No real-world assertions exist | Critical | Low | 2.2 |
| Baseline measurement | Cannot quantify improvement | High | Low | 2.3 |
| JSON input support | Cannot process tfstate, package.json, etc. | High | Low | 2.4 |
| Bundled schemas | Users must provide schema file paths | Medium | Low | 2.5 |
| Terraform state schema | System-managed fields not stripped | Medium | Medium | 2.6 |
| cloud-init schema | No cloud-init defaults | Medium | Low | 2.7 |
| Directory/recursive mode | One file at a time only | Medium | Medium | 2.8 |
| Schema learning commands | Manual schema creation only | Low | High | 2.9 |
| Jinja2 template handling | Cannot process Ansible/cloud-init templates | Low | High | Future |
| HCL input support | Cannot process Terraform configs | Low | High | Future |

---

## 4. Schema Sourcing Strategy

### Tier 1 — Direct Import (low effort, high value)

**cloud-init:**
- Source: `cloud-init` package ships JSON Schema (`/usr/share/doc/cloud-init/cloud-config-schema.json`)
- Method: Parse JSON Schema `default` fields, convert to decoct schema format
- Estimated defaults: ~30
- Confidence: authoritative

**Ansible modules:**
- Source: `ansible-doc --metadata-dump --no-fail-on-errors` produces JSON with per-module option defaults
- Method: Parse JSON output, extract `options.*.default` for target modules
- Estimated defaults: ~20 per module (target: `ansible.builtin.apt`, `ansible.builtin.systemd`, `ansible.builtin.user`)
- Confidence: authoritative

**SSH (sshd_config):**
- Source: `sshd -T` dumps compiled-in defaults
- Method: Capture output, parse key-value pairs as schema defaults
- Estimated defaults: ~50
- Confidence: authoritative

### Tier 2 — Schema + Curation (medium effort)

**Docker Compose:**
- Source: [Compose Specification](https://github.com/compose-spec/compose-spec/blob/main/spec.md) + [compose-go](https://github.com/docker/compose/tree/main/pkg/compose) Go struct tags
- Method: Manual curation — read spec for documented defaults, cross-reference with compose-go `default:` struct tags
- Key defaults identified (~40):
  - Service: `restart: "no"`, `privileged: false`, `read_only: false`, `stdin_open: false`, `tty: false`, `init: false`
  - Network mode: `bridge`
  - Healthcheck: `interval: 30s`, `timeout: 30s`, `retries: 3`, `start_period: 0s`
  - Logging: `driver: json-file`
  - Deploy: `replicas: 1`, `restart_policy.condition: any`, `update_config.order: stop-first`
  - Ports (long-form): `protocol: tcp`, `mode: ingress`
  - depends_on (long-form): `condition: service_started`, `required: true`
  - Networks: `driver: bridge`, `external: false`, `internal: false`
  - Volumes: `external: false`
- Confidence: authoritative

**Terraform:**
- Source: `terraform providers schema -json` for provider-specific defaults; envelope fields curated manually
- Envelope/system-managed fields: `version`, `serial`, `lineage`, `terraform_version`, `resources.*.instances.*.private`, `resources.*.instances.*.sensitive_attributes`, `resources.*.instances.*.schema_version`
- Provider defaults vary by provider — start with vSphere (matches live data)
- Confidence: authoritative (envelope), high (provider defaults)

### Tier 3 — Snapshot (higher effort, lower priority)

**Netplan:** Manual extraction from netplan.io docs. ~15 defaults (renderer, dhcp4, etc.)

**systemd:** Large surface area. Start with `[Service]` section defaults from man pages. ~30 relevant defaults.

**sysctl:** Snapshot `sysctl -a` on reference system, curate security/network-relevant subset. ~20 defaults.

---

## 5. Assertion Derivation

Mapping from ENS-OPS-DOCKER-001 (deployment-standards.md) to machine-evaluable assertions:

| ID | Standard Section | Assert | Severity | Match Type | Path | Evaluable? |
|----|-----------------|--------|----------|------------|------|------------|
| `ens-image-pinned` | Mandatory elements | Image tags must be pinned, not `:latest` | must | pattern | `services.*.image` | Yes |
| `ens-restart-policy` | Mandatory elements | Restart policy must be `unless-stopped` or `always` | must | pattern | `services.*.restart` | Yes |
| `ens-container-name` | Mandatory elements | Container name must be explicitly set | must | pattern | `services.*.container_name` | Yes |
| `ens-healthcheck` | Health check patterns | Application containers must have health checks | must | — | — | LLM-context only |
| `ens-logging-driver` | Logging standard | Logging driver must be json-file | must | value | `services.*.logging.driver` | Yes |
| `ens-logging-max-size` | Logging standard | Log max-size must be configured | must | pattern | `services.*.logging.options.max-size` | Yes |
| `ens-logging-max-file` | Logging standard | Log max-file must be configured | must | pattern | `services.*.logging.options.max-file` | Yes |
| `ens-security-opt` | Security baseline | Containers should set `no-new-privileges:true` | should | contains | `services.*.security_opt` | Yes |
| `ens-no-privileged` | Security baseline | Containers must not run privileged | must | value | `services.*.privileged` | Yes |
| `ens-resource-limits` | Security baseline | Production stacks should have resource limits | should | — | — | LLM-context only |
| `ens-named-networks` | Network declarations | Services should use named networks, not default bridge | should | — | — | LLM-context only |
| `ens-no-host-0000` | Firewall | Ports must not bind to 0.0.0.0 | should | — | — | LLM-context only |

**Notes:**
- 8 of 12 assertions are machine-evaluable (have `match` definitions)
- 4 are LLM-context only due to structural complexity (existence checks, cross-field logic, format variation)
- `ens-healthcheck` could theoretically check for key existence, but the spec says "application containers" — distinguishing app vs infrastructure containers requires LLM judgement
- `ens-no-host-0000` is complex because port formats vary (short-form string, long-form map)

---

## 6. Build Order

### Immediate (Phase 2.1–2.3) — Validate on real data

1. **Comprehensive Docker Compose schema** — expand from 6 to ~40 defaults
2. **Deployment standards assertions** — 12 assertions from ENS-OPS-DOCKER-001
3. **Baseline measurement** — run decoct against all 11 enable-infra compose files, document token savings at each tier

### Short-term (Phase 2.4–2.5) — Expand input support

4. **JSON input** — `json.load()` → `CommentedMap` conversion, format auto-detection
5. **Bundled schemas** — `--schema docker-compose` shorthand, ship schemas with package

### Medium-term (Phase 2.6–2.8) — New platforms

6. **Terraform state schema** — envelope/system-managed field stripping
7. **cloud-init schema** — import from upstream JSON Schema
8. **Directory/recursive mode** — process multiple files, aggregate stats

### Future (Phase 2.9+) — Automation

9. **`decoct schema learn`** — LLM-assisted schema generation from examples
10. **Jinja2 pre-processing** — strip template syntax before YAML parsing
11. **HCL support** — terraform config files (requires HCL parser dependency)
