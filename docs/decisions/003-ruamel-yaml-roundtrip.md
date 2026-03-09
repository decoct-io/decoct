# ADR-003: ruamel.yaml Round-Trip Mode

## Status
Accepted

## Context
decoct needs to parse, transform, and re-serialize YAML documents. The annotation passes insert comments into the document. PyYAML and ruamel.yaml are the main Python YAML libraries.

## Decision
Use `ruamel.yaml` with `typ='rt'` (round-trip mode) exclusively. All internal data structures use `CommentedMap` and `CommentedSeq`, never plain `dict` or `list`.

## Rationale
1. **Comment preservation** — Round-trip mode preserves existing comments, which matters for understanding the original document structure.
2. **Comment insertion** — The annotation passes (annotate-deviations, deviation-summary, emit-classes) add inline and header comments. This requires ruamel.yaml's comment API (`yaml_add_eol_comment`, `CommentToken` manipulation).
3. **Key ordering** — `CommentedMap` preserves insertion order, which ensures deterministic output and meaningful diffs.
4. **Type consistency** — Using `CommentedMap`/`CommentedSeq` everywhere avoids subtle bugs from mixing plain dicts with YAML-aware types.

## Consequences
- All code that processes documents must use `CommentedMap`/`CommentedSeq` types.
- JSON and INI inputs must be converted to these types (via `json_to_commented_map`, `ini_to_commented_map`).
- Plain `dict` construction is a bug — enforced by code review and convention.
- PyYAML cannot be used as a drop-in replacement.
