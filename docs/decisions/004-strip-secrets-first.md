# ADR-004: strip-secrets Must Always Run First

## Status
Accepted

## Context
Infrastructure data frequently contains secrets (passwords, API keys, tokens, connection strings). decoct processes this data and may output it to files, stdout, or LLM context windows. The learn commands send data to external APIs.

## Decision
The strip-secrets pass MUST be the first pass in every pipeline execution. This is enforced by:
1. `StripSecretsPass` declares an empty `run_after` list.
2. All other passes declare `run_after` including `"strip-secrets"` (directly or transitively).
3. The topological sort guarantees strip-secrets runs before any other pass.

## Rationale
1. **Security boundary** — strip-secrets is the point where secrets are removed. Everything after it operates on redacted data.
2. **No exceptions** — Even if a user constructs a custom pipeline, the ordering constraints enforce strip-secrets first. There is no `--skip-secrets` flag.
3. **Audit trail safety** — The audit trail records (path, detection_method) but never the actual secret values. This is only safe because redaction happens before any other processing that might log values.
4. **Defense in depth** — Over-redaction (false positives) is preferred over missed secrets. The entropy threshold and regex patterns are tuned for recall over precision.

## Consequences
- Users cannot skip secret redaction.
- False positives (e.g., high-entropy non-secret strings) are redacted. Users can adjust thresholds via profile configuration.
- The learn commands do NOT run strip-secrets on their input — users are responsible for not passing files with real secrets to learn commands.
