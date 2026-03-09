# Bundled Schemas Reference

## Overview

decoct ships with 25 bundled schemas accessible via short names (e.g., `--schema docker-compose`). Each schema defines platform defaults that the strip-defaults pass uses to remove redundant values. When a value in your configuration matches the platform default, it carries no information -- decoct strips it to save tokens and reduce noise.

Schemas also declare **system-managed fields** (e.g., `metadata.uid`, `status`) that are auto-populated by the platform and can be dropped entirely, and **drop patterns** for structural noise.

## Summary Table

| Schema Name | Platform | Source | Confidence | Defaults | Auto-Detect |
|---|---|---|---|---|---|
| `ansible-playbook` | ansible-playbook | Ansible builtin module documentation | authoritative | 132 | Yes |
| `argocd` | argocd | ArgoCD CRD spec + official documentation | authoritative | 14 | No |
| `aws-cloudformation` | aws-cloudformation | AWS CloudFormation Resource Specification + AWS Service Documentation | authoritative | 56 | No |
| `azure-arm` | azure-arm | Azure ARM/Bicep Template Reference (learn.microsoft.com) | authoritative | 65 | No |
| `cloud-init` | cloud-init | cloud-init upstream JSON Schema (schema-cloud-config-v1.json) | authoritative | 55 | Yes |
| `docker-compose` | docker-compose | Docker Compose specification + compose-go source | authoritative | 35 | Yes |
| `entra-id` | entra-id | Microsoft Graph API v1.0 Reference (learn.microsoft.com) | authoritative | 44 | No |
| `fluent-bit` | fluent-bit | Fluent Bit Official Manual -- Service, Input, Output, Filter configuration reference | authoritative | 75 | No |
| `gcp-resources` | gcp-resources | GCP REST API Reference + Google Cloud Documentation | authoritative | 42 | No |
| `github-actions` | github-actions | GitHub Actions documentation + SchemaStore github-workflow.json schema | authoritative | 8 | Yes |
| `gitlab-ci` | gitlab-ci | GitLab CI/CD YAML syntax reference + CI/CD settings documentation | authoritative | 25 | No |
| `grafana` | grafana | Grafana defaults.ini (github.com/grafana/grafana/blob/main/conf/defaults.ini) | authoritative | 162 | No |
| `intune` | intune | Microsoft Graph API v1.0 Intune Reference (learn.microsoft.com) | authoritative | 96 | No |
| `kafka` | kafka | Apache Kafka Documentation -- Broker Configs (v3.7+) | authoritative | 63 | No |
| `keycloak` | keycloak | Keycloak Server Administration Guide + REST API (RealmRepresentation, ClientRepresentation) + source code Constants.java | authoritative | 78 | No |
| `kubernetes` | kubernetes | Kubernetes API Reference (v1.29+) | authoritative | 50 | Yes |
| `mariadb-mysql` | mariadb-mysql | MySQL 8.0 Reference Manual + MariaDB 10.11 Server System Variables | authoritative | 76 | No |
| `mongodb` | mongodb | MongoDB Manual -- Configuration File Options (v8.0) | authoritative | 15 | No |
| `opentelemetry-collector` | opentelemetry-collector | OpenTelemetry Collector source code (v0.110.0+) | authoritative | 19 | No |
| `postgresql` | postgresql | PostgreSQL Documentation -- Server Configuration (v17) | authoritative | 169 | No |
| `prometheus` | prometheus | Prometheus source code (config/config.go) + configuration reference | authoritative | 62 | Yes |
| `redis` | redis | Redis 7.0 redis.conf reference | authoritative | 61 | No |
| `sshd-config` | sshd-config | OpenSSH 9.x sshd_config(5) man page | authoritative | 35 | No |
| `terraform-state` | terraform-state | Terraform state file format v4 | authoritative | 0 | Yes |
| `traefik` | traefik | Traefik v3 documentation + configuration reference | authoritative | 57 | Yes |

**Total: 1,494 platform defaults across 25 schemas.**

---

## Schemas by Category

### 1. Container & Orchestration

#### docker-compose

- **Short name:** `docker-compose`
- **Platform:** docker-compose
- **Source:** Docker Compose specification + compose-go source
- **Confidence:** authoritative
- **Number of defaults:** 35
- **Key defaults:**
  - `services.*.restart`: `"no"` -- most services do not restart by default
  - `services.*.privileged`: `false`
  - `services.*.network_mode`: `bridge`
  - `services.*.logging.driver`: `json-file`
  - `services.*.deploy.replicas`: `1`
  - `services.*.healthcheck.interval`: `30s`
  - `services.*.healthcheck.retries`: `3`
  - `services.*.ports.*.protocol`: `tcp`
  - `services.*.depends_on.*.condition`: `service_started`
  - `networks.*.driver`: `bridge`
- **Drop patterns:** none
- **System-managed fields:** none
- **Auto-detection:** Yes -- document contains a `"services"` key with a dict value

#### kubernetes

- **Short name:** `kubernetes`
- **Platform:** kubernetes
- **Source:** Kubernetes API Reference (v1.29+)
- **Confidence:** authoritative
- **Number of defaults:** 50
- **Key defaults:**
  - `**.restartPolicy`: `Always`
  - `**.terminationGracePeriodSeconds`: `30`
  - `**.containers.*.imagePullPolicy`: `IfNotPresent`
  - `**.containers.*.ports.*.protocol`: `TCP`
  - `**.containers.*.securityContext.allowPrivilegeEscalation`: `true`
  - `spec.replicas`: `1`
  - `spec.revisionHistoryLimit`: `10`
  - `spec.strategy.type`: `RollingUpdate`
  - `spec.type`: `ClusterIP`
  - `spec.sessionAffinity`: `None`
- **Drop patterns:** none
- **System-managed fields:** `metadata.uid`, `metadata.resourceVersion`, `metadata.generation`, `metadata.creationTimestamp`, `metadata.managedFields`, `status`
- **Auto-detection:** Yes -- document contains both `"apiVersion"` and `"kind"` keys

---

### 2. Configuration Management

#### ansible-playbook

- **Short name:** `ansible-playbook`
- **Platform:** ansible-playbook
- **Source:** Ansible builtin module documentation
- **Confidence:** authoritative
- **Number of defaults:** 132
- **Key defaults:**
  - `*.gather_facts`: `true`
  - `*.become`: `false`
  - `**.apt.state`: `present`
  - `**.dnf.state`: `present`
  - `**.systemd.scope`: `system`
  - `**.copy.force`: `true`
  - `**.template.trim_blocks`: `true`
  - `**.user.state`: `present`
  - `**.user.create_home`: `true`
  - `**.git.version`: `HEAD`
- **Drop patterns:** none
- **System-managed fields:** none
- **Auto-detection:** Yes -- document is a list where the first item has `"hosts"` and either `"tasks"` or `"roles"`

#### cloud-init

- **Short name:** `cloud-init`
- **Platform:** cloud-init
- **Source:** cloud-init upstream JSON Schema (schema-cloud-config-v1.json)
- **Confidence:** authoritative
- **Number of defaults:** 55
- **Key defaults:**
  - `package_update`: `false`
  - `package_upgrade`: `false`
  - `disable_root`: `true`
  - `ssh_deletekeys`: `true`
  - `users.*.lock_passwd`: `true`
  - `growpart.mode`: `auto`
  - `write_files.*.permissions`: `"0644"`
  - `write_files.*.append`: `false`
  - `ntp.enabled`: `true`
  - `preserve_hostname`: `false`
- **Drop patterns:** none
- **System-managed fields:** none
- **Auto-detection:** Yes -- document contains 2 or more cloud-init keys from the set: `packages`, `runcmd`, `write_files`, `users`, `ssh_authorized_keys`, `growpart`, `ntp`

#### sshd-config

- **Short name:** `sshd-config`
- **Platform:** sshd-config
- **Source:** OpenSSH 9.x sshd_config(5) man page
- **Confidence:** authoritative
- **Number of defaults:** 35
- **Key defaults:**
  - `Port`: `22`
  - `PermitRootLogin`: `prohibit-password`
  - `PasswordAuthentication`: `yes`
  - `PubkeyAuthentication`: `yes`
  - `MaxAuthTries`: `6`
  - `MaxSessions`: `10`
  - `X11Forwarding`: `no`
  - `AllowTcpForwarding`: `yes`
  - `LogLevel`: `INFO`
  - `Compression`: `yes`
- **Drop patterns:** none
- **System-managed fields:** none
- **Auto-detection:** No

---

### 3. Infrastructure as Code

#### terraform-state

- **Short name:** `terraform-state`
- **Platform:** terraform-state
- **Source:** Terraform state file format v4
- **Confidence:** authoritative
- **Number of defaults:** 0
- **Key defaults:** none -- this schema relies entirely on system-managed field removal
- **Drop patterns:** none
- **System-managed fields:** `version`, `serial`, `lineage`, `terraform_version`, `outputs.*.type`, `resources.*.instances.*.schema_version`, `resources.*.instances.*.sensitive_attributes`, `resources.*.instances.*.private`, `resources.*.instances.*.dependencies`
- **Auto-detection:** Yes -- document contains both `"terraform_version"` and `"resources"` keys

#### aws-cloudformation

- **Short name:** `aws-cloudformation`
- **Platform:** aws-cloudformation
- **Source:** AWS CloudFormation Resource Specification + AWS Service Documentation
- **Confidence:** authoritative
- **Number of defaults:** 56
- **Key defaults:**
  - `**.SourceDestCheck`: `true` (EC2)
  - `**.PublicAccessBlockConfiguration.BlockPublicAcls`: `true` (S3)
  - `**.MultiAZ`: `false` (RDS)
  - `**.AutoMinorVersionUpgrade`: `true` (RDS)
  - `**.Timeout`: `3` (Lambda)
  - `**.MemorySize`: `128` (Lambda)
  - `**.DesiredCount`: `1` (ECS)
  - `**.VisibilityTimeout`: `30` (SQS)
  - `**.BillingMode`: `PROVISIONED` (DynamoDB)
  - `**.HealthCheckType`: `EC2` (Auto Scaling)
- **Drop patterns:** none
- **System-managed fields:** `**.PhysicalResourceId`, `**.StackId`, `**.LogicalResourceId`, `**.CreationTime`, `**.LastUpdatedTime`, `**.ResourceStatus`, `**.DriftInformation`
- **Auto-detection:** No

#### azure-arm

- **Short name:** `azure-arm`
- **Platform:** azure-arm
- **Source:** Azure ARM/Bicep Template Reference (learn.microsoft.com)
- **Confidence:** authoritative
- **Number of defaults:** 65
- **Key defaults:**
  - `**.properties.osProfile.linuxConfiguration.provisionVMAgent`: `true`
  - `**.properties.priority`: `Regular`
  - `**.properties.storageProfile.osDisk.deleteOption`: `Detach`
  - `**.properties.allowBlobPublicAccess`: `false` (Storage)
  - `**.properties.supportsHttpsTrafficOnly`: `true` (Storage)
  - `**.properties.minimumTlsVersion`: `TLS1_0` (Storage)
  - `**.properties.clientAffinityEnabled`: `true` (App Service)
  - `**.properties.enabled`: `true` (App Service)
  - `**.properties.siteConfig.http20Enabled`: `true` (App Service)
  - `**.properties.siteConfig.managedPipelineMode`: `Integrated` (App Service)
- **Drop patterns:** none
- **System-managed fields:** 20 fields including `**.properties.provisioningState`, `**.properties.vmId`, `**.properties.primaryEndpoints`, `**.properties.creationTime`, `**.etag`, and others
- **Auto-detection:** No

#### gcp-resources

- **Short name:** `gcp-resources`
- **Platform:** gcp-resources
- **Source:** GCP REST API Reference + Google Cloud Documentation
- **Confidence:** authoritative
- **Number of defaults:** 42
- **Key defaults:**
  - `**.scheduling.automaticRestart`: `true` (Compute Engine)
  - `**.scheduling.onHostMaintenance`: `MIGRATE` (Compute Engine)
  - `**.canIpForward`: `false` (Compute Engine)
  - `**.disks.*.autoDelete`: `true` (Compute Engine)
  - `**.initialNodeCount`: `3` (GKE)
  - `**.nodeConfig.diskSizeGb`: `100` (GKE)
  - `**.management.autoRepair`: `true` (GKE)
  - `**.settings.activationPolicy`: `ALWAYS` (Cloud SQL)
  - `**.storageClass`: `STANDARD` (Cloud Storage)
  - `**.template.spec.containerConcurrency`: `80` (Cloud Run)
- **Drop patterns:** none
- **System-managed fields:** `**.id`, `**.selfLink`, `**.creationTimestamp`, `**.status`, `**.fingerprint`, `**.zone`, `**.labelFingerprint`
- **Auto-detection:** No

---

### 4. CI/CD

#### github-actions

- **Short name:** `github-actions`
- **Platform:** github-actions
- **Source:** GitHub Actions documentation + SchemaStore github-workflow.json schema
- **Confidence:** authoritative
- **Number of defaults:** 8
- **Key defaults:**
  - `jobs.*.timeout-minutes`: `360`
  - `jobs.*.continue-on-error`: `false`
  - `jobs.*.steps.*.continue-on-error`: `false`
  - `jobs.*.strategy.fail-fast`: `true`
  - `concurrency.cancel-in-progress`: `false`
  - `jobs.*.concurrency.cancel-in-progress`: `false`
  - `on.workflow_call.inputs.*.required`: `false`
  - `on.workflow_dispatch.inputs.*.required`: `false`
- **Drop patterns:** none
- **System-managed fields:** none
- **Auto-detection:** Yes -- document contains both `"on"` and `"jobs"` keys

#### gitlab-ci

- **Short name:** `gitlab-ci`
- **Platform:** gitlab-ci
- **Source:** GitLab CI/CD YAML syntax reference + CI/CD settings documentation
- **Confidence:** authoritative
- **Number of defaults:** 25
- **Key defaults:**
  - `*.when`: `on_success`
  - `*.allow_failure`: `false`
  - `*.interruptible`: `false`
  - `*.retry`: `0`
  - `*.artifacts.expire_in`: `30 days`
  - `*.artifacts.public`: `true`
  - `*.cache.key`: `default`
  - `*.cache.policy`: `pull-push`
  - `*.environment.action`: `start`
  - `*.services.*.pull_policy`: `always`
- **Drop patterns:** none
- **System-managed fields:** none
- **Auto-detection:** No

#### argocd

- **Short name:** `argocd`
- **Platform:** argocd
- **Source:** ArgoCD CRD spec + official documentation
- **Confidence:** authoritative
- **Number of defaults:** 14
- **Key defaults:**
  - `spec.project`: `default`
  - `spec.source.targetRevision`: `HEAD`
  - `spec.source.helm.passCredentials`: `false`
  - `spec.source.helm.skipCrds`: `false`
  - `spec.source.directory.recurse`: `false`
  - `spec.syncPolicy.automated.prune`: `false`
  - `spec.syncPolicy.automated.selfHeal`: `false`
  - `spec.syncPolicy.retry.limit`: `0`
  - `spec.syncPolicy.retry.backoff.duration`: `5s`
  - `spec.revisionHistoryLimit`: `10`
- **Drop patterns:** none
- **System-managed fields:** `metadata.uid`, `metadata.resourceVersion`, `metadata.generation`, `metadata.creationTimestamp`, `metadata.managedFields`, `status`
- **Auto-detection:** No

---

### 5. Databases

#### postgresql

- **Short name:** `postgresql`
- **Platform:** postgresql
- **Source:** PostgreSQL Documentation -- Server Configuration (v17)
- **Confidence:** authoritative
- **Number of defaults:** 169
- **Key defaults:**
  - `listen_addresses`: `localhost`
  - `port`: `5432`
  - `max_connections`: `100`
  - `shared_buffers`: `128MB`
  - `work_mem`: `4MB`
  - `wal_level`: `replica`
  - `max_wal_size`: `1GB`
  - `effective_cache_size`: `4GB`
  - `log_destination`: `stderr`
  - `autovacuum`: `on`
- **Drop patterns:** none
- **System-managed fields:** none
- **Auto-detection:** No

#### mariadb-mysql

- **Short name:** `mariadb-mysql`
- **Platform:** mariadb-mysql
- **Source:** MySQL 8.0 Reference Manual + MariaDB 10.11 Server System Variables
- **Confidence:** authoritative
- **Number of defaults:** 76
- **Key defaults:**
  - `port`: `3306`
  - `max_connections`: `151`
  - `default_storage_engine`: `InnoDB`
  - `innodb_flush_log_at_trx_commit`: `1`
  - `innodb_file_per_table`: `ON`
  - `character_set_server`: `utf8mb4`
  - `sync_binlog`: `1`
  - `max_allowed_packet`: `67108864`
  - `autocommit`: `ON`
  - `performance_schema`: `ON`
- **Drop patterns:** none
- **System-managed fields:** none
- **Auto-detection:** No

#### mongodb

- **Short name:** `mongodb`
- **Platform:** mongodb
- **Source:** MongoDB Manual -- Configuration File Options (v8.0)
- **Confidence:** authoritative
- **Number of defaults:** 15
- **Key defaults:**
  - `storage.dbPath`: `/data/db`
  - `storage.engine`: `wiredTiger`
  - `storage.directoryPerDB`: `false`
  - `storage.journal.commitIntervalMs`: `100`
  - `net.port`: `27017`
  - `net.bindIp`: `"127.0.0.1"`
  - `net.ipv6`: `false`
  - `security.authorization`: `disabled`
  - `operationProfiling.mode`: `"off"`
  - `operationProfiling.slowOpThresholdMs`: `100`
- **Drop patterns:** none
- **System-managed fields:** none
- **Auto-detection:** No

#### redis

- **Short name:** `redis`
- **Platform:** redis
- **Source:** Redis 7.0 redis.conf reference
- **Confidence:** authoritative
- **Number of defaults:** 61
- **Key defaults:**
  - `port`: `6379`
  - `protected-mode`: `yes`
  - `tcp-keepalive`: `300`
  - `databases`: `16`
  - `loglevel`: `notice`
  - `appendonly`: `no`
  - `appendfsync`: `everysec`
  - `replica-read-only`: `yes`
  - `repl-diskless-sync`: `yes`
  - `hz`: `10`
- **Drop patterns:** none
- **System-managed fields:** none
- **Auto-detection:** No

#### kafka

- **Short name:** `kafka`
- **Platform:** kafka
- **Source:** Apache Kafka Documentation -- Broker Configs (v3.7+)
- **Confidence:** authoritative
- **Number of defaults:** 63
- **Key defaults:**
  - `listeners`: `PLAINTEXT://:9092`
  - `log.dirs`: `/tmp/kafka-logs`
  - `log.segment.bytes`: `1073741824`
  - `log.retention.hours`: `168`
  - `num.partitions`: `1`
  - `default.replication.factor`: `1`
  - `auto.create.topics.enable`: `true`
  - `min.insync.replicas`: `1`
  - `num.io.threads`: `8`
  - `offsets.topic.replication.factor`: `3`
- **Drop patterns:** none
- **System-managed fields:** none
- **Auto-detection:** No

---

### 6. Observability

#### prometheus

- **Short name:** `prometheus`
- **Platform:** prometheus
- **Source:** Prometheus source code (config/config.go) + configuration reference
- **Confidence:** authoritative
- **Number of defaults:** 62
- **Key defaults:**
  - `global.scrape_interval`: `1m`
  - `global.scrape_timeout`: `10s`
  - `global.evaluation_interval`: `1m`
  - `scrape_configs.*.metrics_path`: `/metrics`
  - `scrape_configs.*.scheme`: `http`
  - `scrape_configs.*.honor_labels`: `false`
  - `scrape_configs.*.honor_timestamps`: `true`
  - `scrape_configs.*.relabel_configs.*.action`: `replace`
  - `alerting.alertmanagers.*.scheme`: `http`
  - `remote_write.*.remote_timeout`: `30s`
- **Drop patterns:** none
- **System-managed fields:** none
- **Auto-detection:** Yes -- document contains a `"scrape_configs"` key

#### grafana

- **Short name:** `grafana`
- **Platform:** grafana
- **Source:** Grafana defaults.ini (github.com/grafana/grafana/blob/main/conf/defaults.ini)
- **Confidence:** authoritative
- **Number of defaults:** 162
- **Key defaults:**
  - `server.protocol`: `http`
  - `server.http_port`: `3000`
  - `database.type`: `sqlite3`
  - `security.admin_user`: `admin`
  - `security.cookie_samesite`: `lax`
  - `users.allow_sign_up`: `false`
  - `users.auto_assign_org_role`: `Viewer`
  - `auth.basic.enabled`: `true`
  - `log.level`: `info`
  - `unified_alerting.max_attempts`: `3`
- **Drop patterns:** none
- **System-managed fields:** none
- **Auto-detection:** No

#### opentelemetry-collector

- **Short name:** `opentelemetry-collector`
- **Platform:** opentelemetry-collector
- **Source:** OpenTelemetry Collector source code (v0.110.0+)
- **Confidence:** authoritative
- **Number of defaults:** 19
- **Key defaults:**
  - `service.telemetry.metrics.level`: `normal`
  - `processors.batch.send_batch_size`: `8192`
  - `processors.batch.timeout`: `200ms`
  - `receivers.otlp.protocols.grpc.endpoint`: `"localhost:4317"`
  - `receivers.otlp.protocols.http.endpoint`: `"localhost:4318"`
  - `exporters.otlp.compression`: `gzip`
  - `exporters.otlp.timeout`: `5s`
  - `exporters.otlp.retry_on_failure.enabled`: `true`
  - `exporters.otlp.sending_queue.enabled`: `true`
  - `exporters.debug.verbosity`: `basic`
- **Drop patterns:** none
- **System-managed fields:** none
- **Auto-detection:** No

#### fluent-bit

- **Short name:** `fluent-bit`
- **Platform:** fluent-bit
- **Source:** Fluent Bit Official Manual -- Service, Input, Output, Filter configuration reference
- **Confidence:** authoritative
- **Number of defaults:** 75
- **Key defaults:**
  - `service.flush`: `1`
  - `service.daemon`: `"off"`
  - `service.log_level`: `info`
  - `service.grace`: `5`
  - `pipeline.inputs.*.refresh_interval`: `60`
  - `pipeline.inputs.*.read_from_head`: `false`
  - `pipeline.inputs.*.key`: `log`
  - `pipeline.outputs.*.retry_limit`: `1`
  - `pipeline.outputs.*.workers`: `2`
  - `pipeline.outputs.*.net.keepalive`: `true`
- **Drop patterns:** none
- **System-managed fields:** none
- **Auto-detection:** No

---

### 7. Networking

#### traefik

- **Short name:** `traefik`
- **Platform:** traefik
- **Source:** Traefik v3 documentation + configuration reference
- **Confidence:** authoritative
- **Number of defaults:** 57
- **Key defaults:**
  - `global.checkNewVersion`: `true`
  - `entryPoints.*.transport.respondingTimeouts.readTimeout`: `60s`
  - `entryPoints.*.transport.respondingTimeouts.idleTimeout`: `180s`
  - `providers.docker.endpoint`: `"unix:///var/run/docker.sock"`
  - `providers.docker.exposedByDefault`: `true`
  - `api.dashboard`: `true`
  - `api.insecure`: `false`
  - `log.level`: `ERROR`
  - `serversTransport.maxIdleConnsPerHost`: `200`
  - `serversTransport.forwardingTimeouts.dialTimeout`: `30s`
- **Drop patterns:** none
- **System-managed fields:** none
- **Auto-detection:** Yes -- document contains `"entryPoints"` key, or both `"providers"` and one of `"api"` / `"log"`

---

### 8. Identity & Device Management

#### keycloak

- **Short name:** `keycloak`
- **Platform:** keycloak
- **Source:** Keycloak Server Administration Guide + REST API (RealmRepresentation, ClientRepresentation) + source code Constants.java
- **Confidence:** authoritative
- **Number of defaults:** 78
- **Key defaults:**
  - `enabled`: `true`
  - `sslRequired`: `external`
  - `registrationAllowed`: `false`
  - `loginWithEmailAllowed`: `true`
  - `accessTokenLifespan`: `300`
  - `ssoSessionIdleTimeout`: `1800`
  - `bruteForceProtected`: `false`
  - `clients.*.protocol`: `openid-connect`
  - `clients.*.standardFlowEnabled`: `true`
  - `clients.*.fullScopeAllowed`: `true`
- **Drop patterns:** none
- **System-managed fields:** `**.id`, `**.internalId`, `**.containerId`, `clients.*.registeredNodes`, `clients.*.notBefore`, `notBefore`
- **Auto-detection:** No

#### entra-id

- **Short name:** `entra-id`
- **Platform:** entra-id
- **Source:** Microsoft Graph API v1.0 Reference (learn.microsoft.com)
- **Confidence:** authoritative
- **Number of defaults:** 44
- **Key defaults:**
  - `**.signInAudience`: `AzureADMyOrg`
  - `**.accountEnabled`: `true`
  - `**.appRoleAssignmentRequired`: `false`
  - `**.servicePrincipalType`: `Application`
  - `**.isAssignableToRole`: `false`
  - `**.isTrusted`: `false`
  - `**.allowInvitesFrom`: `everyone`
  - `**.blockMsolPowerShell`: `false`
  - `**.grantControls.operator`: `OR`
  - `**.b2bCollaborationInbound.applications.accessType`: `allowed`
- **Drop patterns:** none
- **System-managed fields:** 21 fields including `id`, `**.id`, `createdDateTime`, `modifiedDateTime`, `**.appId`, `**.publisherDomain`, `**.proxyAddresses`, `**.securityIdentifier`, and others
- **Auto-detection:** No

#### intune

- **Short name:** `intune`
- **Platform:** intune
- **Source:** Microsoft Graph API v1.0 Intune Reference (learn.microsoft.com)
- **Confidence:** authoritative
- **Number of defaults:** 96
- **Key defaults:**
  - `**.windows10CompliancePolicy.passwordRequired`: `false`
  - `**.windows10CompliancePolicy.bitLockerEnabled`: `false`
  - `**.iosCompliancePolicy.passcodeRequired`: `false`
  - `**.iosCompliancePolicy.securityBlockJailbrokenDevices`: `false`
  - `**.androidCompliancePolicy.passwordRequired`: `false`
  - `**.macOSCompliancePolicy.firewallEnabled`: `false`
  - `**.deviceComplianceRequired`: `true`
  - `**.pinRequired`: `true`
  - `**.minimumPinLength`: `4`
  - `**.periodOfflineBeforeWipeIsEnforced`: `"P90D"`
- **Drop patterns:** none
- **System-managed fields:** `**.id`, `**.createdDateTime`, `**.lastModifiedDateTime`, `**.version`, `**.roleScopeTagIds`, `**.'@odata.type'`, `**.'@odata.context'`
- **Auto-detection:** No

---

## Auto-Detection

Eight platforms support automatic detection via `detect_platform()` in `formats.py`. When using `decoct` without `--schema`, the tool examines document structure to select the right schema automatically.

| Platform | Detection Rule |
|---|---|
| Docker Compose | Document contains a `"services"` key with a dict value |
| Kubernetes | Document contains both `"apiVersion"` and `"kind"` keys |
| Ansible Playbook | Document is a list where the first element has `"hosts"` and either `"tasks"` or `"roles"` |
| cloud-init | Document contains 2 or more keys from: `packages`, `runcmd`, `write_files`, `users`, `ssh_authorized_keys`, `growpart`, `ntp` |
| Terraform State | Document contains both `"terraform_version"` and `"resources"` keys |
| GitHub Actions | Document contains both `"on"` and `"jobs"` keys |
| Traefik | Document contains `"entryPoints"`, or both `"providers"` and one of `"api"` / `"log"` |
| Prometheus | Document contains a `"scrape_configs"` key |

For all other platforms, pass the schema name explicitly with `--schema <name>`.
