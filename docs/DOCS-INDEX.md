# decoct Documentation Suite — Index

This is the master index for all decoct documentation. Each entry describes a
document to write, its audience, purpose, and current status (existing/needs
update/new). Documents are grouped by audience and ordered for incremental
authoring — tackle them top-to-bottom within each group.

---

## 1. User-Facing Documentation

### 1.1 README.md
- **Status:** EXISTS — needs update
- **Location:** `/README.md`
- **Audience:** First-time visitors, GitHub browsers
- **Purpose:** Project pitch, install, 60-second quick start, link to full docs
- **Work needed:**
  - Update bundled schemas table (currently lists 6, should list all 25)
  - Add INI/config input format to "What It Does"
  - Add `assertion learn` to Quick Start examples
  - Add badges (PyPI, CI, coverage, Python versions)
  - Add "Supported Platforms" summary section
  - Mention auto-detection capability
  - Link to full documentation suite

### 1.2 Getting Started Guide
- **Status:** NEW
- **Location:** `docs/getting-started.md`
- **Audience:** New users who just installed decoct
- **Purpose:** Walk through first compression, explain what happened, build to profiles
- **Sections:**
  1. Installation (pip, pip with LLM extras, dev install)
  2. Your first compression (a Docker Compose file, basic output)
  3. Understanding the output (what was stripped, what annotations mean)
  4. Adding a schema (bundled vs custom, `--stats` to see improvement)
  5. Adding assertions (bundled vs custom, deviation annotations)
  6. Using a profile (combining schema + assertions + pass config)
  7. Processing multiple files and directories
  8. Next steps (links to CLI reference, schema authoring, assertion authoring)

### 1.3 CLI Reference
- **Status:** NEW (partial coverage in manual.md)
- **Location:** `docs/cli-reference.md`
- **Audience:** Users who know the basics, need option details
- **Purpose:** Complete reference for every command, subcommand, option, and flag
- **Sections:**
  1. `decoct` — global options (`--version`, `--help`)
  2. `decoct compress` — all options with detailed descriptions and examples
     - `FILES` argument (files, directories, stdin)
     - `--schema` (path or bundled name, auto-detection)
     - `--assertions` (path)
     - `--profile` (path or bundled name)
     - `--stats` / `--stats-only`
     - `--show-removed`
     - `-o, --output`
     - `-r, --recursive`
     - `--encoding`
  3. `decoct schema learn` — all options, examples, requirements
  4. `decoct assertion learn` — all options, modes (standards, corpus, combined), examples
  5. `decoct entity-graph stats` — compression statistics reporting
  6. `decoct entity-graph generate-questions` — QA question bank generation
  7. `decoct entity-graph evaluate` — LLM comprehension evaluation
  8. Exit codes and error messages
  9. Environment variables (ANTHROPIC_API_KEY for learn and evaluate commands)
  10. stdin/stdout/stderr behaviour

### 1.4 User Manual
- **Status:** EXISTS — needs expansion
- **Location:** `docs/manual.md`
- **Audience:** Users who want deep understanding
- **Purpose:** Comprehensive guide to all features, configuration, and workflows
- **Work needed:**
  - Add INI/config input format section
  - Add `exists` match condition to match conditions table
  - Add `assertion learn` command documentation
  - Add `emit-classes` and `prune-empty` to pipeline passes table
  - Add auto-detection section (how it works, which platforms)
  - Add bundled schema/profile resolution section
  - Add recursive/directory processing section
  - Expand library usage with more examples
  - Add troubleshooting section

### 1.5 Schema Authoring Guide
- **Status:** NEW
- **Location:** `docs/schema-authoring.md`
- **Audience:** Users creating custom schemas for their platforms
- **Purpose:** How to write, test, and iterate on schema files
- **Sections:**
  1. Schema file format (all fields, types, examples)
  2. Path pattern syntax (`*` single segment, `**` any depth)
  3. Finding defaults for your platform (vendor docs, CLI dumps, LLM-assisted)
  4. Using `decoct schema learn` to bootstrap a schema
  5. Confidence levels and their effect on stripping
  6. `drop_patterns` — when and how to use them
  7. `system_managed` — identifying system-generated fields
  8. Testing your schema (run against known input, verify with `--show-removed`)
  9. Merging additional defaults into an existing schema
  10. Contributing schemas upstream (bundled schema requirements)

### 1.6 Assertion Authoring Guide
- **Status:** NEW
- **Location:** `docs/assertion-authoring.md`
- **Audience:** Users encoding their design standards
- **Purpose:** How to write, test, and maintain assertion files
- **Sections:**
  1. Assertion file format (all fields, types, examples)
  2. Writing effective assertions (id naming, rationale, severity choice)
  3. Match conditions deep dive (value, pattern, range, contains, not_value, exists)
  4. Path patterns in assertions (same wildcards as schemas)
  5. Assertions without `match` — LLM-context-only assertions
  6. Using `decoct assertion learn` to bootstrap assertions
  7. Corpus inference mode (learning from existing configs)
  8. Severity levels: `must` vs `should` vs `may` — what each means for the pipeline
  9. Testing assertions against known inputs
  10. Merging and maintaining assertion files over time

### 1.7 Profile Authoring Guide
- **Status:** NEW
- **Location:** `docs/profile-authoring.md`
- **Audience:** Users bundling schemas + assertions + pass config
- **Purpose:** How to create and use profiles for repeatable compression
- **Sections:**
  1. Profile file format (all fields, path resolution)
  2. Bundled profiles vs custom profiles
  3. Pass configuration options (per-pass config keys)
  4. Choosing which passes to include
  5. Pass ordering (automatic topological sort, constraints)
  6. Example profiles for common platforms
  7. Sharing profiles across teams

### 1.8 Bundled Schemas Reference
- **Status:** NEW
- **Location:** `docs/bundled-schemas.md`
- **Audience:** Users wanting to know what's included out of the box
- **Purpose:** Catalogue of all 25 bundled schemas with details
- **Sections:**
  1. Overview table (platform, short name, defaults count, confidence, source)
  2. Per-schema detail pages (grouped by category):
     - **Container/Orchestration:** docker-compose, kubernetes
     - **Configuration Management:** ansible-playbook, cloud-init, sshd-config
     - **Infrastructure as Code:** terraform-state, aws-cloudformation, azure-arm, gcp-resources
     - **CI/CD:** github-actions, gitlab-ci, argocd
     - **Databases:** postgresql, mariadb-mysql, mongodb, redis, kafka
     - **Observability:** prometheus, grafana, opentelemetry-collector, fluent-bit
     - **Networking:** traefik
     - **Identity:** keycloak, entra-id, intune
  3. Each entry: platform name, source of defaults, confidence level, number of defaults, key defaults listed, drop patterns, system-managed fields
  4. Auto-detection: which platforms are auto-detected and how

### 1.9 Bundled Assertions Reference
- **Status:** NEW
- **Location:** `docs/bundled-assertions.md`
- **Audience:** Users wanting to understand the included deployment standards
- **Purpose:** Document every bundled assertion with rationale
- **Sections:**
  1. `deployment-standards.yaml` — overview and design philosophy
  2. Per-assertion detail:
     - ID, severity, human-readable assertion text
     - Rationale (why this matters)
     - Match condition (how it's evaluated)
     - Example conformant value
     - Example non-conformant value
     - Exceptions
  3. Coverage gaps (what isn't checked, known limitations)

### 1.10 Input Formats Guide
- **Status:** NEW
- **Location:** `docs/input-formats.md`
- **Audience:** Users working with non-YAML input
- **Purpose:** How decoct handles different input formats
- **Sections:**
  1. YAML input (native, round-trip, comment handling)
  2. JSON input (auto-detection, conversion to CommentedMap)
  3. INI/config file input (`.ini`, `.conf`, `.cfg`, `.cnf`, `.properties`)
  4. Auto-detection by file extension
  5. Platform auto-detection from document content
  6. Limitations and known issues per format
  7. Future formats (XML, CLI output — roadmap)

### 1.11 Output Format Guide
- **Status:** NEW
- **Location:** `docs/output-format.md`
- **Audience:** Users and LLM pipeline builders consuming decoct output
- **Purpose:** Explain the compressed YAML output format in detail
- **Sections:**
  1. Output structure overview
  2. Class definitions (`@class` header comments, what they mean)
  3. Deviation annotations (`# [!]` inline comments)
  4. Deviation summary block (preamble format)
  5. `[REDACTED]` sentinel values
  6. Token statistics output format
  7. `--show-removed` output format
  8. Feeding decoct output to LLMs (best practices, prompting tips)
  9. Reconstituting full documents from compressed output

### 1.12 Entity-Graph Evaluation Guide
- **Status:** EXISTS
- **Location:** `docs/entity-graph-evaluation.md`
- **Audience:** Users running entity-graph compression who want to measure effectiveness
- **Purpose:** Complete guide to compression statistics, QA question generation, and LLM comprehension evaluation
- **Sections:**
  1. Entity-graph stats — CLI usage, options, output format, key metrics
  2. QA question generation — categories, deterministic generation, question bank format
  3. QA evaluation — LLM-based comprehension testing, answer matching, report format
  4. Python API — programmatic access to all features
  5. Interpreting results — what good/concerning results look like
  6. End-to-end example — complete workflow from configs to evaluation report

### 1.13 Cookbook / Recipes
- **Status:** NEW
- **Location:** `docs/cookbook.md`
- **Audience:** Users looking for copy-paste solutions
- **Purpose:** Task-oriented recipes for common use cases
- **Recipes:**
  1. Compress Docker Compose for ChatGPT/Claude
  2. Compress Kubernetes manifests for code review
  3. Compress Terraform state for troubleshooting
  4. Compress Ansible playbooks for architecture review
  5. Build a custom schema from scratch
  6. Learn a schema from production configs using Claude
  7. Encode team deployment standards as assertions
  8. Learn assertions from a corpus of existing configs
  9. Set up a profile for CI pipeline integration
  10. Batch-process a config directory
  11. Pipe kubectl output through decoct
  12. Compare compressed vs uncompressed token counts
  13. Integrate decoct into an MCP tool server
  14. Use decoct as a Python library in a script

---

## 2. Developer Documentation

### 2.1 Architecture Guide
- **Status:** NEW (partial coverage in CLAUDE.md)
- **Location:** `docs/dev/architecture.md`
- **Audience:** Contributors, maintainers
- **Purpose:** Technical architecture of the codebase
- **Sections:**
  1. High-level architecture diagram (three-phase pipeline)
  2. Module dependency graph
  3. Data flow: input → normalize → passes → output
  4. Pass system design (base class, registry, topological sort)
  5. Schema system (models, loader, resolver, bundled)
  6. Assertion system (models, loader, matcher, bundled)
  7. Profile system (models, loader, resolver, bundled)
  8. Format handling (detection, conversion, round-trip preservation)
  9. Token counting integration
  10. LLM integration (optional dependency, learn module)
  11. CLI layer (click commands, option resolution, pipeline construction)
  12. Key design decisions and trade-offs

### 2.2 Contributing Guide
- **Status:** NEW
- **Location:** `CONTRIBUTING.md`
- **Audience:** External contributors
- **Purpose:** How to set up, develop, test, and submit changes
- **Sections:**
  1. Development setup (clone, venv, install, verify)
  2. Project structure overview
  3. Running tests (`pytest --cov=decoct -v`)
  4. Running linters (`ruff check src/ tests/`)
  5. Running type checks (`mypy src/`)
  6. Writing tests (conventions, fixtures, naming)
  7. Adding a new pass (base class, registry, ordering, tests)
  8. Adding a bundled schema (format, validation, resolver registration)
  9. Adding a bundled assertion set
  10. Adding a bundled profile
  11. Adding input format support
  12. Code style (line length 120, type annotations, dataclasses over Pydantic)
  13. Commit message conventions
  14. Pull request process

### 2.3 Pass Development Guide
- **Status:** NEW
- **Location:** `docs/dev/writing-passes.md`
- **Audience:** Developers adding new compression passes
- **Purpose:** Step-by-step guide to implementing a new pass
- **Sections:**
  1. Pass base class API (`BasePass`, `PassResult`)
  2. Pass registration (`register_pass`, `get_pass`)
  3. Ordering constraints (`run_after`, `run_before`)
  4. Working with `CommentedMap` / `CommentedSeq`
  5. Path matching utilities (wildcards, globbing)
  6. Adding comments (ruamel.yaml comment API)
  7. Removing nodes safely (preserving structure)
  8. Pass configuration (accepting options from profiles)
  9. Testing a pass (fixture-based testing pattern)
  10. Example: building a pass from scratch

### 2.4 Testing Guide
- **Status:** NEW (conventions in `.claude/rules/testing.md`)
- **Location:** `docs/dev/testing.md`
- **Audience:** Developers writing or running tests
- **Purpose:** Testing conventions, fixture patterns, coverage expectations
- **Sections:**
  1. Test organisation (one test file per module, test_passes/ subdirectory)
  2. Fixture system (YAML fixtures in tests/fixtures/, organised by type)
  3. Writing fixture-based pass tests (input YAML → expected output YAML)
  4. CLI testing with `CliRunner`
  5. Integration tests (full pipeline, realistic data)
  6. End-to-end tests (all bundled schemas/assertions)
  7. Mocking LLM calls (for learn module tests)
  8. Test naming conventions (describe behaviour, not method)
  9. Running tests (basic, with coverage, filtered)
  10. Coverage expectations and gaps

### 2.5 API Reference
- **Status:** NEW
- **Location:** `docs/dev/api-reference.md`
- **Audience:** Developers using decoct as a library
- **Purpose:** Complete Python API documentation
- **Sections:**
  1. `decoct.pipeline` — `Pipeline`, `PipelineStats`
  2. `decoct.tokens` — `count_tokens`, `create_report`, `format_report`, `TokenReport`
  3. `decoct.formats` — `detect_format`, `detect_platform`, `load_input`, `json_to_commented_map`, `ini_to_commented_map`
  4. `decoct.schemas.models` — `Schema`
  5. `decoct.schemas.loader` — `load_schema`
  6. `decoct.schemas.resolver` — `resolve_schema`, `BUNDLED_SCHEMAS`
  7. `decoct.assertions.models` — `Assertion`, `Match`
  8. `decoct.assertions.loader` — `load_assertions`
  9. `decoct.assertions.matcher` — `evaluate_match`, `find_matches`
  10. `decoct.profiles.loader` — `load_profile`
  11. `decoct.profiles.resolver` — `resolve_profile`, `BUNDLED_PROFILES`
  12. `decoct.passes.base` — `BasePass`, `PassResult`, registry functions
  13. `decoct.passes.strip_secrets` — `StripSecretsPass`, `strip_secrets`, `shannon_entropy`
  14. `decoct.passes.strip_comments` — `StripCommentsPass`
  15. `decoct.passes.strip_defaults` — `StripDefaultsPass`, `strip_defaults`
  16. `decoct.passes.drop_fields` — `DropFieldsPass`, `drop_fields`
  17. `decoct.passes.keep_fields` — `KeepFieldsPass`, `keep_fields`
  18. `decoct.passes.prune_empty` — `PruneEmptyPass`, `prune_empty`
  19. `decoct.passes.strip_conformant` — `StripConformantPass`, `strip_conformant`
  20. `decoct.passes.annotate_deviations` — `AnnotateDeviationsPass`, `annotate_deviations`, `Deviation`
  21. `decoct.passes.deviation_summary` — `DeviationSummaryPass`, `deviation_summary`
  22. `decoct.passes.emit_classes` — `EmitClassesPass`, `emit_classes`
  23. `decoct.learn` — `learn_schema`, `learn_assertions`, `merge_schemas`, `merge_assertions`

### 2.6 Security Model
- **Status:** NEW (partial in `.claude/rules/strip-secrets.md`)
- **Location:** `docs/dev/security.md`
- **Audience:** Security reviewers, contributors touching strip-secrets
- **Purpose:** Document the security boundary and threat model
- **Sections:**
  1. Threat model (secrets in infrastructure data, LLM exposure)
  2. strip-secrets as the security boundary
  3. Detection methods (entropy, regex, path-based)
  4. Ordering guarantee (always first, enforcement mechanism)
  5. What is NOT detected (structural secrets, encoded data)
  6. Audit trail (what's logged, what's never logged)
  7. False positives (healthcheck commands, high-entropy non-secrets)
  8. LLM data flow (learn commands send data to API — what, when, safeguards)
  9. Recommendations for sensitive environments

---

## 3. Project Documentation

### 3.1 CHANGELOG.md
- **Status:** EXISTS — needs restructuring
- **Location:** `/CHANGELOG.md`
- **Work needed:**
  - Move from single [Unreleased] block to versioned entries
  - Add [0.1.0] entry with date
  - Group by Added/Changed/Fixed/Removed per Keep a Changelog
  - Include Phase 2 features (JSON input, INI input, bundled schemas, learn commands, etc.)

### 3.2 Roadmap
- **Status:** NEW
- **Location:** `docs/roadmap.md`
- **Audience:** Users and potential contributors
- **Purpose:** Public-facing roadmap of planned features
- **Sections:**
  1. Phase 1 — Foundation + Core Pipeline (COMPLETE)
  2. Phase 2 — Real-World Validation (CURRENT — what's done, what remains)
  3. Phase 3 — planned features:
     - XML input normalisation
     - CLI output normalisation
     - Absent-field detection (`exists` match improvements)
     - Scaffolding packs
     - Class resolver / inheritance
     - LLM-direct compression mode
     - LLM fallback for ambiguity resolution
  4. Phase 4-7 — high-level roadmap items
  5. How to influence the roadmap (issues, discussions)

### 3.3 Design Decisions (ADRs)
- **Status:** NEW
- **Location:** `docs/decisions/` (one file per decision)
- **Audience:** Contributors, future maintainers
- **Purpose:** Record why key decisions were made
- **Decisions to document:**
  1. `001-yaml-output-only.md` — Why YAML is the only output format
  2. `002-dataclasses-over-pydantic.md` — Why we use stdlib dataclasses
  3. `003-ruamel-yaml-roundtrip.md` — Why ruamel.yaml in round-trip mode
  4. `004-strip-secrets-first.md` — Why strip-secrets must always run first
  5. `005-assertions-not-rules.md` — Why we call them "assertions" not "rules"
  6. `006-optional-llm-dependency.md` — Why LLM features are an optional extra
  7. `007-class-reconstitution.md` — Why stripped values are recorded as classes
  8. `008-confidence-levels.md` — Why schemas have confidence and how it affects stripping
  9. `009-topological-pass-ordering.md` — Why passes declare ordering constraints
  10. `010-match-is-optional.md` — Why assertions can exist without match conditions

### 3.4 Baseline Measurements
- **Status:** EXISTS
- **Location:** `docs/baseline-measurement.md`
- **Work needed:** No changes — keep as historical reference

### 3.5 Steering Document
- **Status:** EXISTS
- **Location:** `docs/steering.md`
- **Work needed:** No changes — internal planning reference

---

## 4. Operational Documentation

### 4.1 Integration Guide
- **Status:** NEW
- **Location:** `docs/integration.md`
- **Audience:** DevOps/platform engineers integrating decoct into workflows
- **Purpose:** How to use decoct in CI/CD, MCP servers, and automation
- **Sections:**
  1. CI/CD integration (GitHub Actions, GitLab CI examples)
  2. Pre-commit hook for config validation
  3. MCP tool server integration (expose decoct as an MCP tool)
  4. Shell pipeline integration (piping kubectl, terraform, ansible output)
  5. Python scripting integration (library usage patterns)
  6. Docker image usage (if/when published)
  7. Caching and performance considerations

### 4.2 Troubleshooting Guide
- **Status:** NEW
- **Location:** `docs/troubleshooting.md`
- **Audience:** Users encountering problems
- **Purpose:** Common issues and solutions
- **Sections:**
  1. "No schema found" — auto-detection didn't work
  2. False positive secret detection
  3. Values not being stripped (confidence, match conditions)
  4. Assertions not matching (path syntax, wildcards)
  5. Empty output (everything stripped)
  6. JSON/INI parsing failures
  7. LLM learn commands failing (API key, model, rate limits)
  8. Token count discrepancies
  9. Performance on large files
  10. Getting help (issue tracker, discussions)

---

## Document Dependency Order

For incremental authoring, this is the recommended order:

```
Phase A — Core user docs (can be done in parallel):
  1.1  README.md update
  1.3  CLI Reference
  1.10 Input Formats Guide
  1.11 Output Format Guide

Phase B — Guides (depend on Phase A for linking):
  1.2  Getting Started Guide
  1.5  Schema Authoring Guide
  1.6  Assertion Authoring Guide
  1.7  Profile Authoring Guide

Phase C — Reference material:
  1.8  Bundled Schemas Reference
  1.9  Bundled Assertions Reference
  1.12 Cookbook / Recipes

Phase D — Developer docs:
  2.1  Architecture Guide
  2.5  API Reference
  2.3  Pass Development Guide
  2.4  Testing Guide
  2.6  Security Model
  2.2  Contributing Guide

Phase E — Project docs:
  3.1  CHANGELOG restructure
  3.2  Roadmap
  3.3  Design Decisions (ADRs)

Phase F — Operational:
  4.1  Integration Guide
  4.2  Troubleshooting Guide
```

## Summary

| Category | Count | Existing | Needs Update | New |
|----------|-------|----------|--------------|-----|
| User-facing | 13 | 3 | 2 | 10 |
| Developer | 6 | 0 | 0 | 6 |
| Project | 5 | 3 | 2 | 2 (+10 ADRs) |
| Operational | 2 | 0 | 0 | 2 |
| **Total** | **26** | **6** | **4** | **20** |
