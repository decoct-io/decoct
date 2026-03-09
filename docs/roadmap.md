# Roadmap

## Phase 1: Foundation + Core Pipeline — COMPLETE
- Project skeleton, packaging, CI
- Internal data formats (schemas, assertions, profiles)
- Token counting with tiktoken
- strip-secrets pass (entropy + regex + path patterns)
- Pipeline framework with topological sort
- Generic passes (strip-comments, drop-fields, keep-fields)
- Schema-aware pass (strip-defaults)
- Assertion-aware passes (strip-conformant, annotate-deviations, deviation-summary)
- CLI integration (decoct compress)

## Phase 2: Real-World Validation — MOSTLY COMPLETE
Completed:
- Comprehensive Docker Compose schema (~35 defaults)
- Deployment standards assertions (12 assertions)
- Baseline measurements (25-35% savings on production configs)
- JSON input support
- INI/config file input support
- Bundled schema support (30 schemas across 9 categories)
- Platform auto-detection (8 platforms)
- Directory/recursive processing
- LLM-assisted schema learning (decoct schema learn)
- LLM-assisted assertion learning (decoct assertion learn)
- Corpus inference mode for assertions
- emit-classes pass for class-based reconstitution
- 21 additional platform schemas (databases, observability, cloud, identity, CI/CD, network OS)

Remaining:
- Additional platform schemas (systemd, Nginx, HAProxy)
- Bundled assertion sets for more platforms

## Phase 3: Input Expansion + LLM Modes
- XML input normalisation
- CLI output normalisation (structured text → YAML)
- Absent-field detection improvements
- LLM-direct compression mode (zero-setup, LLM does everything)
- LLM fallback for ambiguity resolution
- Schema adapter framework (YANG, OpenAPI, JSON Schema, ADMX)

## Phase 4: Scaffolding + Assertions
- Scaffolding pack format (reusable expert knowledge)
- Interview mechanism for assertion authoring
- Assertion validation against fixtures

## Phase 5: Classes + Reconstitution
- Class resolver and inheritance
- Class-based document expansion
- Round-trip compression/expansion verification

## Phase 6: Benchmarks + Evaluation
- Corpus collection across platforms
- Token savings benchmarks
- LLM comprehension harness (does the LLM understand compressed output?)
- Published benchmark results

## Phase 7: Polish + Release
- Documentation site at decoct.io
- PyPI stable release
- Example schemas, assertions, and profiles
- Community contribution guidelines

## Influencing the Roadmap
- Open an issue: https://github.com/decoct-io/decoct/issues
- Contribute a schema, assertion set, or profile
- Join the discussion on GitHub
