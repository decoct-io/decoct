# Hybrid Infrastructure Fixture — "Ridgeline Data"

Third fixture corpus for the entity-graph pipeline. The previous two: IOS-XR (86 `.cfg`
files) and Entra-Intune (88 `.json` files). This one is the crown jewel:
**~100 mixed-format files (YAML + JSON + INI) spanning 8+ platform types** across all
three supported input formats. It represents a realistic, organically-grown SaaS
deployment — messy, inconsistent, and ideal for testing fleet-scale compression.

## Platform Type Coverage

| Platform Type | Format | Covered Here |
|---|---|---|
| Docker Compose | YAML | yes |
| Ansible playbooks | YAML | yes |
| PostgreSQL | INI (.conf) | yes |
| MariaDB/MySQL | INI (.cnf) | yes |
| Traefik | YAML | yes |
| Cloud-init | YAML | yes |
| Prometheus | YAML | yes |
| sshd_config | INI (.conf) | yes |

This corpus covers **8 platform types across 3 input formats** — the most diverse
fixture set in the project.

---

## Company: Ridgeline Data

B2B analytics platform. 55 engineers, 4 years old. Series B funded. ~180 business
customers.

**Year 1** — The "just ship it" era. One engineer built the MVP as a Python Flask
monolith. Single MariaDB database. Single Hetzner VPS. Deployed by SSH-ing in and
running `git pull`. The original `my.cnf` has never been tuned. It still says
`max_connections = 151` (the MariaDB default that nobody questioned).

**Year 2** — The "microservices" pivot. New CTO arrives. FastAPI for all new backend
services ("Flask is legacy, we're moving to async"). Node.js React SSR for the new
frontend ("SSR is the future"). PostgreSQL for new services because someone read the HN
thread about why MariaDB is the wrong choice. Docker Compose for deployment because
Kubernetes "is overkill for our scale." But the Flask monolith still runs. Nobody wants
to migrate the billing data out of MariaDB.

**Year 3** — The "DevOps hire" era. Platform engineer joins. Introduces Ansible ("no
more SSH-and-pray"). Adds Traefik as the edge proxy ("better than Nginx for
Docker-native routing"). Starts writing OpenTofu modules for infrastructure ("we need
reproducibility"). But every Ansible playbook is slightly different — some use
`become: true` globally, some per-task. Some set `gather_facts: true` explicitly, some
don't. The playbook naming convention changed three times.

**Year 4** — The "scale and suffer" phase. Now running 12 services across 10 servers in
3 environments. The PostgreSQL primary has `shared_buffers = 2GB` but the replica still
has `256MB` because someone forgot to update it. The Traefik config in staging has
`api.insecure: true` left over from debugging. Three different engineers configured sshd
on three different servers — one allows password auth, one doesn't, one is the default
nobody changed. The OpenTofu state has drifted. Prometheus scrape configs reference hosts
that were decommissioned 6 months ago. The Docker Compose files use a mix of
`restart: always` and `restart: unless-stopped` depending on who wrote them. The CI
pipeline has its own Compose file that nobody remembers creating.

## Services

| Service | Tech | DB | Status |
|---|---|---|---|
| `core-api` | FastAPI | PostgreSQL | Active, v2.1 |
| `auth-service` | FastAPI | PostgreSQL | Active, v1.8 |
| `billing-api` | FastAPI | MariaDB (legacy!) | Active, v1.3 |
| `analytics-worker` | Python/Celery | PostgreSQL | Active, workers scale to 4 |
| `report-generator` | Python batch | PostgreSQL | Active, cron-triggered |
| `web-app` | Node.js React SSR | — | Active, v3.0 |
| `notification-svc` | Node.js Express | — | Active, v1.2 |
| `search-svc` | Node.js Fastify | — | Active, v0.9 |
| `admin-panel` | Node.js | PostgreSQL | Active, v1.0 |
| `legacy-dashboard` | Flask | MariaDB | "Legacy," but half the company uses it daily |
| `docs-site` | Static Hugo | — | Container serves built HTML |
| `cron-jobs` | systemd timers | various | Bare-metal, not containerized |

## Infrastructure

| Server | Role | Environment | Notes |
|---|---|---|---|
| `app-prod-01..03` | Docker host (API/frontend) | prod | 3 servers, compose stacks |
| `worker-prod-01` | Docker host (workers) | prod | Scaled analytics worker |
| `db-prod-01` | PostgreSQL primary | prod | Main data, 32GB RAM |
| `db-prod-02` | PostgreSQL replica | prod | Read replica, 16GB (under-provisioned) |
| `db-prod-03` | PostgreSQL analytics | prod | Analytics workload, 64GB |
| `db-legacy-01` | MariaDB | prod | The OG. Nobody touches it. |
| `edge-prod-01` | Traefik + docs | prod | Edge proxy, TLS termination |
| `mon-prod-01` | Prometheus + Grafana | prod | Monitoring |
| `ci-01` | CI runner | shared | Self-hosted runner |
| `app-staging-01` | All apps (staging) | staging | Everything crammed onto one box |
| `db-staging-01` | PG + MariaDB (staging) | staging | Both DBs on one server |
| `dev-01` | Dev environment | dev | Shared dev box, lax security |

## The Mess (intentional inconsistencies)

- **Docker Compose:** `restart: always` on app services, `restart: unless-stopped` on DB
  containers, `restart: "no"` on CI services (a mix of all three, plus some left at
  default)
- **Ansible playbooks:** `base-server.yaml` has `become: true` globally;
  `deploy-api.yaml` sets `become: true` per-task; `emergency-rollback.yaml` has
  `become: false` (mistake, but it works because they always run as root)
- **PostgreSQL:** Primary has `ssl = on`, replica has `ssl = off` (someone forgot);
  analytics has `work_mem = 256MB` (intentionally high), others at default `4MB`
- **MariaDB:** Legacy instance has `character_set_server = latin1` (from the Year 1
  default); billing instance was set up properly with `utf8mb4`
- **sshd:** Production servers have `PasswordAuthentication no`, staging has
  `PasswordAuthentication yes` (for the intern who couldn't figure out SSH keys), dev
  has the default
- **Traefik:** Production has `api.insecure: false`; staging has `api.insecure: true`
  (debugging leftover); dev exposes everything
- **Cloud-init:** Some servers use `package_upgrade: true`, some don't; NTP config
  varies; user creation varies by team
- **Prometheus:** Production scrapes 15 targets; staging scrapes 8; dev scrapes 3 with
  longer intervals
- **systemd units:** Some have `Restart=on-failure`, some `Restart=always`, some have
  no Restart (the old ones)
- **sysctl:** DB servers have aggressive `vm.swappiness=10` and
  `net.core.somaxconn=65535`; app servers use defaults; dev has `vm.swappiness=60`
  (the kernel default nobody changed)

## Secrets Scattered Everywhere (for secret masking testing)

- Docker Compose `environment` vars: `DB_PASSWORD=`, `API_KEY=sk_live_`,
  `JWT_SECRET=`, `REDIS_PASSWORD=`
- Ansible vars: `db_password`, `deploy_key` (SSH private key PEM), `vault_password`
- OpenTofu tfvars: `db_password`, `api_secret`, `ssh_private_key`
- PostgreSQL conf: `ssl_passphrase_command` referencing password
- MariaDB cnf: embedded in comment (legacy practice)
- App config JSON: `jwt_secret`, `encryption_key`, `api_key`

---

## Fixture Inventory (100 files)

### YAML (54 files, 5 platform types + untyped)

| Type | Platform | Count | Description |
|---|---|---|---|
| Docker Compose | docker-compose | 16 | Stacks across prod/staging/dev/CI with 2-6 services each |
| Ansible playbooks | ansible-playbook | 16 | Server provisioning, app deploy, DB setup, security, backups, rollback |
| Ansible inventory/vars | — | 6 | 3 inventories (prod/staging/dev) + 3 var files (with secrets) |
| Cloud-init | cloud-init | 6 | Per server type: app, db, edge, worker, monitoring, dev |
| Traefik | traefik | 4 | Prod static, prod dynamic, staging, dev |
| Prometheus | prometheus | 3 | Prod (15 targets), staging (8), dev (3) |
| App configs (YAML) | — | 3 | FastAPI logging config, feature flags, service mesh |

### JSON (15 files)

| Type | Count | Description |
|---|---|---|
| OpenTofu tfvars | 5 | Prod, staging, dev, DR, edge workspaces |
| Node.js package.json | 4 | web-app, notification-svc, search-svc, admin-panel |
| Docker daemon.json | 3 | Prod, dev, CI (different logging/storage) |
| App configs (JSON) | 3 | Auth JWT config, billing API config, search config |

### INI (31 files, 3 platform types + untyped)

| Type | Platform | Extension | Count | Description |
|---|---|---|---|---|
| PostgreSQL | postgresql | .conf | 6 | Primary, replica, analytics, staging, dev, migration |
| MariaDB | mariadb-mysql | .cnf | 5 | Legacy-main, legacy-billing, staging, dev, galera-node |
| sshd_config | sshd-config | .conf | 4 | Production, bastion, staging, dev (varying security) |
| systemd units | — | .conf | 10 | 6 services + 4 timers for cron jobs |
| sysctl | — | .conf | 6 | DB-tuned, app-server, edge, monitoring, dev, hardened |

## Generation

```bash
python tests/fixtures/hybrid-infra/generate/generate_configs.py
```

## Summary

  Hybrid Infrastructure Fixture Generator — Complete

  100 files generated across all three supported input formats:

  ┌────────┬───────┬───────────────────────────────────────────────────────────────────┐
  │ Format │ Files │                         Schemas Exercised                         │
  ├────────┼───────┼───────────────────────────────────────────────────────────────────┤
  │ YAML   │ 54    │ docker-compose, ansible-playbook, cloud-init, traefik, prometheus │
  ├────────┼───────┼───────────────────────────────────────────────────────────────────┤
  │ JSON   │ 15    │ tfvars, package.json, docker-daemon, app configs                  │
  ├────────┼───────┼───────────────────────────────────────────────────────────────────┤
  │ INI    │ 31    │ postgresql, mariadb-mysql, sshd-config, systemd, sysctl           │
  ├────────┼───────┼───────────────────────────────────────────────────────────────────┤
  │ Total  │ 100   │ 8+ platform types across 3 input formats                          │
  └────────┴───────┴───────────────────────────────────────────────────────────────────┘

  Verification results:
  - 54 YAML files parse cleanly with yaml.safe_load
  - 15 JSON files parse cleanly with json.loads
  - 31 INI files parse cleanly
  - 43 files contain embedded secrets (for secret masking testing)

  Files created: ~50 new files
  - generate_configs.py — main generator script
  - 17 CSV input files
  - 17 templates + 15 Ansible section templates + 1 macros file
  - 100 generated config files in tests/fixtures/hybrid-infra/configs/