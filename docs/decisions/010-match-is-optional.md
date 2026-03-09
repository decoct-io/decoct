# ADR-010: Match Conditions Are Optional on Assertions

## Status
Accepted

## Context
Design standards vary in how precisely they can be machine-evaluated. "All images must use pinned versions" can be checked with a regex. "Resource limits should be set appropriately" requires human or LLM judgment.

## Decision
The `match` field on assertions is optional. Assertions without `match` are included in the pipeline output as LLM context but are not machine-evaluated.

## Rationale
1. **Spectrum of evaluability** — Some standards are precisely checkable (value equality, regex patterns, numeric ranges). Others require judgment about appropriateness, completeness, or architectural fit.
2. **Context is valuable** — Even non-evaluable assertions provide useful context for LLMs consuming the compressed output. An LLM reading "resource limits should be set appropriately" can check the actual values and flag concerns.
3. **Incremental improvement** — Teams can start with LLM-context-only assertions and add `match` conditions over time as they formalize their standards.
4. **No false precision** — Forcing a `match` on every assertion would lead to either overly broad patterns (matching everything) or overly narrow ones (missing edge cases). It's better to be honest about what can and can't be automated.

## Pipeline Behavior
| Has `match`? | `strip-conformant` | `annotate-deviations` | `deviation-summary` |
|-------------|--------------------|-----------------------|--------------------|
| Yes | Strips conformant values (must only) | Annotates deviations | Lists in summary |
| No | Skipped | Skipped | Skipped |

## Consequences
- Assertions without `match` are invisible to the deterministic pipeline — they pass through unchanged.
- The LLM consumer sees them in the assertion file context but not as annotations in the compressed output.
- `decoct assertion learn` generates assertions with and without `match` conditions depending on the standard's evaluability.
