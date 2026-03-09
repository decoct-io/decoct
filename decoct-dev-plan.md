# decoct — Development Plan

---

## Phases

1. **Foundation + Core Pipeline** — COMPLETE — repo, packaging, data formats, deterministic passes, strip-secrets, token counting, CLI
2. **Real-World Validation** — MOSTLY COMPLETE — bundled schemas, JSON/INI input, learning commands, platform auto-detection, documentation
3. **Input Expansion + LLM Modes** — XML/CLI normalisation, LLM-direct compression, schema adapter framework
4. **Scaffolding + Assertions** — scaffolding pack format, interview mechanism, assertion validation
5. **Classes + Reconstitution** — class resolver, inheritance, round-trip compression/expansion
6. **Benchmarks + Evaluation** — corpus collection, token benchmarks, LLM comprehension harness
7. **Polish + Release** — docs site, PyPI stable release, community contribution guidelines

---

## Phase 1: Foundation + Core Pipeline — COMPLETE

- [x] 1.1 Project Skeleton
- [x] 1.2 Internal Data Formats (schemas, assertions, profiles)
- [x] 1.3 Token Counting
- [x] 1.4 Strip-Secrets Pass
- [x] 1.5 Pipeline Framework
- [x] 1.6 Generic Passes (strip-comments, drop-fields, keep-fields)
- [x] 1.7 Schema-Aware Pass (strip-defaults)
- [x] 1.8 Assertion-Aware Passes (strip-conformant, annotate-deviations, deviation-summary)
- [x] 1.9 CLI Integration

---

## Phase 2: Real-World Validation — MOSTLY COMPLETE

- [x] 2.1 Docker Compose schema (~35 defaults)
- [x] 2.2 Deployment standards assertions (12 assertions)
- [x] 2.3 Baseline measurement (25-35% savings on production configs)
- [x] 2.4 JSON input support
- [x] 2.5 Bundled schema support (30 schemas across 9 categories)
- [x] 2.6 Terraform state schema
- [x] 2.7 cloud-init schema
- [x] 2.8 Directory/recursive mode
- [x] 2.9 Schema learning commands (`decoct schema learn`)
- [x] 2.10 INI/config file input support
- [x] 2.11 Assertion learning with corpus inference (`decoct assertion learn`)
- [x] 2.12 emit-classes pass
- [x] 2.13 Platform auto-detection (8 platforms)
- [x] 2.14 Additional schemas (databases, observability, cloud, identity, CI/CD, network OS)
- [x] 2.15 Comprehensive documentation (40+ docs)

Remaining:
- [ ] Additional platform schemas (systemd, Nginx, HAProxy)
- [ ] Bundled assertion sets for more platforms

---

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

---

See `docs/roadmap.md` for the public-facing roadmap and `docs/steering.md` for detailed research and the tiered context model.
