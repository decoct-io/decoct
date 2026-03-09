# ADR-002: Dataclasses Over Pydantic

## Status
Accepted

## Context
The project needs structured types for schemas, assertions, profiles, pass results, and token reports. Pydantic and stdlib dataclasses are both viable options.

## Decision
Use stdlib `dataclasses` for all internal data models. Pydantic is not a dependency.

## Rationale
1. **Minimal dependencies** — decoct's core dependencies are ruamel.yaml, tiktoken, and click. Adding Pydantic would increase the dependency tree significantly.
2. **Simplicity** — The data models are straightforward containers. They don't need Pydantic's validation, serialization, or schema generation features.
3. **Manual validation** — Loaders (schema, assertion, profile) perform explicit validation with clear error messages. This is more predictable than Pydantic's validation errors for infrastructure tooling.
4. **Performance** — Dataclasses have zero overhead. The models are created once and read many times.

## Consequences
- Validation logic lives in loader modules, not in the models themselves.
- No automatic JSON Schema generation from models.
- If validation needs grow complex, this decision may be revisited.
