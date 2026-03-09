# ADR-005: "Assertions" Not "Rules"

## Status
Accepted

## Context
The project needs a name for the structured design standards that the pipeline evaluates against. Common terms: rules, policies, constraints, checks, assertions.

## Decision
Call them "assertions" throughout the codebase, documentation, and CLI.

## Rationale
1. **Declarative, not imperative** — "Assertions" describe what should be true, not what to do about violations. This aligns with the design: the assertion states the standard, and the pipeline decides whether to strip conformant values or annotate deviations.
2. **Severity spectrum** — Assertions have `must`/`should`/`may` severity levels. "Rules" implies enforcement; "assertions" allows for advisory standards that inform rather than enforce.
3. **LLM context** — Assertions without `match` conditions serve as context for LLM consumers. They assert something about the intended state without being machine-evaluable. "Rules" without enforcement would be confusing.
4. **Testing analogy** — Like test assertions, these declare expected conditions and report when reality differs. The mental model is familiar to developers.

## Consequences
- The YAML key is `assert` (not `rule` or `check`).
- The Python field is `assert_` (trailing underscore to avoid the keyword).
- CLI flag is `--assertions`, not `--rules`.
- Documentation consistently uses "assertion" terminology.
