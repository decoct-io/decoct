# ADR-001: YAML as the Only Output Format

## Status
Accepted

## Context
decoct accepts multiple input formats (YAML, JSON, INI) but needs to choose an output format. Options considered: preserve original format, support multiple outputs, or standardize on one.

## Decision
All output is YAML, regardless of input format. JSON and INI inputs are converted to YAML during processing and output as YAML.

## Rationale
1. **Token efficiency** — YAML is more token-efficient than JSON for hierarchical data (no braces, quotes, or commas on every line).
2. **Comment support** — YAML supports inline comments, which the annotation passes require for deviation markers and class definitions. JSON and INI cannot carry these annotations.
3. **Round-trip fidelity** — ruamel.yaml preserves structure, ordering, and comments. This is essential for the annotation pipeline.
4. **LLM readability** — YAML is widely understood by LLMs and humans alike. Infrastructure tooling (Kubernetes, Docker Compose, Ansible) already uses YAML as the lingua franca.
5. **Simplicity** — One output format means one serialization path, one set of tests, and no format negotiation.

## Consequences
- Users working with JSON-native tools (Terraform state) get YAML output, which may require format conversion downstream.
- INI-format configs lose their original structure (sections become nested YAML maps).
- No `--output-format` flag is needed.
