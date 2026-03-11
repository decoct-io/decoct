# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Entity-graph compression pipeline — 8-phase lossless compression for fleet-scale infrastructure configs
- Three adapters: IOS-XR (.cfg), Hybrid-Infra (YAML/JSON/INI), Entra-Intune (JSON)
- Three-tier output: Tier A (fleet overview), Tier B (shared classes), Tier C (per-entity deltas)
- Reconstruction validation gate test (100% fidelity)
- Strict bidirectional source fidelity validation (Phase 1.5) — token-sequence normalisation proves `source ≡ entity` with no heuristics; 0 mismatches on Hybrid-Infra (JSON/YAML/INI)
- Secret masking — pre-flatten + post-flatten via `src/decoct/secrets/`
- Subject projections — slice compressed output by topic
- LLM-assisted spec inference: ingestion specs, projection specs, Tier A summaries
- QA evaluation harness — generate questions and measure LLM comprehension on raw vs compressed
- CLI: `decoct entity-graph` command group with stats, generate-questions, evaluate, infer-spec, project, infer-projections, review-tier-a, enhance-tier-a subcommands

### Removed
- Legacy pass-based pipeline (`decoct compress`, schemas, assertions, profiles)

## [0.1.0] - 2026-03-09

### Added
- Initial release with pass-based compression pipeline
- Token counting with tiktoken (cl100k_base default, configurable encoding)
- Secret detection via entropy analysis, regex patterns, and path-based rules
- JSON and INI/config input format support
- GitHub Actions CI pipeline (Python 3.10-3.13, pytest, ruff, mypy)

[Unreleased]: https://github.com/decoct-io/decoct/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/decoct-io/decoct/releases/tag/v0.1.0
