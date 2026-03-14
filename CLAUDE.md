# CLAUDE.md — decoct

## What This Project Is

decoct is an open source Python library and CLI that compresses fleets of infrastructure
configs (YAML, JSON, INI, XML) for LLM context windows — extracting shared classes,
computing per-host deltas, and producing a two-tier compressed representation
(tier_b.yaml for class definitions + per-host YAML for deltas).

**Repository:** `decoct-io/decoct` on GitHub
**Package:** `decoct` on PyPI (v0.1.0)
**Licence:** MIT
**Python:** 3.10+

## Pipeline

The compression pipeline runs in these phases:

1. **Parse** — `formats.load_input()` per file (YAML, JSON, INI, XML)
2. **Section** — Top-level keys = sections (XML: YANG module:tag via `xml_sections.py`)
3. **Secrets** — `secrets.document_masker.mask_document()` on parsed sections
4. **Compress** — `compress(inputs)` extracts shared classes + per-host deltas
5. **Reconstruct + Validate** — Rebuild from tier_b + tier_c, compare against originals
6. **XML Validation** — For XML inputs, reconstruct back to XML and validate
7. **Output** — Write `tier_b.yaml` + per-host `{hostname}.yaml`
8. **Stats** — Compression statistics

## Output Format

```
output_dir/
  tier_b.yaml              # {ClassName: {field: value, _identity: [...]}}
  {hostname}.yaml           # {section: {_class: Name, overrides...}}
  projections/              # Optional: per-type subject projections
```

### YAML Rendering Rules

Output YAML is rendered by `render.py` with compact, LLM-friendly formatting:

1. **Dot-notation collapse** — single-child dict chains become `a.b.c: val`
2. **Flow maps at leaf dicts** — `{k: v, k: v}` when ≤6 leaf-only keys
3. **Flow maps for list items** — items with only leaves/small dicts rendered as flow maps
4. **No subclass refs in Tier B** — class bodies must not contain `_list_class`/`_instances`/`_also`
5. **`_identity`/`_discriminators` as flow sequences** — `[a, b]` not block list

When reading collapsed output back (e.g. via the API), `reconstruct.unflatten_collapsed()`
reverses the dot-notation collapse.

## Tech Stack

- **ruamel.yaml** — round-trip YAML (CommentedMap/CommentedSeq throughout)
- **tiktoken** — token counting (cl100k_base default, o200k_base configurable)
- **click** — CLI framework
- **fastapi** — API server for compressed output
- **defusedxml** — safe XML parsing
- **hatchling** — build system
- **pytest** / **ruff** / **mypy** — testing, linting, type checking

## CLI Commands

```bash
decoct compress -i <input_dir> -o <output_dir> [--no-secrets] [--no-validate]
decoct stats -i <input_dir> -o <output_dir> [--format markdown|json]
decoct serve -o <output_dir>
decoct generate-questions -c <config_dir> -o <output.json>
decoct evaluate -c <config_dir> -o <output_dir>
decoct infer-spec -i <input_dir> [-o spec.yaml]
decoct project -o <output_dir> -s <spec_file>
decoct infer-projections -o <output_dir> --type <type_id>
```

## Development Workflow

```bash
pip install -e ".[dev]"       # Install with dev dependencies
pip install -e ".[dev,llm]"   # Also enables LLM features (learn, QA evaluation)
pytest --cov=decoct -v        # Run all tests with coverage
ruff check src/ tests/        # Lint
mypy src/                     # Type check
decoct --version              # Verify CLI entry point
```

## Module Layout

```
src/decoct/
  compress.py             Main compression engine
  render.py               YAML rendering with compact formatting rules
  reconstruct.py          Reconstruction + validation from tier_b/tier_c
  xml_sections.py         XML to sectioned dict conversion
  xml_reconstruct.py      Dict to XML reconstruction
  pipeline.py             Pipeline orchestrator (parse -> compress -> validate -> output)
  stats.py                Compression statistics
  cli.py                  Click CLI entry point
  formats.py              Input format detection + parsing
  tokens.py               Tiktoken wrapper
  id_ranges.py            ID range compression/expansion
  tier_a_models.py        TierASpec/TierATypeDescription dataclasses
  compression/            Compression package (re-exports compress)
  adapters/               BaseAdapter + ingestion spec support
  secrets/                Secret detection + document masking
  qa/                     Question generation + LLM evaluation
  projections/            Subject projections (spec, generator, models)
  api/                    FastAPI server for compressed output
  learn_ingestion.py      LLM-assisted ingestion spec inference
  learn_projections.py    LLM-assisted projection spec inference
  learn_tier_a.py         LLM-assisted Tier A spec inference
```

## Conventions

- **src layout** — all package code under `src/decoct/`
- **Dataclasses over Pydantic** — keep core dependency-light
- **Type annotations everywhere** — mypy strict mode
- **ruamel.yaml round-trip** — use CommentedMap/CommentedSeq, never plain dict for YAML processing
- **Tests per module** — every module has corresponding tests
- **LLM deps are optional** — `pip install decoct` = deterministic pipeline only; `[llm]` adds anthropic SDK
- **Line length 120** — ruff enforced

## What NOT to Do

- Never use plain `dict` where `CommentedMap` is needed — breaks round-trip YAML
- Never add required dependencies for LLM features — keep them in `[llm]` extra
- Never commit fixture files containing real secrets or credentials
