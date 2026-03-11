# Kubernetes Multi-Cluster Fleet Fixture -- "WavePoint Financial"

Fifth fixture corpus for the entity-graph pipeline. Represents a fintech company's
Kubernetes fleet spanning 3 regions, 3 environments, 12 microservices, and 7 config
types -- all YAML format. Ideal for testing class extraction and delta compression
across a highly structured but organically drifted fleet.

## Company: WavePoint Financial

Series C fintech. 120 engineers, 5 years old. Processes $2.3B in annual transaction
volume across payment processing, KYC/AML compliance, and real-time risk scoring.
PCI-DSS Level 1 certified (in theory). SOC 2 Type II audit passed last quarter (barely).

**3 regions** x **3 environments** = **9 clusters**:

| Region | Cluster Prefix | Cloud | Notes |
|---|---|---|---|
| us-east-1 | `use1` | AWS EKS | Primary region, most traffic |
| eu-west-1 | `euw1` | AWS EKS | EU data residency (GDPR) |
| ap-southeast-1 | `apse1` | AWS EKS | APAC expansion (6 months old) |

| Environment | Suffix | Purpose |
|---|---|---|
| dev | `dev` | Developer sandbox, relaxed limits |
| staging | `stg` | Pre-prod, inconsistent configs |
| prod | `prd` | Production, strict resource limits |

## Services

| Service | Purpose | Has Deployment | Has Service | Has HPA | Notes |
|---|---|---|---|---|---|
| `payment-api` | Payment processing gateway | yes (3 envs) | yes (3 envs) | yes (3 envs) | Core revenue path |
| `auth-svc` | Authentication/OAuth2/OIDC | yes (3 envs) | yes (3 envs) | yes (3 envs) | JWT issuer |
| `ledger-svc` | Double-entry ledger | yes (3 envs) | yes (3 envs) | no | Stateful, no autoscale |
| `risk-engine` | Real-time fraud scoring | yes (3 envs) | yes (3 envs) | yes (3 envs) | ML model serving |
| `kyc-worker` | KYC/AML background checks | yes (3 envs) | no | no | Queue consumer only |
| `notification-svc` | Email/SMS/push notifications | yes (3 envs) | no | no | Fire-and-forget |
| `gateway-api` | API gateway / BFF | yes (3 envs) | yes (3 envs) | yes (3 envs) | Public-facing |
| `reporting-svc` | Regulatory reporting | yes (3 envs) | yes (3 envs) | no | Batch workloads |
| `audit-log` | Immutable audit trail | yes (3 envs) | no | no | Write-heavy |
| `rate-limiter` | Distributed rate limiting | yes (3 envs) | yes (3 envs) | no | Redis-backed |
| `config-server` | Centralized config | yes (3 envs) | no | no | Spring Cloud Config |
| `healthcheck-api` | Synthetic monitoring | yes (3 envs) | yes (3 envs) | no | Canary checks |

## Config Type Coverage

| Config Type | Format | Count | Description |
|---|---|---|---|
| deployment | YAML | 36 | 12 services x 3 envs, K8s Deployment manifests |
| service | YAML | 24 | 8 services x 3 envs, K8s Service manifests |
| configmap | YAML | 20 | Shared configs across envs with regional overrides |
| ingress | YAML | 15 | Nginx ingress rules, TLS, rate limiting |
| hpa | YAML | 12 | 4 services x 3 envs, HorizontalPodAutoscaler |
| networkpolicy | YAML | 10 | Namespace isolation and inter-service rules |
| serviceaccount | YAML | 8 | RBAC, IAM role annotations |

**Total: 125 files, all YAML format**

## The Mess (intentional inconsistencies)

### API Version Drift

- **Dev deployments** still use `apps/v1beta1` for 3 services (payment-api, auth-svc,
  ledger-svc) because the dev cluster runs K8s 1.24 and nobody upgraded it.
- **Staging** uses `apps/v1` everywhere but has outdated `networking.k8s.io/v1beta1`
  for some ingress resources (leftover from the 1.19 -> 1.25 migration).
- **Prod** uses correct current API versions throughout.

### Resource Limits

- **Prod** has strict, well-tuned resource limits: payment-api gets 2 CPU / 4Gi,
  auth-svc gets 1 CPU / 2Gi. Requests equal 50% of limits.
- **Staging** has limits copied from prod 6 months ago but never updated. Some
  services have grown significantly since then.
- **Dev** has `resources: {}` (empty) on 4 services because "it's just dev."
  The remaining services have requests but no limits.

### Replica Counts

- **Prod**: payment-api=5, auth-svc=3, gateway-api=5, risk-engine=3, others=2
- **Staging**: everything=2 (uniform, never adjusted)
- **Dev**: everything=1

### Environment Variable Chaos

- Dev has `LOG_LEVEL=DEBUG` everywhere; prod has `LOG_LEVEL=WARN` on most services
  but someone left `LOG_LEVEL=DEBUG` on risk-engine (debugging a prod issue 3 weeks ago).
- Database URLs differ per env but the connection pool sizes were copy-pasted from prod
  to dev (50 connections in dev, where the DB only allows 20).
- Some services use `DATABASE_URL` env var, others use `DB_HOST` + `DB_PORT` + `DB_NAME`
  separately (depends on which team wrote the service).

### Ingress Inconsistencies

- Prod ingresses have proper `cert-manager.io/cluster-issuer: letsencrypt-prod`
  annotations. Staging uses `letsencrypt-staging`. Dev has no cert-manager annotations
  (self-signed certs mounted manually).
- Rate limiting annotations vary: prod has `nginx.ingress.kubernetes.io/limit-rps: "100"`,
  staging has `"50"`, dev has no rate limiting.
- Some ingresses have `nginx.ingress.kubernetes.io/ssl-redirect: "true"`, others omit it.

### HPA Drift

- Prod: payment-api scales 3-10, auth-svc scales 2-8, gateway-api scales 3-12,
  risk-engine scales 2-6 with both CPU and memory metrics.
- Staging: all services scale 1-3 with CPU only (memory metrics were "causing flapping").
- Dev: scales 1-2 (mostly for testing HPA behavior).

### Network Policy Gaps

- Prod has comprehensive network policies: default deny + explicit allow rules.
- Staging has the default deny but is missing 2 allow rules (notification-svc and
  audit-log can't reach each other -- a bug nobody noticed because those services
  don't interact in staging test scenarios).
- Dev has `allow-all` policies (the platform team gave up enforcing network policies
  in dev after the third "my pod can't reach anything" incident).

### ServiceAccount Confusion

- Prod has proper least-privilege IAM roles per service. payment-api has
  `eks.amazonaws.com/role-arn` pointing to a role with S3, SQS, and KMS access.
- Staging service accounts reference prod IAM roles (copy-paste error nobody fixed
  because staging has its own trust policy that blocks it anyway).
- Dev service accounts have wildcard IAM policies (convenience over security).

## Secrets (for secret masking testing)

- **Deployments**: `DATABASE_URL` values contain embedded passwords
  (`postgresql://user:p4ssw0rd@host:5432/db`), `API_KEY` values, `JWT_SECRET` values
- **ConfigMaps**: Database connection strings in `data` values, API endpoint tokens
- **ServiceAccounts**: IAM role ARNs (not secret per se, but sensitive infrastructure)
- **Ingresses**: No secrets in spec, but annotations reference cert-manager secrets

## Generation

```bash
python tests/fixtures/k8s-fleet/generate/generate_configs.py
```
