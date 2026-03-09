# Bundled Assertions Reference

## deployment-standards.yaml

### Overview

This assertion set encodes container deployment standards for Docker Compose services. It covers image versioning, restart policies, health checks, logging, security, and networking. All assertions reference the `OPS-DOCKER-001` source standard.

The set contains 12 assertions: 7 with `must` severity, 5 with `should` severity. Ten of the twelve have machine-evaluable `match` conditions; the remaining two (`ops-resource-limits`, `ops-named-networks`) are LLM-context only.

### Usage

```bash
decoct compress docker-compose.yml --assertions deployment-standards
# or via the docker-compose profile:
decoct compress docker-compose.yml --profile docker-compose
```

### Assertions

---

#### `ops-image-pinned`

- **Severity:** must
- **Assertion:** Image tags must be pinned to specific versions, not :latest
- **Rationale:** Pinned versions ensure reproducible deployments and auditable rollbacks
- **Match:**
  - Path: `services.*.image`
  - Condition: `pattern` = `^(?!.*:latest$)(?=.*:.+$)` -- the image string must contain a colon followed by a tag, and that tag must not be `latest`.
- **Example (conformant):** `nginx:1.25.3`
- **Example (non-conformant):** `nginx:latest` or `nginx` (no tag at all)
- **Exceptions:** None
- **Pipeline effect:** When the image value matches the pattern (conformant), the `strip-conformant` pass removes the `image` key from the output, recording its class for reconstitution. When the value does not match, the `annotate-deviations` pass adds an inline comment: `[!] assertion: Image tags must be pinned to specific versions, not :latest`.

---

#### `ops-restart-policy`

- **Severity:** must
- **Assertion:** Restart policy must be unless-stopped or always
- **Rationale:** Services must automatically recover from crashes
- **Match:**
  - Path: `services.*.restart`
  - Condition: `pattern` = `^(unless-stopped|always)$` -- the restart value must be exactly `unless-stopped` or `always`.
- **Example (conformant):** `unless-stopped`
- **Example (non-conformant):** `no` or `on-failure`
- **Exceptions:** None
- **Pipeline effect:** Conformant values are stripped by `strip-conformant`. Non-conformant values receive an inline annotation: `[!] assertion: Restart policy must be unless-stopped or always`.

---

#### `ops-container-name`

- **Severity:** must
- **Assertion:** Container name must be explicitly set
- **Rationale:** Explicit naming prevents Docker-generated names and aids log correlation
- **Match:**
  - Path: `services.*.container_name`
  - Condition: `exists` = `true` -- the key must be present.
- **Example (conformant):** `container_name: acme-app-web`
- **Example (non-conformant):** The `container_name` key is absent from the service definition.
- **Exceptions:** None
- **Pipeline effect:** Because this is an `exists` assertion, the `strip-conformant` pass skips it (there is no value to strip for presence checks). The `annotate-deviations` pass detects missing keys and records a deviation: `[!] missing: Container name must be explicitly set`. Note that YAML inline comments cannot be attached to absent keys, so the deviation appears only in the pass report.

---

#### `ops-healthcheck`

- **Severity:** must
- **Assertion:** All application containers must have health checks configured
- **Rationale:** Health checks enable proper orchestration, dependency ordering, and monitoring
- **Match:**
  - Path: `services.*.healthcheck`
  - Condition: `exists` = `true` -- the key must be present.
- **Example (conformant):** A `healthcheck` block with `test`, `interval`, `timeout`, and `retries` defined.
- **Example (non-conformant):** The `healthcheck` key is absent from the service definition.
- **Exceptions:** Infrastructure-only containers (redis, postgres) may rely on built-in health mechanisms
- **Pipeline effect:** Same as `ops-container-name` -- `strip-conformant` skips exists assertions; `annotate-deviations` records a deviation for absent keys but cannot attach an inline YAML comment.

---

#### `ops-logging-driver`

- **Severity:** must
- **Assertion:** Logging driver must be json-file
- **Rationale:** Consistent json-file logging enables centralised log collection
- **Match:**
  - Path: `services.*.logging.driver`
  - Condition: `value` = `json-file` -- the logging driver must be exactly the string `json-file`.
- **Example (conformant):** `driver: json-file`
- **Example (non-conformant):** `driver: syslog` or `driver: fluentd`
- **Exceptions:** None
- **Pipeline effect:** Conformant values are stripped by `strip-conformant`. Non-conformant values receive an inline annotation showing the expected standard: `[!] standard: json-file`.

---

#### `ops-logging-max-size`

- **Severity:** must
- **Assertion:** Log rotation max-size must be configured
- **Rationale:** Unbounded logs cause disk exhaustion
- **Match:**
  - Path: `services.*.logging.options.max-size`
  - Condition: `pattern` = `.+` -- the value must be a non-empty string (any value is acceptable as long as it is set).
- **Example (conformant):** `max-size: "10m"`
- **Example (non-conformant):** The `max-size` key is absent or empty.
- **Exceptions:** None
- **Pipeline effect:** Conformant values (any non-empty string) are stripped by `strip-conformant`. When the field is absent, `annotate-deviations` records a deviation.

---

#### `ops-logging-max-file`

- **Severity:** must
- **Assertion:** Log rotation max-file must be configured
- **Rationale:** Log file count must be bounded to prevent disk exhaustion
- **Match:**
  - Path: `services.*.logging.options.max-file`
  - Condition: `pattern` = `.+` -- the value must be a non-empty string.
- **Example (conformant):** `max-file: "3"`
- **Example (non-conformant):** The `max-file` key is absent or empty.
- **Exceptions:** None
- **Pipeline effect:** Same as `ops-logging-max-size` -- conformant values are stripped; absent values produce a deviation.

---

#### `ops-security-opt`

- **Severity:** should
- **Assertion:** Containers should set no-new-privileges security option
- **Rationale:** Prevents privilege escalation via setuid/setgid binaries
- **Match:**
  - Path: `services.*.security_opt`
  - Condition: `contains` = `no-new-privileges:true` -- the `security_opt` list must include the string `no-new-privileges:true`.
- **Example (conformant):** `security_opt: ["no-new-privileges:true"]`
- **Example (non-conformant):** `security_opt` is absent, empty, or does not contain `no-new-privileges:true`.
- **Exceptions:** None
- **Pipeline effect:** Because the severity is `should` (not `must`), the `strip-conformant` pass does not remove conformant values. The `annotate-deviations` pass checks all severities and annotates non-conformant values with: `[!] assertion: Containers should set no-new-privileges security option`.

---

#### `ops-no-privileged`

- **Severity:** must
- **Assertion:** Containers must not run in privileged mode
- **Rationale:** Privileged mode gives full host access, violating container isolation
- **Match:**
  - Path: `services.*.privileged`
  - Condition: `value` = `false` -- the `privileged` key, if present, must be `false`.
- **Example (conformant):** `privileged: false`
- **Example (non-conformant):** `privileged: true`
- **Exceptions:** None
- **Pipeline effect:** Conformant values (`false`) are stripped by `strip-conformant`. Non-conformant values receive an inline annotation: `[!] standard: false`.

---

#### `ops-resource-limits`

- **Severity:** should
- **Assertion:** Production and multi-container stacks should define resource limits
- **Rationale:** Resource limits prevent runaway containers from exhausting host resources
- **Match:** None -- this assertion has no `match` condition and is not machine-evaluable.
- **Example (conformant):** A `deploy.resources.limits` block with `cpus` and `memory` set.
- **Example (non-conformant):** No resource limits defined in the service.
- **Exceptions:** Single-container development stacks may omit limits
- **Pipeline effect:** No automated stripping or annotation. This assertion is included as LLM context only -- when decoct output is consumed by an LLM, the assertion text provides guidance for reasoning about the configuration.

---

#### `ops-named-networks`

- **Severity:** should
- **Assertion:** Services should use named networks, not the default bridge
- **Rationale:** Named networks provide DNS resolution and isolation between stacks
- **Match:** None -- this assertion has no `match` condition and is not machine-evaluable.
- **Example (conformant):** `networks: [app-net]` with a corresponding top-level `networks` definition.
- **Example (non-conformant):** No `networks` key, causing Docker to place the service on the default bridge.
- **Exceptions:** None
- **Pipeline effect:** LLM context only. No automated stripping or annotation.

---

#### `ops-no-host-0000`

- **Severity:** should
- **Assertion:** Ports must not bind to 0.0.0.0; use specific IPs or 127.0.0.1
- **Rationale:** Binding to all interfaces exposes services beyond intended network boundaries
- **Match:** None -- this assertion has no `match` condition and is not machine-evaluable.
- **Example (conformant):** `ports: ["127.0.0.1:8080:8080"]`
- **Example (non-conformant):** `ports: ["0.0.0.0:8080:8080"]` or `ports: ["8080:8080"]` (Docker defaults to 0.0.0.0)
- **Exceptions:** Containers behind reverse proxy should bind to 127.0.0.1; management services bind to management IP
- **Pipeline effect:** LLM context only. No automated stripping or annotation.

---

### Coverage Summary

| Area | Assertions | Machine-Evaluable |
|------|-----------|-------------------|
| Image versioning | `ops-image-pinned` | Yes |
| Restart policy | `ops-restart-policy` | Yes |
| Container naming | `ops-container-name` | Yes |
| Health checks | `ops-healthcheck` | Yes |
| Logging | `ops-logging-driver`, `ops-logging-max-size`, `ops-logging-max-file` | Yes |
| Security | `ops-security-opt`, `ops-no-privileged` | Yes |
| Resources | `ops-resource-limits` | No |
| Networking | `ops-named-networks`, `ops-no-host-0000` | No |

### Known Limitations

- **Absent-field detection:** Assertions with `exists: true` check for presence but cannot report on services that entirely lack the field. The deviation is recorded in the pass report but no inline YAML comment can be attached to a missing key.
- **Pattern matching on variable substitution:** `${IMAGE_TAG:-latest}` passes the `ops-image-pinned` check because the literal string does not end with `:latest` -- the shell variable syntax is not expanded during evaluation.
- **Resource limits assertion has no match:** `ops-resource-limits` is LLM-context only and cannot be machine-evaluated. A future version may add path-based existence checks for `deploy.resources.limits`.
- **Port binding assertion has no match:** `ops-no-host-0000` requires parsing port mapping syntax (e.g., `"0.0.0.0:8080:8080"`) which is not yet supported by the match condition model.
- **`should`-severity stripping:** The `strip-conformant` pass only removes values for `must`-severity assertions. Conformant `should` values remain in the output, which is by design -- `should` conformance is less certain and the context may be useful to an LLM reviewer.
