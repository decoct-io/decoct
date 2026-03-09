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
| PostgreSQL | `pg_settings` system view / sample config | Authoritative | Query `pg_settings` for boot_val vs reset_val | ~60 relevant | Low | 1 (direct import) |
| MariaDB/MySQL | `SHOW VARIABLES` / `mysqld --help --verbose` | Authoritative | CLI dump, diff against custom .cnf files | ~40 relevant | Low | 1 (direct import) |
| Kubernetes | [API OpenAPI spec](https://github.com/kubernetes/kubernetes/tree/master/api/openapi-spec) | Authoritative | Parse OpenAPI `default` fields per resource kind | ~80 (Deployment alone ~30) | High | 1 (direct import) |
| Traefik | [Traefik docs](https://doc.traefik.io/traefik/) + CLI defaults | High | `traefik --help` + docs curation | ~25 | Medium | 2 (spec + curation) |
| nginx | [ngx_http_core_module docs](https://nginx.org/en/docs/) | Authoritative | Manual curation from module reference | ~40 | Medium | 2 (spec + curation) |
| Helm values | Per-chart `values.yaml` | Authoritative | Parse chart's `values.yaml` as defaults | varies/chart | Low | 1 (direct import) |
| GitHub Actions | [Actions schema](https://json.schemastore.org/github-workflow.json) | High | JSON Schema import | ~20 | Low | 1 (direct import) |
| GitLab CI | [GitLab CI schema](https://json.schemastore.org/gitlab-ci.json) | High | JSON Schema import | ~25 | Low | 1 (direct import) |
| Prometheus | [Prometheus config docs](https://prometheus.io/docs/prometheus/latest/configuration/) | Authoritative | Manual curation from config reference | ~30 | Medium | 2 (spec + curation) |
| Grafana | [Grafana defaults.ini](https://github.com/grafana/grafana/blob/main/conf/defaults.ini) | Authoritative | Parse shipped defaults.ini | ~80 | Low | 1 (direct import) |
| Zabbix Agent | Reference config shipped with package | Authoritative | Diff uncommented lines against reference config | ~30 | Low | 1 (direct import) |
| ESLint / Prettier | JSON config, schema on SchemaStore | Authoritative | JSON Schema import | ~15 per tool | Low | 1 (direct import) |
| AWS CloudFormation | [CloudFormation resource spec](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cfn-resource-specification.html) | Authoritative | JSON import of resource type defaults | ~50/resource type | High | 1 (direct import) |
| Azure ARM | [ARM template schema](https://schema.management.azure.com/schemas/) | Authoritative | JSON Schema import | ~40/resource type | High | 1 (direct import) |
| Dockerfiles | [Dockerfile reference](https://docs.docker.com/reference/dockerfile/) | Authoritative | Manual curation | ~10 | Low | 2 (spec + curation) |
| Apache httpd | [httpd docs](https://httpd.apache.org/docs/current/mod/directives.html) | Authoritative | Manual curation from directive reference | ~40 | Medium | 2 (spec + curation) |
| HAProxy | [HAProxy config manual](https://www.haproxy.org/download/2.8/doc/configuration.txt) | Authoritative | Manual curation from defaults/global sections | ~35 | Medium | 2 (spec + curation) |
| Redis | `CONFIG GET *` / redis.conf reference | Authoritative | CLI dump or parse reference config | ~50 | Low | 1 (direct import) |
| Elasticsearch | [Elasticsearch settings](https://www.elastic.co/docs/reference/elasticsearch/configuration-reference) | Authoritative | REST API `_cluster/settings` with `include_defaults` | ~60 | Medium | 1 (direct import) |
| Envoy | [Envoy API reference](https://www.envoyproxy.io/docs/envoy/latest/api-v3/api) | Authoritative | Protobuf default values from API spec | ~40 | High | 2 (spec + curation) |
| Vault | [Vault config docs](https://developer.hashicorp.com/vault/docs/configuration) | High | Manual curation from config reference | ~20 | Medium | 2 (spec + curation) |
| Consul | [Consul config docs](https://developer.hashicorp.com/consul/docs/agent/config) | High | Manual curation from config reference | ~25 | Medium | 2 (spec + curation) |

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

### What decoct could process with format support

| Data Type | Files | Format | Blocker | Compression Potential |
|-----------|-------|--------|---------|----------------------|
| PostgreSQL config | 1 (500+ lines) | INI-like (`key = value`) | No INI input support | ~60% — mostly defaults and comments |
| MariaDB config | 5 `.cnf` files | INI (`.cnf`) | No INI input support | ~50% — boilerplate defaults per file |
| Traefik static + dynamic | 8 files | YAML | None (supported today) | ~45% — TLS ciphers, HSTS, middleware |
| nginx config | 2 files | nginx syntax | No nginx parser | ~35% — gzip, logging, worker defaults |
| Zabbix Agent config | 3 (565 lines each) | INI-like | No INI input support | ~70% — comments, examples, defaults |
| Grafana Alloy | 4 files (130+ lines) | Alloy DSL (HCL-like) | No Alloy parser | ~40% — repetitive discovery rules |
| systemd units | 14 files | INI (`[Unit]`/`[Service]`) | No INI input support | ~35% — repeated Requires/After/Wants |
| sysctl configs | 12-14 per host | INI-like | No INI input support | ~70% — heavily commented kernel defaults |
| Docker daemon.json | 1 per host | JSON | Needs JSON input (Phase 2.4) | ~30% — well-known defaults |

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

**PostgreSQL:**
- Source: `pg_settings` system view — `SELECT name, boot_val, reset_val FROM pg_settings`
- Method: Query running instance or parse sample `postgresql.conf` shipped with every install
- Estimated defaults: ~60 relevant (300+ total but many are internal)
- Confidence: authoritative
- Note: Massive compression opportunity — `postgresql.conf` is typically 500+ lines of which ~90% is commented defaults and documentation. The enable-infra instance confirms this pattern.

**MariaDB/MySQL:**
- Source: `SHOW VARIABLES` or `mysqld --help --verbose 2>/dev/null | tail -n +N`
- Method: CLI dump, diff against custom `.cnf` files
- Estimated defaults: ~40 relevant
- Confidence: authoritative
- Note: enable-infra has 5 `.cnf` files, only one (`99-enable-tuning.cnf`) has intentional customisations

**Redis:**
- Source: `CONFIG GET *` against running instance, or parse `redis.conf` reference
- Method: CLI dump or shipped reference config (extensively commented with defaults)
- Estimated defaults: ~50
- Confidence: authoritative

**Grafana:**
- Source: `defaults.ini` shipped with every Grafana install (`/usr/share/grafana/conf/defaults.ini`)
- Method: Parse INI file, all values are defaults by definition
- Estimated defaults: ~80
- Confidence: authoritative

**Zabbix Agent:**
- Source: Reference `zabbix_agent2.conf` shipped with package (every parameter documented and commented)
- Method: Diff uncommented lines against reference
- Estimated defaults: ~30
- Confidence: authoritative
- Note: enable-infra has 565-line agent configs that are ~70% defaults and documentation

**Kubernetes:**
- Source: Kubernetes OpenAPI spec (JSON, shipped with every cluster via `/openapi/v2`)
- Method: Parse OpenAPI `default` fields per resource kind
- Estimated defaults: ~80 (Deployment alone has ~30 defaulted fields)
- Confidence: authoritative
- Note: Massive user base. K8s manifests are the single most common LLM infrastructure input.

**Helm values:**
- Source: Each chart's `values.yaml` — this IS the defaults file by definition
- Method: Parse `values.yaml` as the schema defaults, diff against user-supplied values
- Estimated defaults: varies per chart, but typically 50-200 lines
- Confidence: authoritative
- Note: Elegant fit — Helm already separates defaults from overrides, decoct just strips the defaults

**GitHub Actions:**
- Source: JSON Schema on SchemaStore (`github-workflow.json`)
- Method: JSON Schema import
- Estimated defaults: ~20
- Confidence: high

**GitLab CI:**
- Source: JSON Schema on SchemaStore (`gitlab-ci.json`)
- Method: JSON Schema import
- Estimated defaults: ~25
- Confidence: high

**ESLint / Prettier / tsconfig:**
- Source: JSON Schemas on SchemaStore
- Method: JSON Schema import
- Estimated defaults: ~15 per tool
- Confidence: authoritative
- Note: Developer tooling configs are very common LLM context. `tsconfig.json` especially has heavy defaults.

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

**Traefik:**
- Source: Traefik docs + `traefik --help` CLI defaults
- Method: Manual curation from documentation, cross-reference with CLI help output
- Key defaults: TLS min version, cipher suites, entrypoint defaults, middleware defaults
- Estimated defaults: ~25
- Confidence: high
- Note: enable-infra has 8 Traefik configs with repeated TLS/HSTS/middleware boilerplate (~45% compressible)

**nginx:**
- Source: nginx module documentation (ngx_http_core_module, ngx_http_gzip_module, etc.)
- Method: Manual curation from directive reference — each directive lists its default
- Key defaults: `worker_connections 512`, `keepalive_timeout 75s`, gzip settings, proxy buffer sizes
- Estimated defaults: ~40
- Confidence: authoritative
- Note: Universal — nginx is in nearly every infrastructure stack

**Prometheus:**
- Source: Prometheus configuration documentation
- Method: Manual curation from config reference
- Key defaults: scrape_interval (1m), evaluation_interval (1m), scrape_timeout (10s), metric relabeling
- Estimated defaults: ~30
- Confidence: authoritative

**Apache httpd:**
- Source: httpd directive reference (each directive documents its default)
- Method: Manual curation
- Estimated defaults: ~40
- Confidence: authoritative
- Note: Still widely deployed, configs are verbose with many defaults

**HAProxy:**
- Source: HAProxy configuration manual (defaults/global sections explicitly document all defaults)
- Method: Manual curation from reference manual
- Estimated defaults: ~35
- Confidence: authoritative

**Envoy:**
- Source: Envoy API v3 reference (protobuf definitions include default values)
- Method: Parse protobuf default values from API spec
- Estimated defaults: ~40
- Confidence: authoritative
- Note: Complex — protobuf-based config is deeply nested

**AWS CloudFormation:**
- Source: CloudFormation resource specification (JSON, published per region)
- Method: JSON import of resource type property defaults
- Estimated defaults: ~50 per resource type
- Confidence: authoritative
- Note: Huge user base but very large surface area — start with common resource types (EC2, S3, RDS, Lambda)

**Azure ARM templates:**
- Source: ARM template schema (published per API version per resource provider)
- Method: JSON Schema import
- Estimated defaults: ~40 per resource type
- Confidence: authoritative

**HashiCorp Vault:**
- Source: Vault configuration reference docs
- Method: Manual curation
- Estimated defaults: ~20
- Confidence: high

**HashiCorp Consul:**
- Source: Consul agent configuration reference
- Method: Manual curation
- Estimated defaults: ~25
- Confidence: high

**Dockerfiles:**
- Source: Dockerfile reference
- Method: Manual curation — `SHELL`, `STOPSIGNAL`, `HEALTHCHECK` defaults etc.
- Estimated defaults: ~10
- Confidence: authoritative
- Note: Small but universal. Requires Dockerfile parsing, not YAML.

### Tier 3 — Snapshot (higher effort, lower priority)

**Netplan:** Manual extraction from netplan.io docs. ~15 defaults (renderer, dhcp4, etc.)

**systemd:** Large surface area. Start with `[Service]` section defaults from man pages. ~30 relevant defaults. enable-infra has 14 unit files across hosts with repeated `Requires=docker.service` / `After=docker.service` / `WantedBy=multi-user.target` patterns.

**sysctl:** Snapshot `sysctl -a` on reference system, curate security/network-relevant subset. ~20 defaults. enable-infra has 12-14 sysctl files per host, heavily commented, ~70% compressible.

**Elasticsearch:**
- Source: `_cluster/settings?include_defaults=true` REST API
- Method: Query running instance for all defaults
- Estimated defaults: ~60 relevant
- Confidence: authoritative
- Note: Cluster settings are verbose JSON, very common in LLM troubleshooting context

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

## 6. Format Support Implications

The schema inventory reveals a clear pattern: the highest-compression targets beyond YAML/JSON use INI-like or custom configuration formats. This has direct implications for decoct's input pipeline.

### Format tiers by unlock potential

| Format | Platforms Unlocked | Combined Est. Defaults | Effort |
|--------|-------------------|----------------------|--------|
| **YAML** (supported today) | Docker Compose, Ansible, cloud-init, K8s, Traefik, Prometheus, Helm | ~300+ | — |
| **JSON** (Phase 2.4) | Terraform state, CloudFormation, ARM, Elasticsearch, Docker daemon, SchemaStore schemas | ~250+ | Low |
| **INI / key-value** (not planned) | PostgreSQL, MariaDB, Redis, Grafana, Zabbix, sysctl, systemd, SSH, fail2ban | ~400+ | Medium |
| **HCL** (future) | Terraform configs, Vault, Consul, Nomad | ~100+ | High |
| **Custom syntax** | nginx, Apache, HAProxy, nftables, Envoy (protobuf/JSON), Alloy | ~200+ | High per format |

### Recommendation

INI-format input support would unlock more high-compression targets than any other single format addition. PostgreSQL, MariaDB, Redis, Grafana, and Zabbix alone represent ~260 defaults from authoritative sources — all extractable with low effort once the format is parseable. Most of these tools ship their own reference configs which double as the schema source.

The normalisation approach should be: parse format → convert to `CommentedMap` → run standard pipeline. Same pattern as JSON input (Phase 2.4), extended to `key = value` formats. Python's `configparser` handles most INI variants; PostgreSQL's `key = value` format needs a simpler custom parser.

---

## 7. Schema Priority Matrix

Ranking all identified platforms by a combination of user base, compression potential, schema quality, and implementation effort.

### Tier A — High impact, low effort (build first)

| Platform | Format | Why | Est. Defaults |
|----------|--------|-----|---------------|
| **Kubernetes** | YAML/JSON | Largest user base for LLM-assisted infra. OpenAPI spec gives authoritative defaults. | ~80 |
| **Docker Compose** | YAML | Already in progress (Phase 2.1). Real data validates ~40 defaults. | ~40 |
| **Helm values** | YAML | `values.yaml` IS the schema. Trivial to implement, elegant model. | varies/chart |
| **GitHub Actions** | YAML/JSON | Massive user base, JSON Schema available, YAML input. | ~20 |
| **PostgreSQL** | INI-like | Highest single-file compression (~60% on 500+ line configs). Authoritative source. | ~60 |
| **Redis** | INI-like | Very common, reference config is the schema, `CONFIG GET *` for extraction. | ~50 |

### Tier B — High impact, medium effort

| Platform | Format | Why | Est. Defaults |
|----------|--------|-----|---------------|
| **Terraform** | JSON/HCL | Already planned. Envelope stripping is high value. Provider defaults vary. | ~15+ |
| **Traefik** | YAML | Real enable-infra data shows ~45% compression. Growing user base. | ~25 |
| **nginx** | Custom | Universal but needs parser. Extremely well-documented defaults. | ~40 |
| **Prometheus** | YAML | Common in monitoring stacks, YAML config, well-documented defaults. | ~30 |
| **GitLab CI** | YAML/JSON | Large user base, JSON Schema available. | ~25 |
| **MariaDB/MySQL** | INI | Second most common database. Authoritative defaults via CLI. | ~40 |
| **Grafana** | INI | `defaults.ini` shipped with every install — the schema writes itself. | ~80 |
| **cloud-init** | YAML | Already planned. JSON Schema available upstream. | ~30 |

### Tier C — Valuable but higher effort or narrower audience

| Platform | Format | Why | Est. Defaults |
|----------|--------|-----|---------------|
| **AWS CloudFormation** | JSON | Huge user base but enormous surface area. Start with common resource types. | ~50/type |
| **Azure ARM** | JSON | Same pattern as CloudFormation. | ~40/type |
| **Elasticsearch** | JSON | Common in observability stacks. REST API gives defaults. | ~60 |
| **Envoy** | JSON/protobuf | Complex config model but important in service mesh deployments. | ~40 |
| **HAProxy** | Custom | Well-documented defaults but needs custom parser. | ~35 |
| **Apache httpd** | Custom | Still widely deployed but declining. Custom format. | ~40 |
| **Zabbix Agent** | INI | Niche but extremely high compression (~70%). | ~30 |
| **HashiCorp Vault/Consul** | HCL/JSON | Important in security-focused stacks. HCL is the blocker. | ~20-25 each |
| **systemd** | INI | Huge surface area, needs curation. | ~30 |
| **ESLint/Prettier/tsconfig** | JSON | Developer tooling — common LLM context but not infrastructure. | ~15 each |
| **Dockerfiles** | Custom | Small default set, needs Dockerfile parser. | ~10 |
| **SSH** | Custom | Already planned. Small but security-relevant. | ~50 |
| **Ansible** | YAML/JSON | Already planned. Per-module extraction. | ~20/module |

### Tier D — Long tail (community-contributed or LLM-learned)

Netplan, sysctl, fail2ban, nftables, Alloy, syslog-ng, and other niche tools. Best handled by `decoct schema learn` (Phase 2.9) or community-contributed schema files rather than first-party curation.

---

## 8. Build Order

### Immediate (Phase 2.1–2.3) — Validate on real data

1. **Comprehensive Docker Compose schema** — expand from 6 to ~40 defaults
2. **Deployment standards assertions** — 12 assertions from ENS-OPS-DOCKER-001
3. **Baseline measurement** — run decoct against all 11 enable-infra compose files, document token savings at each tier

### Short-term (Phase 2.4–2.5) — Expand input support

4. **JSON input** — `json.load()` → `CommentedMap` conversion, format auto-detection
5. **Bundled schemas** — `--schema docker-compose` shorthand, ship schemas with package

### Medium-term (Phase 2.6–2.8) — New platforms (YAML/JSON native)

6. **Kubernetes schema** — parse OpenAPI spec, target Deployment/Service/ConfigMap/Ingress defaults
7. **Terraform state schema** — envelope/system-managed field stripping
8. **cloud-init schema** — import from upstream JSON Schema
9. **GitHub Actions schema** — JSON Schema import from SchemaStore
10. **Traefik schema** — curate from docs, validate against enable-infra configs
11. **Prometheus schema** — curate from config reference
12. **Directory/recursive mode** — process multiple files, aggregate stats

### Medium-term (Phase 2.9–2.11) — INI format support + database configs

13. **INI/key-value input support** — `configparser` normalisation → `CommentedMap`
14. **PostgreSQL schema** — extract via `pg_settings`, validate against enable-infra config
15. **Redis schema** — extract via `CONFIG GET *` or reference config
16. **MariaDB schema** — extract via `SHOW VARIABLES`, validate against enable-infra `.cnf` files
17. **Grafana schema** — parse `defaults.ini`

### Future — Automation + remaining platforms

18. **`decoct schema learn`** — LLM-assisted schema generation from examples
19. **Helm values adapter** — treat chart's `values.yaml` as schema source
20. **Jinja2 pre-processing** — strip template syntax before YAML parsing
21. **HCL support** — Terraform/Vault/Consul configs (requires HCL parser dependency)
22. **SchemaStore adapter** — bulk import from SchemaStore for JSON-schema-described formats (GitLab CI, ESLint, tsconfig, etc.)
23. **Cloud provider schemas** — CloudFormation resource spec, ARM template schemas (large surface area, start with common types)
24. **Custom format parsers** — nginx, Apache, HAProxy (per-format effort, community-driven)
