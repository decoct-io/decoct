---
globs: src/decoct/passes/**, src/decoct/schemas/**, src/decoct/assertions/**
---
# YAML Processing Rules

When writing code that processes YAML data:

- ALWAYS use `ruamel.yaml` with round-trip mode (`YAML(typ='rt')`)
- ALWAYS operate on `CommentedMap` and `CommentedSeq` types, never plain `dict`/`list`
- Preserve document structure — comments and ordering matter for annotation passes
- When removing nodes, use `del` on the CommentedMap key — do not reconstruct dicts
- When inserting comments (annotations), use ruamel.yaml's comment API
- Path matching must support `*` (single segment) and `**` (any depth) wildcards
