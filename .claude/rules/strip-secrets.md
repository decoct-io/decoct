---
globs: src/decoct/passes/strip_secrets.py, tests/**/test_strip_secrets*
---
# Strip-Secrets Safety Rules

The strip-secrets pass is the security boundary of the pipeline.

- strip-secrets MUST be the first pass after normalisation — `run_after` must be empty
  or only contain normalisation passes
- NEVER log, print, or store the actual secret values — audit trail records
  (path, detection_method) only
- Test fixtures MUST use synthetic secrets, never real credentials
- Replacement value is always `[REDACTED]` — no other sentinel
- The pass must handle: entropy detection, regex patterns, and path-based rules
- False-positive tolerance: prefer redacting too much over missing a secret
