# Baseline Measurement — example-infra Docker Compose Files

Date: 2026-03-09
Schema: `docker-compose-full.yaml` (35 defaults, authoritative)
Assertions: `deployment-standards.yaml` (12 assertions, 8 evaluable)
Encoding: cl100k_base

## Three-Tier Token Savings

| Stack | Svcs | Input | T1 Generic | T1% | T2 +Schema | T2% | T3 Full | T3% |
|-------|------|-------|-----------|-----|-----------|-----|---------|-----|
| acme-app | 6 | 2367 | 1851 | 21.8% | 1733 | 26.8% | 1480 | 37.5% |
| mautic | 3 | 1646 | 1371 | 16.7% | 1309 | 20.5% | 1168 | 29.0% |
| crm-stack | 6 | 1655 | 1351 | 18.4% | 1254 | 24.2% | 1038 | 37.3% |
| traefik-internal | 1 | 432 | 364 | 15.7% | 345 | 20.1% | 303 | 29.9% |
| wiki | 1 | 571 | 418 | 26.8% | 394 | 31.0% | 350 | 38.7% |
| dns | 1 | 389 | 355 | 8.7% | 336 | 13.6% | 289 | 25.7% |
| grafana | 1 | 554 | 489 | 11.7% | 465 | 16.1% | 422 | 23.8% |
| infisical | 3 | 705 | 662 | 6.1% | 639 | 9.4% | 533 | 24.4% |
| loki | 3 | 730 | 721 | 1.2% | 664 | 9.0% | 532 | 27.1% |
| traefik-mgmt | 1 | 317 | 314 | 0.9% | 295 | 6.9% | 253 | 20.2% |
| zabbix | 2 | 620 | 616 | 0.6% | 578 | 6.8% | 476 | 23.2% |
| **TOTAL** | **28** | **9986** | **8512** | **14.8%** | **8012** | **19.8%** | **6844** | **31.5%** |

## Per-Pass Contribution (acme-app, largest file)

| Pass | Items Removed |
|------|--------------|
| strip-comments | 8 |
| strip-secrets | 12 |
| strip-defaults | 19 |
| strip-conformant | 30 |

## Key Findings

### 1. strip-conformant is the biggest contributor

Across all files, `strip-conformant` removes the most content — stripping conformant
`image`, `restart`, `container_name`, `logging.driver`, `logging.options.max-size`,
`logging.options.max-file`, and `security_opt` values. These are repeated identically
on every service, making them high-value compression targets.

### 2. Schema savings are lower than expected

Target was 30-45% at the schema tier; actual is **19.8%**. These production configs
are already lean — most services don't explicitly set defaults like `privileged: false`
or `init: false`. The schema tier catches `healthcheck.retries: 3`, `network.driver: bridge`,
and a few others, but well-maintained configs naturally omit most defaults.

### 3. Full pipeline reaches 31.5%, not 40-60%

The 40-60% target assumed configs with more verbose defaults and more diverse
deviation patterns. These configs are highly conformant (0 deviations across
28 services), so the annotations tier adds no content — it only strips.

### 4. Absent field detection is a gap

The matcher only evaluates fields that exist. Across 28 services:
- 3 services missing `container_name` (infisical postgres/redis, crm-stack redis)
- 1 service missing `healthcheck` (traefik-internal — expected, infrastructure service)
- 0 missing `restart`, `security_opt`, or `logging`

These absent-field violations are invisible to the current assertion matcher.
Impact: moderate — well-maintained configs have the fields, but the tool can't
validate completeness.

### 5. strip-secrets has false positives on healthcheck commands

Entropy-based detection redacts healthcheck `CMD-SHELL` test strings (e.g.
`curl -f http://localhost:8080/health`). The "prefer redacting too much" policy
is correct for security, but these false positives inflate the secrets count
and remove useful information. Healthcheck commands should be exempted.

### 6. Variable substitution passes correctly

`acme-app:${IMAGE_TAG:-latest}` is correctly evaluated as conformant by
`ops-image-pinned` — the literal string doesn't end with `:latest`, so the
negative lookahead passes. This is the right behaviour.

## Template Comparison (less hardened)

| Template | Svcs | Input | Full | Savings | Devs |
|----------|------|-------|------|---------|------|
| acme-app | 6 | 2255 | 1370 | 39.2% | 0 |
| mautic | 3 | 1505 | 1055 | 29.9% | 0 |
| crm-stack | 6 | 1384 | 814 | **41.2%** | 0 |
| wiki | 1 | 558 | 337 | 39.6% | 0 |

Templates achieve **35-41% savings** — closer to the 40-60% target. Higher savings
come from `strip-conformant` stripping more present-but-conformant values.

Still 0 deviations because the "violations" are absent fields (e.g. crm-stack-run missing
`container_name`, 5/6 services missing `security_opt`, 3/6 missing `healthcheck`).
These would be caught by absent-field detection.

## Recommendations

1. **Accept 25-35% as realistic target** for well-maintained Docker Compose configs.
   The 40-60% target is achievable on more verbose/less-curated configs.

2. **Add healthcheck command exclusion** to strip-secrets — exempt paths matching
   `services.*.healthcheck.test` from entropy-based detection.

3. **Consider absent-field detection** as a Phase 3 feature — would require a new
   match type (`exists: true`) that checks for key presence rather than value evaluation.

4. **Remove `ops-no-privileged` assertion** or convert to absent-field check —
   conformant services omit `privileged` entirely (default is false), so the
   assertion never matches.

5. **Test against non-conformant configs** — the templates directory has less-hardened
   versions that should produce deviations, better validating the annotation pipeline.
