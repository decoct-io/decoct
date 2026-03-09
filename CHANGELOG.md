# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Core compression pipeline with topological pass ordering
- 10 pipeline passes: strip-secrets, strip-comments, strip-defaults, strip-conformant, annotate-deviations, deviation-summary, emit-classes, drop-fields, keep-fields, prune-empty
- Schema system with defaults, drop patterns, and system-managed fields
- Assertion system with value, pattern, range, contains, not_value, and exists match types
- Profile system combining schemas, assertions, and pass configuration
- Bundled schemas: docker-compose (~35 defaults), cloud-init (~55 defaults), ansible-playbook (~120 defaults), kubernetes (~55 defaults + 6 system-managed), sshd-config (~35 defaults), terraform-state
- Bundled profiles: docker-compose (schema + deployment standards assertions)
- Auto-detection of platform from document content (Docker Compose, Terraform state, cloud-init, Kubernetes, Ansible)
- JSON input support with automatic conversion to round-trip YAML types
- Directory and recursive mode for batch processing
- Token counting with tiktoken (cl100k_base default, configurable encoding)
- CLI: `decoct compress` with `--schema`, `--assertions`, `--profile`, `--stats`, `--stats-only`, `--show-removed`, `-o`, `--recursive`, `--encoding` options
- CLI: `decoct schema learn` for LLM-assisted schema derivation from examples and docs (requires `decoct[llm]`)
- Class-based reconstitution: emit-classes pass adds header comments listing stripped default classes for LLM reconstruction
- Wildcard path matching for both dict keys and list items in schemas and assertions
- `**` glob pattern for matching across any depth of nesting
- Secret detection via entropy analysis, regex patterns, and path-based rules
- Healthcheck command exemption from entropy-based secret detection
- GitHub Actions CI pipeline (Python 3.10-3.13, pytest, ruff, mypy)
