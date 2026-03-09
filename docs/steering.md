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
| systemd | `systemd-analyze dump` / man pages | Medium | Snapshot + manual curation | ~30 | High | 3 (snapshot) |
| PostgreSQL | `pg_settings` system view / sample config | Authoritative | Query `pg_settings` for boot_val vs reset_val | ~60 relevant | Low | 1 (direct import) |
| MariaDB/MySQL | `SHOW VARIABLES` / `mysqld --help --verbose` | Authoritative | CLI dump, diff against custom .cnf files | ~40 relevant | Low | 1 (direct import) |
| MongoDB | `mongod --help` / [MongoDB manual](https://www.mongodb.com/docs/manual/reference/configuration-options/) | Authoritative | Parse `mongod.conf` defaults from manual + CLI help | ~40 | Low | 1 (direct import) |
| Kubernetes | [API OpenAPI spec](https://github.com/kubernetes/kubernetes/tree/master/api/openapi-spec) | Authoritative | Parse OpenAPI `default` fields per resource kind | ~80 (Deployment alone ~30) | High | 1 (direct import) |
| Traefik | [Traefik docs](https://doc.traefik.io/traefik/) + CLI defaults | High | `traefik --help` + docs curation | ~25 | Medium | 2 (spec + curation) |
| nginx | [ngx_http_core_module docs](https://nginx.org/en/docs/) | Authoritative | Manual curation from module reference | ~40 | Medium | 2 (spec + curation) |
| Helm values | Per-chart `values.yaml` | Authoritative | Parse chart's `values.yaml` as defaults | varies/chart | Low | 1 (direct import) |
| GitHub Actions | [Actions schema](https://json.schemastore.org/github-workflow.json) | High | JSON Schema import | ~20 | Low | 1 (direct import) |
| GitLab CI | [GitLab CI schema](https://json.schemastore.org/gitlab-ci.json) | High | JSON Schema import | ~25 | Low | 1 (direct import) |
| Prometheus | [Prometheus config docs](https://prometheus.io/docs/prometheus/latest/configuration/) | Authoritative | Manual curation from config reference | ~30 | Medium | 2 (spec + curation) |
| OpenTelemetry Collector | [OTel Collector JSON Schema](https://github.com/open-telemetry/opentelemetry-collector) + docs | High | JSON Schema import + docs curation per component | ~50+ | Medium | 2 (spec + curation) |
| Grafana | [Grafana defaults.ini](https://github.com/grafana/grafana/blob/main/conf/defaults.ini) | Authoritative | Parse shipped defaults.ini | ~80 | Low | 1 (direct import) |
| Zabbix Agent | Reference config shipped with package | Authoritative | Diff uncommented lines against reference config | ~30 | Low | 1 (direct import) |
| Redis | `CONFIG GET *` / redis.conf reference | Authoritative | CLI dump or parse reference config | ~50 | Low | 1 (direct import) |
| Elasticsearch | [Elasticsearch settings](https://www.elastic.co/docs/reference/elasticsearch/configuration-reference) | Authoritative | REST API `_cluster/settings` with `include_defaults` | ~60 | Medium | 1 (direct import) |
| Apache Kafka | Reference `server.properties` / `kafka-configs.sh --describe` | Authoritative | Parse reference config or CLI dump | ~80 | Low | 1 (direct import) |
| Keycloak | [Keycloak REST API](https://www.keycloak.org/docs-api/latest/rest-api/) + admin console schema | High | Parse realm export JSON against API schema | ~60/resource type | Medium | 2 (spec + curation) |
| ArgoCD | [ArgoCD CRD OpenAPI spec](https://github.com/argoproj/argo-cd) | Authoritative | Parse CRD spec for Application/AppProject defaults | ~25/Application | Low | 1 (direct import) |
| Fluent Bit / Fluentd | [Fluent Bit JSON Schema](https://docs.fluentbit.io/) + docs | High | JSON Schema import + docs curation per plugin | ~30 | Medium | 2 (spec + curation) |
| Envoy | [Envoy API reference](https://www.envoyproxy.io/docs/envoy/latest/api-v3/api) | Authoritative | Protobuf default values from API spec | ~40 | High | 2 (spec + curation) |
| Apache httpd | [httpd docs](https://httpd.apache.org/docs/current/mod/directives.html) | Authoritative | Manual curation from directive reference | ~40 | Medium | 2 (spec + curation) |
| HAProxy | [HAProxy config manual](https://www.haproxy.org/download/2.8/doc/configuration.txt) | Authoritative | Manual curation from defaults/global sections | ~35 | Medium | 2 (spec + curation) |
| Vault | [Vault config docs](https://developer.hashicorp.com/vault/docs/configuration) | High | Manual curation from config reference | ~20 | Medium | 2 (spec + curation) |
| Consul | [Consul config docs](https://developer.hashicorp.com/consul/docs/agent/config) | High | Manual curation from config reference | ~25 | Medium | 2 (spec + curation) |
| Microsoft Entra ID | [Microsoft Graph API metadata](https://graph.microsoft.com/v1.0/$metadata) | Authoritative | OData CSDL metadata + REST API defaults | ~60 per resource type | High | 1 (direct import) |
| Intune | [Graph API / deviceManagement](https://graph.microsoft.com/beta/$metadata) | Authoritative | Graph API schema, `deviceManagement` resource defaults | ~80 per policy type | High | 1 (direct import) |
| Azure (Bicep/ARM) | [Azure REST API specs](https://github.com/Azure/azure-rest-api-specs) + ARM schemas | Authoritative | OpenAPI specs per resource provider, published per API version | ~40/resource type | High | 1 (direct import) |
| Azure Policy | [Built-in policy definitions](https://github.com/Azure/azure-policy) | Authoritative | JSON policy definitions with default parameter values | ~30/policy | Medium | 1 (direct import) |
| AWS CDK/CloudFormation | [CloudFormation resource spec](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cfn-resource-specification.html) | Authoritative | JSON resource spec with property defaults per type | ~50/resource type | High | 1 (direct import) |
| AWS IAM policies | [IAM policy schema](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_grammar.html) | Authoritative | JSON, well-defined defaults (Effect, Version, etc.) | ~15 | Low | 2 (spec + curation) |
| AWS SSM / Config Rules | [AWS Config managed rules](https://docs.aws.amazon.com/config/latest/developerguide/managed-rules-by-aws-config.html) | Authoritative | JSON rule definitions with default parameters | ~20/rule | Medium | 2 (spec + curation) |
| GCP Deployment Manager | [GCP API discovery docs](https://www.googleapis.com/discovery/v1/apis) | Authoritative | JSON Schema from discovery API per service | ~40/resource type | High | 1 (direct import) |
| GCP IAM / Org Policies | [GCP Organization Policy constraints](https://cloud.google.com/resource-manager/docs/organization-policy/org-policy-constraints) | Authoritative | REST API, constraint defaults per service | ~25 | Medium | 2 (spec + curation) |
| Cisco IOS XE | [YANG models (GitHub)](https://github.com/YangModels/yang/tree/main/vendor/cisco/xe) + RFC 6243 `report-all-tagged` | Medium-High | pyang extraction of YANG `default` statements; supplement with RFC 6243 device capture | ~100+ | Medium | 2 (schema + curation) |
| Cisco IOS XR | [YANG models (GitHub)](https://github.com/YangModels/yang/tree/main/vendor/cisco/xr) + RFC 6243 | Medium-High | pyang extraction; model-driven architecture, unified models improving | ~100+ | Medium | 2 (schema + curation) |
| Cisco NX-OS | [YANG models (GitHub)](https://github.com/YangModels/yang/tree/main/vendor/cisco/nx) | Low-Medium | pyang extraction (NX-OS README acknowledges incorrect default values) | ~80+ | High | 3 (snapshot) |
| Juniper JunOS | `show groups junos-defaults` + [YANG models (GitHub)](https://github.com/Juniper/yang) | High | Built-in `junos-defaults` group is authoritative machine-readable defaults database | ~150+ | Low | 1 (direct import) |
| Arista EOS | [OpenConfig YANG (GitHub)](https://github.com/aristanetworks/yang) + `show run all` diff | Medium | `show run all` minus `show run` diff; OpenConfig leader but YANG defaults intentionally sparse | ~80+ | Medium | 2 (schema + curation) |

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

**MongoDB:**
- Source: `mongod --help` + [MongoDB Configuration File Options](https://www.mongodb.com/docs/manual/reference/configuration-options/)
- Method: Parse `mongod.conf` (YAML format) defaults from manual. Config is YAML — works with decoct today, zero parser effort.
- Estimated defaults: ~40 (storage engine, journal, network, replication, security, logging)
- Confidence: authoritative
- Note: People routinely paste full `mongod.conf` into LLMs for tuning review. Same use case pattern as PostgreSQL but needs no new format support — `mongod.conf` is native YAML.

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

**Apache Kafka:**
- Source: Reference `server.properties` shipped with Kafka distribution + `kafka-configs.sh --describe --entity-type brokers`
- Method: Parse reference config (INI-like `key=value`). CLI dump for runtime defaults.
- Estimated defaults: ~80 (broker, log, network, replication, ZooKeeper/KRaft, producer/consumer defaults)
- Confidence: authoritative
- Note: People paste full broker configs into LLMs for tuning advice. Typically 200+ lines with only 10–15 intentional changes. Very high compression. Requires INI input support.

**Kubernetes:**
- Source: Kubernetes OpenAPI spec (JSON, shipped with every cluster via `/openapi/v2`)
- Method: Parse OpenAPI `default` fields per resource kind
- Estimated defaults: ~80 (Deployment alone has ~30 defaulted fields)
- Confidence: authoritative
- Note: Massive user base. K8s manifests are the single most common LLM infrastructure input.

**ArgoCD:**
- Source: ArgoCD CRD OpenAPI spec (published in the [argo-cd repo](https://github.com/argoproj/argo-cd))
- Method: Parse CRD spec for Application and AppProject default values
- Estimated defaults: ~25 per Application (sync policy defaults, retry defaults, health check defaults, destination defaults)
- Confidence: authoritative
- Note: Widely deployed GitOps tool (CNCF 2024 survey: Argo at 45% CI/CD adoption). People managing dozens of ArgoCD apps dump them for review or audit. YAML input — works today.

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

### Cloud management platforms

Cloud management APIs are among the most token-heavy data sources fed into LLMs — policy exports, resource configurations, and compliance reports are deeply nested JSON with extensive platform defaults. They're also among the best-documented: every major cloud provider publishes machine-readable API specifications.

**Microsoft Entra ID (Azure AD):**
- Source: Microsoft Graph API OData metadata (`$metadata` endpoint) — every entity type, property, and default is formally specified
- Method: Parse CSDL metadata for entity defaults; cross-reference with Graph API docs for conditional access policy defaults, authentication method defaults, group settings defaults
- Key areas: Conditional access policies (~40 defaults per policy — session controls, grant controls, conditions), authentication methods configuration (~20 defaults), group settings (~15), app registration defaults (~25)
- Estimated defaults: ~60 per resource type, ~200+ across commonly exported resources
- Confidence: authoritative
- Note: Conditional access policy exports are a prime use case — organisations export dozens of policies for LLM review, each carrying identical platform defaults in session controls, client app types, and sign-in risk settings

**Microsoft Intune:**
- Source: Graph API `deviceManagement` resources (beta and v1.0) — full schema published via OData metadata
- Method: Parse Graph API schema for device configuration profiles, compliance policies, app protection policies
- Key areas: Device compliance policies (~30 defaults per platform — password requirements, encryption, OS version), device configuration profiles (~50 defaults per profile type), app protection policies (~40 defaults for MAM), Windows Update rings (~25 defaults)
- Estimated defaults: ~80 per policy type, hundreds across a typical tenant export
- Confidence: authoritative
- Note: Intune tenants with 50+ policies are common. Each policy carries substantial boilerplate — platform defaults for every setting not explicitly configured. Compression potential is very high (~50-60%) for policy exports.

**Azure (Bicep / ARM templates):**
- Source: [Azure REST API specs](https://github.com/Azure/azure-rest-api-specs) — OpenAPI specs for every Azure resource provider, published per API version. Also: [ARM template schemas](https://schema.management.azure.com/schemas/)
- Method: Parse OpenAPI `default` fields per resource type, extract from ARM JSON schemas
- Key resource types to target first: `Microsoft.Compute/virtualMachines` (~40 defaults), `Microsoft.Storage/storageAccounts` (~25), `Microsoft.Network/networkSecurityGroups` (~15 per rule), `Microsoft.Web/sites` (~35), `Microsoft.Sql/servers` (~20)
- Estimated defaults: ~40 per resource type
- Confidence: authoritative
- Note: The Azure REST API specs repo on GitHub is the single most comprehensive machine-readable source of Azure defaults. Bicep and ARM templates are JSON — native input once Phase 2.4 lands.

**Azure Policy:**
- Source: [azure-policy GitHub repo](https://github.com/Azure/azure-policy) — all built-in policy definitions as JSON
- Method: Parse policy definition JSON for default parameter values and effect defaults
- Estimated defaults: ~30 per policy definition
- Confidence: authoritative
- Note: Policy compliance reports exported for LLM review carry per-resource evaluation results with default parameters. Stripping the defaults leaves only the deviations — which is exactly what decoct does.

**AWS CloudFormation / CDK:**
- Source: [CloudFormation resource specification](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cfn-resource-specification.html) — JSON, published per region, lists every resource type with property types and defaults
- Method: JSON import, extract `Default` fields per property per resource type
- Key resource types: `AWS::EC2::Instance` (~30 defaults), `AWS::S3::Bucket` (~20), `AWS::RDS::DBInstance` (~40), `AWS::Lambda::Function` (~15), `AWS::ECS::Service` (~25)
- Estimated defaults: ~50 per resource type
- Confidence: authoritative
- Note: CDK synthesises to CloudFormation — same schema applies. The resource spec is a single JSON download per region, making it one of the easiest cloud schemas to import.

**AWS IAM policies:**
- Source: IAM policy grammar + action-level defaults
- Method: Manual curation from policy reference — `Version` defaults to `2012-10-17`, `Effect` has no default (must be specified), `Resource` patterns, condition operator defaults
- Estimated defaults: ~15 (small but universal — every AWS deployment has IAM policies)
- Confidence: authoritative

**AWS Config Rules / SSM:**
- Source: AWS Config managed rule reference — each rule documents its default parameters
- Method: Parse rule definitions for default parameter values
- Estimated defaults: ~20 per rule
- Confidence: authoritative

**Google Cloud (GCP) resource configs:**
- Source: GCP API discovery documents (`googleapis.com/discovery/v1/apis`) — JSON Schema per service
- Method: Parse discovery doc JSON Schema `default` fields per resource type
- Key services: Compute Engine (`instances`, `firewalls`), GKE (`clusters`), Cloud SQL, Cloud Storage (`buckets`), Cloud Run
- Estimated defaults: ~40 per resource type
- Confidence: authoritative
- Note: GCP Deployment Manager templates and `gcloud` exports are JSON/YAML — directly processable

**GCP Organization Policies / IAM:**
- Source: Org policy constraint reference + IAM policy schema
- Method: Manual curation from constraint documentation
- Estimated defaults: ~25
- Confidence: authoritative

### Network operating systems

Network device configs are among the most commonly pasted infrastructure data in LLM context windows — troubleshooting, architecture review, compliance audit, and migration planning all involve dumping running-configs. Configs are large (500–20,000+ lines), default-heavy (`show running-config all` is typically 3–10x larger than `show running-config`), and pasted frequently.

There are two processing paths, and both are worth pursuing:

**YANG/RESTCONF path (structured).** All five major NOS vendors publish YANG models. Configs retrieved via RESTCONF are JSON; via NETCONF they're XML. Once decoct has JSON input (Phase 2.4), RESTCONF-retrieved configs can be processed immediately with YANG-extracted default schemas. This path delivers structured, standards-based compression without custom parsers.

**CLI path (what people actually paste).** Engineers paste `show running-config` output, not RESTCONF JSON. CLI formats are custom per vendor family: flat line-oriented for Cisco/Arista, hierarchical brace-structured for JunOS. Each needs a dedicated parser. Higher effort, but this is where the real user demand is. Fortunately, IOS/IOS XE/NX-OS/EOS all share a similar flat format, so one parser covers four vendors.

**Cisco IOS XE:**
- Source: [YangModels/yang — vendor/cisco/xe](https://github.com/YangModels/yang/tree/main/vendor/cisco/xe) — extensive native + OpenConfig YANG models
- YANG `default` coverage: Medium — many leaf nodes have `default` statements (actively maintained, see revision history), but not exhaustive
- RFC 6243 support: `report-all-tagged` available — programmatic way to identify which values are defaults from a live device
- Config size: 500–3,000 lines (`show run`); 5,000–15,000+ lines (`show run all`)
- Estimated defaults: ~100+
- LLM context frequency: Highest of any NOS — IOS XE dominates enterprise networking
- Extraction approach: pyang plugin to walk YANG tree and extract `default` statements, supplemented by RFC 6243 `report-all-tagged` captures from reference devices
- Confidence: medium-high
- Note: Cisco's YDK SDK does not expose YANG default values. Custom pyang plugin or PyangBind is needed. The same pyang tooling works across all Cisco platforms.

**Cisco IOS XR:**
- Source: [YangModels/yang — vendor/cisco/xr](https://github.com/YangModels/yang/tree/main/vendor/cisco/xr) — native, unified, and OpenConfig models
- YANG `default` coverage: Medium — similar to IOS XE; unified models (from 7.1.1) are improving consistency
- RFC 6243 support: Available but requires explicit enablement (`netconf-yang agent ssh with-defaults-support enable`)
- Config size: 2,000–20,000+ lines (service provider routers with BGP tables, route policies)
- Estimated defaults: ~100+
- LLM context frequency: Medium — SP/large enterprise, but configs are very large when pasted
- Note: IOS XR is the strongest Cisco platform for model-driven operations. Three model families: native (legacy), unified (CLI-generated, replacing native), OpenConfig.

**Cisco NX-OS:**
- Source: [YangModels/yang — vendor/cisco/nx](https://github.com/YangModels/yang/tree/main/vendor/cisco/nx)
- YANG `default` coverage: Low — the NX-OS README explicitly acknowledges "incorrect default values" inherited from the DME (Data Management Engine) backend
- Config size: 1,000–5,000 lines (`show run`); 10,000–30,000+ lines (`show run all`)
- Estimated defaults: ~80+
- LLM context frequency: High — data centre VXLAN/EVPN configs are commonly shared for troubleshooting
- Note: Weakest Cisco platform for YANG default extraction. Best approached via `show run all` minus `show run` diff from reference devices, not YANG model parsing. Wait for Cisco to fix DME-derived model defaults.

**Juniper JunOS:**
- Source: `show groups junos-defaults` — immutable built-in configuration group containing all predefined default values. This is a machine-readable defaults database built into the device itself.
- YANG source: [Juniper/yang](https://github.com/Juniper/yang) — YANG models are auto-generated from Juniper's internal DDL schema. Sparse `default` statements; relies on proprietary extensions (`junos:must`, `junos:must-message`).
- Config size: 500–5,000+ lines (hierarchical format is inherently verbose)
- Estimated defaults: ~150+ (the `junos-defaults` group is comprehensive)
- LLM context frequency: High — SP/enterprise engineers heavily use LLMs; hierarchical format is verbose and benefits greatly from compression
- Extraction approach: Capture `show groups junos-defaults` output from reference devices across platform families (MX, EX, SRX, QFX). Use this as the defaults database rather than parsing YANG models.
- Confidence: high
- Note: JunOS has three display formats — hierarchical (default), `display set` (flat), and `display xml` (full XML matching YANG schema). The hierarchical and `display set` formats each need parser support. The XML path works with future XML input support. JunOS's `junos-defaults` mechanism makes it the best NOS for authoritative default extraction.

**Arista EOS:**
- Source: [aristanetworks/yang](https://github.com/aristanetworks/yang) — publishes OpenConfig augmentations and deviations, not complete native YANG models
- YANG `default` coverage: Low — follows OpenConfig style guide policy of intentionally avoiding `default` statements
- Config size: 500–3,000 lines; IOS-like flat format
- Estimated defaults: ~80+
- LLM context frequency: High — data centre engineers frequently paste EOS configs
- Extraction approach: `show running-config all` minus `show running-config` diff from reference devices. Arista is the strongest OpenConfig adopter; structured path via OpenConfig models is viable but defaults-sparse.
- Note: IOS-like format means most IOS XE parser work transfers directly. Best approached after IOS XE.

**Cross-cutting: pyang as a universal schema extraction tool.**
A single pyang plugin can walk any YANG model tree and extract `default` statements as decoct schema YAML files. This covers all five NOS vendors plus any other YANG-modeled platform. Key repositories:
- [YangModels/yang](https://github.com/YangModels/yang) — central repo with Cisco XE/XR/NX-OS and many other vendors
- [Juniper/yang](https://github.com/Juniper/yang) — JunOS models
- [aristanetworks/yang](https://github.com/aristanetworks/yang) — Arista OpenConfig augmentations
- [openconfig/public](https://github.com/openconfig/public) — cross-vendor OpenConfig models (useful as structural framework, not for defaults)
- [mbj4668/pyang](https://github.com/mbj4668/pyang) — YANG validator/converter (Python)
- [robshakir/pyangbind](https://github.com/robshakir/pyangbind) — pyang plugin that generates Python bindings with default tracking

**Cross-cutting: OpenConfig as structural framework.**
OpenConfig models ([openconfig/public](https://github.com/openconfig/public)) deliberately avoid `default` statements — their style guide states "the use of default should be avoided." OpenConfig is not useful as a defaults database but is valuable as a cross-vendor structural framework for mapping vendor-specific defaults to canonical paths.

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

**OpenTelemetry Collector:**
- Source: [OTel Collector JSON Schema](https://github.com/open-telemetry/opentelemetry-collector) + component documentation
- Method: JSON Schema import for core config structure, curation per component (receivers, processors, exporters, connectors)
- Estimated defaults: ~50+ across common components (OTLP receiver, batch processor, logging exporter, memory_limiter processor, etc.)
- Confidence: high
- Note: One of the fastest-growing CNCF projects. Configs are YAML — works today. Verbose and repetitive (receivers, processors, exporters, service pipelines) with extensive per-component defaults. People paste entire collector pipelines into LLMs for troubleshooting and architecture review.

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

**Keycloak:**
- Source: [Keycloak REST API](https://www.keycloak.org/docs-api/latest/rest-api/) + admin console schema documentation
- Method: Parse realm export JSON against REST API schema. Identify defaults per resource type (clients, roles, authentication flows, identity providers).
- Estimated defaults: ~60 per resource type (client defaults alone: ~30 settings for access type, consent, session timeouts, token lifespans)
- Confidence: high
- Note: A single Keycloak realm export can be 5,000–10,000 lines of JSON with 80%+ platform defaults. Organisations export realms for LLM-assisted security review, migration planning, and audit. Enormous compression potential. Requires JSON input (Phase 2.4).

**Fluent Bit / Fluentd:**
- Source: [Fluent Bit documentation](https://docs.fluentbit.io/) + JSON Schema (Fluent Bit), Fluentd plugin documentation
- Method: JSON Schema import for Fluent Bit core config, docs curation per plugin
- Estimated defaults: ~30 (flush interval, buffer, retry limits, parser defaults per input/output plugin)
- Confidence: high
- Note: Common in Kubernetes logging stacks. People paste pipeline configs when debugging log routing. YAML/JSON config — works today for Fluent Bit.

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

### Tier 3 — Snapshot (higher effort, lower priority)

**systemd:** Large surface area. Start with `[Service]` section defaults from man pages. ~30 relevant defaults. enable-infra has 14 unit files across hosts with repeated `Requires=docker.service` / `After=docker.service` / `WantedBy=multi-user.target` patterns.

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
| **YAML** (supported today) | Docker Compose, Ansible, cloud-init, K8s, Traefik, Prometheus, Helm, MongoDB, OpenTelemetry Collector, ArgoCD, Fluent Bit | ~400+ | — |
| **JSON** (Phase 2.4) | Terraform state, CloudFormation/CDK, ARM/Bicep, Entra ID, Intune, Azure Policy, GCP, Keycloak, Elasticsearch, Docker daemon, SchemaStore schemas | ~900+ | Low |
| **INI / key-value** (not planned) | PostgreSQL, MariaDB, Redis, Grafana, Kafka, Zabbix, systemd, SSH | ~430+ | Medium |
| **HCL** (future) | Terraform configs, Vault, Consul, Nomad | ~100+ | High |
| **Network CLI** (not planned) | Cisco IOS/IOS XE/NX-OS/EOS (flat), JunOS (hierarchical) | ~500+ | High (two parser families) |
| **Network YANG/RESTCONF** (via JSON) | All YANG-modeled NOS via RESTCONF JSON retrieval | ~500+ | Low (uses JSON input) |
| **Custom syntax** | nginx, Apache, HAProxy, nftables, Envoy (protobuf/JSON) | ~200+ | High per format |

### Recommendation

INI-format input support would unlock more high-compression targets than any other single format addition. PostgreSQL, MariaDB, Redis, Grafana, and Kafka alone represent ~310 defaults from authoritative sources — all extractable with low effort once the format is parseable. Most of these tools ship their own reference configs which double as the schema source.

The normalisation approach should be: parse format → convert to `CommentedMap` → run standard pipeline. Same pattern as JSON input (Phase 2.4), extended to `key = value` formats. Python's `configparser` handles most INI variants; PostgreSQL's `key = value` format needs a simpler custom parser.

Network operating system configs represent the largest single category of unlockable defaults (~500+ across five vendors), but they split into two paths. The **YANG/RESTCONF path** retrieves configs as JSON via RESTCONF — this works with Phase 2.4 JSON input and needs only YANG-extracted default schemas (a pyang tool, not a parser). The **CLI path** is what engineers actually paste and needs custom parsers: one for the Cisco/Arista flat format family, one for JunOS hierarchical format. The YANG path should come first — lower effort, structured data, and the pyang extraction tool serves all vendors.

---

## 7. Schema Priority Matrix

Ranking all identified platforms by: **large configs × high LLM context frequency × low implementation effort**. The core filter is: do people actually paste this configuration into LLM context windows, and is the file large enough that compression delivers meaningful token savings?

### Tier A — High impact, low effort (build first)

| Platform | Format | Why | Est. Defaults |
|----------|--------|-----|---------------|
| **Kubernetes** | YAML/JSON | Largest user base for LLM-assisted infra. OpenAPI spec gives authoritative defaults. Manifests are routinely pasted wholesale. | ~80 |
| **Docker Compose** | YAML | Already in progress (Phase 2.1). Real data validates ~40 defaults. | ~40 |
| **MongoDB** | YAML | `mongod.conf` is YAML — works today, zero parser effort. People paste full configs for tuning review. Same pattern as PostgreSQL. | ~40 |
| **OpenTelemetry Collector** | YAML | Fastest-growing CNCF observability project. Verbose, repetitive configs pasted for troubleshooting. YAML native. | ~50+ |
| **Helm values** | YAML | `values.yaml` IS the schema. Trivial to implement, elegant model. | varies/chart |
| **GitHub Actions** | YAML/JSON | Massive user base, JSON Schema available, YAML input. | ~20 |
| **PostgreSQL** | INI-like | Highest single-file compression (~60% on 500+ line configs). People paste for tuning. Requires INI support. | ~60 |
| **Redis** | INI-like | Very common, reference config is the schema. People paste for tuning. Requires INI support. | ~50 |

### Tier B — High impact, medium effort (cloud management + popular platforms)

| Platform | Format | Why | Est. Defaults |
|----------|--------|-----|---------------|
| **Keycloak** | JSON | Realm exports are 5,000–10,000 lines, 80%+ defaults. Pasted for security review and migration. Requires JSON input. | ~60/type |
| **Microsoft Entra ID** | JSON | Conditional access + auth method exports are token-heavy with extensive defaults. Graph API metadata is the schema. | ~60/type |
| **Intune** | JSON | Policy exports carry ~50-60% boilerplate defaults. Massive enterprise user base. Graph API schema available. | ~80/policy type |
| **Azure (ARM/Bicep)** | JSON | REST API specs repo gives authoritative defaults per resource type. JSON input lands in Phase 2.4. | ~40/type |
| **AWS CloudFormation/CDK** | JSON | Single JSON resource spec download per region. CDK synthesises to same format. Start with EC2, S3, RDS, Lambda. | ~50/type |
| **ArgoCD** | YAML | 45% CI/CD adoption (CNCF 2024). People dump dozens of Applications for review. YAML native. | ~25/Application |
| **Terraform** | JSON/HCL | Already planned. Envelope stripping is high value. Provider defaults vary. | ~15+ |
| **GCP resources** | JSON | Discovery API gives JSON Schema per service. Compute, GKE, Cloud SQL, Storage. | ~40/type |
| **Apache Kafka** | INI-like | 200+ line broker configs with 10–15 intentional changes. Pasted for tuning. Requires INI support. | ~80 |
| **Traefik** | YAML | Real enable-infra data shows ~45% compression. Growing user base. | ~25 |
| **nginx** | Custom | Universal but needs parser. Extremely well-documented defaults. | ~40 |
| **Prometheus** | YAML | Common in monitoring stacks, YAML config, well-documented defaults. | ~30 |
| **GitLab CI** | YAML/JSON | Large user base, JSON Schema available. | ~25 |
| **MariaDB/MySQL** | INI | Second most common database. Authoritative defaults via CLI. People paste for tuning. Requires INI support. | ~40 |
| **Grafana** | INI | `defaults.ini` shipped with every install — the schema writes itself. Requires INI support. | ~80 |
| **cloud-init** | YAML | Already planned. JSON Schema available upstream. | ~30 |
| **Fluent Bit / Fluentd** | YAML/JSON | Common in K8s logging. Pasted when debugging log routing. YAML/JSON native. | ~30 |
| **Cisco IOS XE** | YANG→JSON / CLI | Most-pasted NOS config. YANG models with `default` stmts on GitHub. pyang extraction + RFC 6243. YANG/JSON path first, CLI parser later. | ~100+ |
| **Juniper JunOS** | YANG→JSON / CLI | Built-in `junos-defaults` group is the best NOS defaults source. Hierarchical format is verbose — high compression value. | ~150+ |
| **Cisco IOS XR** | YANG→JSON / CLI | Model-driven architecture, large SP configs (2K–20K lines). Same pyang tooling as IOS XE. | ~100+ |

### Tier C — Valuable but higher effort or narrower audience

| Platform | Format | Why | Est. Defaults |
|----------|--------|-----|---------------|
| **Azure Policy** | JSON | Policy definitions with default parameters. Useful for compliance review context. | ~30/policy |
| **AWS IAM policies** | JSON | Small default set but universal — every AWS deployment has them. | ~15 |
| **AWS Config Rules** | JSON | Managed rule defaults. Useful for compliance context. | ~20/rule |
| **GCP Org Policies** | JSON | Constraint defaults per service. | ~25 |
| **Elasticsearch** | JSON | Common in observability stacks. REST API gives defaults. Large cluster configs. | ~60 |
| **Envoy** | JSON/protobuf | Complex config model but important in service mesh deployments. | ~40 |
| **HAProxy** | Custom | Well-documented defaults but needs custom parser. | ~35 |
| **Apache httpd** | Custom | Still widely deployed but declining. Custom format. | ~40 |
| **Zabbix Agent** | INI | High compression (~70%) but niche user base. Useful for enable-infra dogfooding. | ~30 |
| **HashiCorp Vault/Consul** | HCL/JSON | Important in security-focused stacks. HCL is the blocker. | ~20-25 each |
| **systemd** | INI | Huge surface area, needs curation. Individual units are small. | ~30 |
| **SSH** | Custom | Moderate value — pasted for security review but small-to-medium files per host. | ~50 |
| **Arista EOS** | YANG→JSON / CLI | IOS-like format — IOS XE parser work transfers. OpenConfig leader but YANG defaults sparse. `show run all` diff approach. | ~80+ |
| **Cisco NX-OS** | YANG→JSON / CLI | High DC usage (VXLAN/EVPN) but YANG models have acknowledged incorrect defaults. Wait for fix or use `show run all` diff. | ~80+ |
| **Ansible** | YAML/JSON | Already planned. Per-module extraction. | ~20/module |

### Tier D — Long tail (community-contributed or SchemaStore-derived)

Small configs, niche tools, or platforms where the effort-to-value ratio doesn't justify first-party curation. These are best handled by `decoct schema learn` (future), community-contributed schema files, or the SchemaStore adapter which would cover JSON-schema-described formats (ESLint, Prettier, tsconfig, etc.) for free. Includes: sysctl, nftables, Netplan, fail2ban, Grafana Alloy, syslog-ng, Dockerfiles.

### Note on cloud platform schemas

The cloud management platforms (Entra, Intune, Azure, AWS, GCP) represent a qualitatively different opportunity from on-premises infrastructure tools. Three things make them distinctive:

1. **Volume.** A single Intune tenant export or CloudFormation stack can be thousands of lines of JSON. Organisations routinely dump dozens of policies, resource configs, or compliance reports into LLM context for review. The token cost is enormous.

2. **Default density.** Cloud platforms have extensive default values for every setting not explicitly configured. An Intune compliance policy might have 80 properties, of which 60 are platform defaults. A CloudFormation EC2 instance definition carries defaults for monitoring, tenancy, instance metadata options, and more. Compression potential is typically 40-60%.

3. **Machine-readable schemas.** Every major cloud provider publishes authoritative API specifications in machine-readable formats (OpenAPI, OData CSDL, JSON Schema). These are not documentation to be curated — they are the schema, importable directly. This makes cloud platform schemas Tier 1 candidates despite their complexity.

The practical implication is that JSON input support (Phase 2.4) unlocks the entire cloud management category. Once decoct can ingest JSON, the schema extraction for Azure/AWS/GCP resources becomes a pipeline import rather than a manual curation exercise.

---

## 8. Build Order

### Immediate (Phase 2.1–2.3) — Validate on real data

1. **Comprehensive Docker Compose schema** — expand from 6 to ~40 defaults
2. **Deployment standards assertions** — 12 assertions from ENS-OPS-DOCKER-001
3. **Baseline measurement** — run decoct against all 11 enable-infra compose files, document token savings at each tier

### Short-term (Phase 2.4–2.5) — Expand input support

4. **JSON input** — `json.load()` → `CommentedMap` conversion, format auto-detection
5. **Bundled schemas** — `--schema docker-compose` shorthand, ship schemas with package

### Medium-term (Phase 2.6–2.14) — New platforms (YAML/JSON native)

6. **Kubernetes schema** — parse OpenAPI spec, target Deployment/Service/ConfigMap/Ingress defaults
7. **MongoDB schema** — curate from manual + `mongod --help`. YAML native, no format gating.
8. **OpenTelemetry Collector schema** — JSON Schema + docs curation per component. YAML native.
9. **ArgoCD schema** — parse CRD OpenAPI spec for Application/AppProject defaults. YAML native.
10. **Terraform state schema** — envelope/system-managed field stripping
11. **cloud-init schema** — import from upstream JSON Schema
12. **GitHub Actions schema** — JSON Schema import from SchemaStore
13. **Traefik schema** — curate from docs, validate against enable-infra configs
14. **Prometheus schema** — curate from config reference
15. **Fluent Bit schema** — JSON Schema + docs curation per plugin
16. **Keycloak schema** — parse realm export JSON against REST API schema (requires JSON input)
17. **Directory/recursive mode** — process multiple files, aggregate stats

### Medium-term (Phase 2.15–2.19) — Cloud management platforms

JSON input (Phase 2.4) is the prerequisite. Cloud APIs publish machine-readable schemas, so extraction is largely automated rather than manually curated.

18. **Microsoft Entra ID schema** — import from Graph API OData metadata; target conditional access policies, authentication methods, group settings
19. **Intune schema** — import from Graph API `deviceManagement` metadata; target compliance policies, device config profiles, app protection policies
20. **Azure resource schemas** — import from Azure REST API specs (OpenAPI); start with Compute, Storage, Network, Web, SQL
21. **AWS CloudFormation schema** — import from resource specification JSON; start with EC2, S3, RDS, Lambda, ECS
22. **GCP resource schemas** — import from discovery API JSON; start with Compute, GKE, Cloud SQL, Storage

### Medium-term (Phase 2.20–2.24) — INI format support + database/broker configs

23. **INI/key-value input support** — `configparser` normalisation → `CommentedMap`
24. **PostgreSQL schema** — extract via `pg_settings`, validate against enable-infra config
25. **Redis schema** — extract via `CONFIG GET *` or reference config
26. **Apache Kafka schema** — parse reference `server.properties` or `kafka-configs.sh --describe`
27. **MariaDB schema** — extract via `SHOW VARIABLES`, validate against enable-infra `.cnf` files
28. **Grafana schema** — parse `defaults.ini`

### Medium-term (Phase 2.25–2.33) — Network operating systems (YANG-first)

JSON input (Phase 2.4) is the prerequisite for the YANG/RESTCONF path. CLI parsers are deferred to Future. The pyang extraction tool is a one-time investment that serves all YANG-modeled vendors.

29. **pyang default extraction tool** — pyang plugin to walk YANG model trees and emit decoct schema YAML files. Cross-vendor: works for Cisco XE/XR/NX-OS, Juniper, Arista, and any YANG-modeled platform. Depends on [pyang](https://github.com/mbj4668/pyang).
30. **Juniper JunOS schema** — capture `show groups junos-defaults` from reference devices (MX, EX, SRX, QFX). This is the easiest NOS schema — the device gives you the defaults directly. No pyang needed for this path.
31. **Cisco IOS XE schema** — extract YANG `default` statements via pyang tool (item 29). Supplement with RFC 6243 `report-all-tagged` captures. Version per IOS XE release.
32. **Cisco IOS XR schema** — same pyang approach as IOS XE. Target unified models where available (7.1.1+).
33. **Arista EOS schema** — `show running-config all` minus `show running-config` diff from reference devices. Supplement with OpenConfig YANG augmentation data.

### Future — Automation + remaining platforms

34. **`decoct schema learn`** — LLM-assisted schema generation from examples
35. **Helm values adapter** — treat chart's `values.yaml` as schema source
36. **Azure Policy / AWS Config / GCP Org Policy schemas** — compliance policy defaults for governance context
37. **Jinja2 pre-processing** — strip template syntax before YAML parsing
38. **HCL support** — Terraform/Vault/Consul configs (requires HCL parser dependency)
39. **SchemaStore adapter** — bulk import from SchemaStore for JSON-schema-described formats (GitLab CI, ESLint, Prettier, tsconfig, etc.)
40. **Cisco NX-OS schema** — deferred until Cisco fixes acknowledged incorrect YANG default values, or build via `show run all` diff approach
41. **Network CLI parsers** — Cisco/Arista flat format (one parser covers IOS XE, IOS XR, NX-OS, EOS) + JunOS hierarchical format (separate parser). Unlocks processing of `show running-config` output directly.
42. **Custom format parsers** — nginx, Apache, HAProxy (per-format effort, community-driven)

---

## Changelog

### 2026-03-09 — Network operating systems (CLI + YANG)

**Added (5 NOS platforms + cross-cutting tooling):**
- **Cisco IOS XE** → Tier B. Most-pasted NOS config in LLM context. YANG models with `default` statements on [GitHub](https://github.com/YangModels/yang/tree/main/vendor/cisco/xe). RFC 6243 `report-all-tagged` supplements. ~100+ defaults.
- **Cisco IOS XR** → Tier B. Model-driven architecture, large SP configs (2K–20K lines). Same pyang tooling as IOS XE. ~100+ defaults.
- **Juniper JunOS** → Tier B. Built-in `groups junos-defaults` is the best NOS defaults source — authoritative, machine-readable, comprehensive. ~150+ defaults.
- **Arista EOS** → Tier C. IOS-like format means IOS XE work transfers. OpenConfig leader but YANG defaults intentionally sparse. ~80+ defaults.
- **Cisco NX-OS** → Tier C (deferred). Acknowledged "incorrect default values" in YANG models. Wait for fix or use `show run all` diff.

**Cross-cutting additions:**
- **pyang default extraction tool** added to build order (item 29) — one-time investment that serves all YANG-modeled vendors
- **Network CLI parsers** added to Future (item 41) — Cisco/Arista flat format + JunOS hierarchical format
- **"Network operating systems" subsection** added to Section 4 (sourcing strategy) with detailed per-vendor analysis
- **Two processing paths documented:** YANG/RESTCONF JSON (structured, lower effort, works with Phase 2.4 JSON input) vs CLI format (what people actually paste, needs custom parsers)

**Structural changes:**
- Section 1 inventory table: 5 new rows (Cisco IOS XE, IOS XR, NX-OS, Juniper JunOS, Arista EOS)
- Section 6 format tiers table: 2 new rows (Network CLI, Network YANG/RESTCONF)
- Section 6 recommendation: added paragraph on network OS YANG vs CLI paths
- Section 7 priority matrix: IOS XE, JunOS, IOS XR added to Tier B; EOS, NX-OS added to Tier C
- Section 8 build order: new subsection "Phase 2.25–2.33 — Network operating systems (YANG-first)" with 5 items
- Build order renumbered sequentially (1–42) after additions
- SchemaStore adapter reference in demotions updated from item 34 to item 39

### 2026-03-09 — Additions, removals, and reprioritisation

Applied the filter: **do people actually paste this configuration into LLM context windows, and is the file large enough that compression delivers meaningful token savings?**

**Added (6 platforms):**
- **MongoDB** → Tier A. `mongod.conf` is YAML (works today). People paste full configs for tuning. ~40 defaults. Same use case as PostgreSQL with zero parser effort.
- **OpenTelemetry Collector** → Tier A. YAML native, fastest-growing CNCF observability project, verbose repetitive configs. ~50+ defaults.
- **Keycloak** → Tier B. Realm exports are 5,000–10,000 lines JSON, 80%+ defaults. Massive compression. Requires JSON input.
- **ArgoCD** → Tier B. YAML native, 45% CI/CD adoption (CNCF 2024), people dump dozens of Applications. ~25 defaults/app.
- **Apache Kafka** → Tier B. INI-like `server.properties`, 200+ lines with ~15 intentional changes. ~80 defaults. Requires INI support.
- **Fluent Bit / Fluentd** → Tier B. YAML/JSON, common in K8s logging stacks. ~30 defaults.

**Removed from priority matrix and build order:**
- **Netplan** — Configs are ~15 lines. Nobody pastes netplan into LLMs. Negligible absolute token savings. Removed from inventory, sourcing strategy, priority matrix, and build order.
- **sysctl** — Individual files are small. High compression percentage is misleading — absolute savings negligible. People don't dump sysctl into LLM context. Removed from build order, moved to Tier D footnote.
- **fail2ban** — Niche, small configs. Removed from format tiers table, moved to Tier D footnote.

**Demoted:**
- **Dockerfiles** — ~10 defaults, requires dedicated parser, poor effort-to-value ratio. Moved from Tier C to Tier D.
- **ESLint / Prettier / tsconfig** — People paste these but files are rarely >40 lines. Not worth dedicated effort. Removed from Tier C and individual build order entries. Covered for free by SchemaStore adapter (build order item 39).
- **SSH (sshd_config)** — Moderate value, small-to-medium files. Kept in inventory and Tier C but not promoted ahead of any Tier A/B item.
- **Zabbix Agent** — High compression percentage but niche user base. Useful for enable-infra dogfooding. Kept in Tier C, not promoted.
- **Grafana Alloy / syslog-ng** — Niche tools. Moved to Tier D footnote.

**Structural changes:**
- Tier D consolidated from individual platform list into a single paragraph framing items as community-contributed or SchemaStore-derived candidates.
- Section 7 tier descriptions updated to emphasise the LLM-context-frequency filter.
- Build order renumbered sequentially (1–35) after additions/removals.
- Format tiers table (Section 6) updated: YAML row now includes MongoDB, OTel Collector, ArgoCD, Fluent Bit; JSON row now includes Keycloak; INI row now includes Kafka, removed sysctl/fail2ban.
- Duplicate AWS CloudFormation entries in Tier 2 sourcing strategy consolidated (was listed under both cloud platforms and Tier 2).
- Duplicate Azure ARM entries in Tier 2 sourcing strategy consolidated (same).
