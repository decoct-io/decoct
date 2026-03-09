# Phase 2 Development Plan — decoct

Phase 2 transitions decoct from toy fixtures to real-world validation.
Each work item includes acceptance criteria and depends on Phase 1 completion.

---

## 2.1 Comprehensive Docker Compose Schema

**Goal:** Expand Docker Compose schema from 6 defaults to ~40.

**Source:** [Compose Specification](https://github.com/compose-spec/compose-spec/blob/main/spec.md) + compose-go struct tags.

**Defaults to add:**

| Category | Path Pattern | Default Value |
|----------|-------------|---------------|
| Service | `services.*.privileged` | `false` |
| Service | `services.*.read_only` | `false` |
| Service | `services.*.stdin_open` | `false` |
| Service | `services.*.tty` | `false` |
| Service | `services.*.init` | `false` |
| Service | `services.*.restart` | `"no"` |
| Network | `services.*.network_mode` | `bridge` |
| Healthcheck | `services.*.healthcheck.interval` | `30s` |
| Healthcheck | `services.*.healthcheck.timeout` | `30s` |
| Healthcheck | `services.*.healthcheck.retries` | `3` |
| Healthcheck | `services.*.healthcheck.start_period` | `0s` |
| Healthcheck | `services.*.healthcheck.start_interval` | `5s` |
| Logging | `services.*.logging.driver` | `json-file` |
| Deploy | `services.*.deploy.replicas` | `1` |
| Deploy | `services.*.deploy.restart_policy.condition` | `any` |
| Deploy | `services.*.deploy.restart_policy.max_attempts` | `0` |
| Deploy | `services.*.deploy.update_config.parallelism` | `1` |
| Deploy | `services.*.deploy.update_config.order` | `stop-first` |
| Deploy | `services.*.deploy.rollback_config.parallelism` | `1` |
| Deploy | `services.*.deploy.rollback_config.order` | `stop-first` |
| Ports | `services.*.ports.*.protocol` | `tcp` |
| Ports | `services.*.ports.*.mode` | `ingress` |
| depends_on | `services.*.depends_on.*.condition` | `service_started` |
| depends_on | `services.*.depends_on.*.required` | `true` |
| depends_on | `services.*.depends_on.*.restart` | `true` |
| Networks | `networks.*.driver` | `bridge` |
| Networks | `networks.*.external` | `false` |
| Networks | `networks.*.internal` | `false` |
| Networks | `networks.*.attachable` | `false` |
| Networks | `networks.*.enable_ipv6` | `false` |
| Volumes | `volumes.*.external` | `false` |
| Build | `services.*.build.pull` | `false` |
| Build | `services.*.build.no_cache` | `false` |
| Secrets | `secrets.*.external` | `false` |
| Configs | `configs.*.external` | `false` |

**Acceptance criteria:**
- [ ] Schema file with ~35-40 defaults loads via `load_schema()`
- [ ] `strip-defaults` removes all specified defaults from test fixture
- [ ] Confidence level: `authoritative`
- [ ] Existing tests still pass

---

## 2.2 Deployment Standards Assertions

**Goal:** Encode ENS-OPS-DOCKER-001 as ~12 machine-evaluable assertions.

**Source:** `enable-infra/docs/reference/deployment-standards.md`

**Assertions:**

| ID | Severity | Match Type | Evaluable |
|----|----------|------------|-----------|
| `ens-image-pinned` | must | pattern | Yes |
| `ens-restart-policy` | must | pattern | Yes |
| `ens-container-name` | must | pattern | Yes |
| `ens-healthcheck` | must | — | LLM-context |
| `ens-logging-driver` | must | value | Yes |
| `ens-logging-max-size` | must | pattern | Yes |
| `ens-logging-max-file` | must | pattern | Yes |
| `ens-security-opt` | should | contains | Yes |
| `ens-no-privileged` | must | value | Yes |
| `ens-resource-limits` | should | — | LLM-context |
| `ens-named-networks` | should | — | LLM-context |
| `ens-no-host-0000` | should | — | LLM-context |

**Acceptance criteria:**
- [ ] 12 assertions load via `load_assertions()`
- [ ] 8 assertions have `match` definitions (machine-evaluable)
- [ ] 4 assertions are LLM-context only (no `match`)
- [ ] `strip-conformant` correctly strips conformant values
- [ ] `annotate-deviations` correctly annotates non-conformant values
- [ ] `deviation-summary` produces accurate count

---

## 2.3 Baseline Measurement

**Goal:** Quantify token savings on real enable-infra data at three tiers.

**Method:** Run decoct against all 11 deployed compose files with `--stats`:
1. Generic only (strip-secrets + strip-comments)
2. Generic + schema (add strip-defaults with full compose schema)
3. Generic + schema + assertions (add strip-conformant, annotate-deviations)

**Acceptance criteria:**
- [ ] Token counts recorded for all 11 files at each tier
- [ ] Results documented in a markdown table
- [ ] Generic tier achieves ~10-15% savings
- [ ] Schema tier achieves ~30-45% savings
- [ ] Full tier achieves ~40-60% savings
- [ ] No real secrets appear in output

---

## 2.4 JSON Input Support

**Goal:** Accept JSON files as input, converting to CommentedMap for pipeline processing.

**Implementation:**
- New module `src/decoct/formats.py`:
  - `detect_format(path: Path) -> str` — returns `"json"` or `"yaml"` based on extension
  - `json_to_commented_map(data: Any) -> Any` — recursively converts `dict` → `CommentedMap`, `list` → `CommentedSeq`
  - `load_input(path: Path) -> tuple[Any, str]` — auto-detects format, returns `(doc, raw_text)`
- Modify `cli.py` to use `load_input()` instead of direct YAML parsing

**Acceptance criteria:**
- [ ] `.json` files auto-detected and loaded
- [ ] Nested objects become `CommentedMap`, arrays become `CommentedSeq`
- [ ] Scalar types (int, float, bool, null) preserved
- [ ] JSON-loaded documents roundtrip to valid YAML
- [ ] All pipeline passes work on JSON-loaded documents
- [ ] Existing YAML input behaviour unchanged

---

## 2.5 Bundled Schema Support

**Goal:** Ship common schemas with the package, accessible via short names.

**Implementation:**
- New module `src/decoct/schemas/resolver.py`:
  - `resolve_schema(name_or_path: str) -> Path` — if name matches a bundled schema, return its path; otherwise return the input as a path
  - `BUNDLED_SCHEMAS: dict[str, str]` — maps short names to bundled file paths
- New directory `src/decoct/schemas/bundled/` with `docker-compose.yaml`
- Modify `cli.py`: `--schema` accepts both paths and short names
- Modify `pyproject.toml`: include bundled schemas in package data

**Acceptance criteria:**
- [ ] `--schema docker-compose` resolves to bundled schema
- [ ] `--schema /path/to/schema.yaml` still works
- [ ] Unknown short names raise clear error
- [ ] Bundled schema loads and validates via `load_schema()`

---

## 2.6 Terraform State Schema

**Goal:** Strip system-managed fields from terraform state JSON.

**Schema fields:**
- Envelope: `version`, `serial`, `lineage`, `terraform_version`
- Per-resource: `resources.*.instances.*.private`, `resources.*.instances.*.sensitive_attributes`, `resources.*.instances.*.schema_version`
- Output metadata: `outputs.*.type`

**Acceptance criteria:**
- [ ] Schema loads via `load_schema()`
- [ ] `strip-defaults` removes envelope fields from tfstate
- [ ] Meaningful resource attributes preserved
- [ ] Works with JSON input (depends on 2.4)

---

## 2.7 cloud-init Schema

**Goal:** Import cloud-init defaults from upstream JSON Schema.

**Method:**
- Download `cloud-config-schema.json` from cloud-init package
- Parse JSON Schema `default` fields
- Convert to decoct schema format
- Ship as bundled schema

**Acceptance criteria:**
- [ ] ~30 defaults extracted from cloud-init schema
- [ ] Schema loads via `load_schema()`
- [ ] `--schema cloud-init` works (depends on 2.5)

---

## 2.8 Directory/Recursive Mode

**Goal:** Process multiple files in a directory, aggregate statistics.

**Implementation:**
- `decoct compress dir/` processes all `.yaml`, `.yml`, `.json` files
- `--recursive` flag for subdirectories
- Aggregate stats across all files
- Output to directory with `--output dir/`

**Acceptance criteria:**
- [ ] Directory argument processes all matching files
- [ ] `--recursive` descends into subdirectories
- [ ] Aggregate stats show total savings
- [ ] Individual file stats available with `--show-removed`
- [ ] Output directory mirrors input structure

---

## 2.9 Schema Learning Commands

**Goal:** LLM-assisted schema generation from example files.

**Implementation:**
- `decoct schema learn <files...>` — analyses files, identifies repeated default-like values
- `decoct schema learn --platform <name>` — uses LLM knowledge of platform defaults
- Output: draft schema YAML to stdout or `--output`

**Acceptance criteria:**
- [ ] Generates valid schema YAML from example files
- [ ] LLM mode requires `decoct[llm]` install
- [ ] Deterministic mode (frequency analysis) works without LLM
- [ ] Generated schema loads via `load_schema()`

---

## Dependencies

```
2.1 ──┐
2.2 ──┼── 2.3 (baseline measurement)
      │
2.4 ──┼── 2.6 (terraform — needs JSON input)
      │
2.5 ──┼── 2.7 (cloud-init — needs bundled schemas)
      │
2.8 (independent)
2.9 (independent, needs [llm] extra)
```

## Priority Order

1. **2.1 + 2.2** — Schema + assertions (unlock real-world validation)
2. **2.3** — Baseline measurement (quantify value)
3. **2.4** — JSON input (unblock terraform, expand input support)
4. **2.5** — Bundled schemas (improve UX)
5. **2.6** — Terraform state schema
6. **2.7** — cloud-init schema
7. **2.8** — Directory mode
8. **2.9** — Schema learning
