# ADR-008: Schema Confidence Levels

## Status
Accepted

## Context
Schema defaults come from different sources with varying reliability. Defaults from an official specification are trustworthy; defaults inferred from examples may be wrong.

## Decision
Schemas include a `confidence` field with four levels: `authoritative`, `high`, `medium`, `low`. The strip-defaults pass can optionally skip lower-confidence schemas.

## Rationale
1. **Source diversity** — Bundled schemas come from official specs (authoritative), vendor docs (high), example analysis (medium), or LLM inference (low). The confidence level communicates this provenance.
2. **User control** — The `skip_low_confidence` flag in strip-defaults configuration lets users be conservative with uncertain schemas. When enabled, both `low` and `medium` confidence schemas are skipped entirely.
3. **Progressive trust** — Users can start with a low-confidence LLM-learned schema, verify it against their configs, and upgrade the confidence level as they validate defaults.
4. **Transparency** — The confidence level appears in `--show-removed` output and class definitions, so users always know the basis for stripping.

## Levels
| Level | Source | Stripped by default | Skipped when `skip_low_confidence: true` |
|-------|--------|--------------------|-----------------------------------------|
| `authoritative` | Official spec/schema | Yes | No |
| `high` | Verified vendor docs | Yes | No |
| `medium` | Example analysis | Yes | Yes |
| `low` | Inferred/uncertain | Yes | Yes |

## Consequences
- All bundled schemas must declare their confidence level.
- The `decoct schema learn` command generates schemas with `medium` or `low` confidence.
- Users who want maximum safety can set `skip_low_confidence: true` in their profile.
