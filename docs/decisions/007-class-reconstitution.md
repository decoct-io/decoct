# ADR-007: Class-Based Reconstitution

## Status
Accepted

## Context
When strip-defaults removes values, the compressed output loses information. An LLM reading the compressed output doesn't know what defaults were stripped or what the full document looked like.

## Decision
The emit-classes pass adds `@class` header comments that list stripped defaults grouped by path prefix. This enables LLMs to reconstruct the full document.

## Rationale
1. **Information preservation** — The compressed output is smaller but not lossy. The `@class` definitions record exactly what was stripped.
2. **LLM-friendly** — Header comments are visible to LLMs consuming the YAML. A simple prompt like "expand using @class definitions" lets the LLM reconstruct defaults.
3. **Compact representation** — Grouping defaults by class (e.g., `service-defaults`, `service-healthcheck-defaults`) is more token-efficient than listing each stripped field individually.
4. **No schema needed for reconstruction** — The class definitions carry the default values inline, so the consumer doesn't need access to the original schema file.

## Format
```yaml
# decoct: defaults stripped using docker-compose schema
# @class service-defaults: privileged=false, read_only=false, restart=no, ...
# @class service-healthcheck-defaults: interval=30s, retries=3, timeout=30s, ...
```

## Consequences
- The emit-classes pass depends on having a schema (it groups defaults from the schema's `defaults` dict).
- Class names are derived from path prefixes, not user-defined.
- Long class definitions are truncated to maintain readability.
- Stripped conformant assertion values are NOT included in class definitions (only schema defaults).
