# Compression Pipeline

The compression pipeline compresses fleets of infrastructure configs into shared classes + per-host deltas (tier_b + tier_c).

## Quick Reference

```bash
# Install
pip install -e ".[dev]"          # Pipeline + tests
pip install -e ".[dev,llm]"      # Also enables QA evaluation

# Tests
pytest --cov=decoct -v           # All tests

# CLI
decoct compress -i <input_dir> -o <output_dir>
decoct stats -i <input_dir> -o <output_dir>
decoct serve -o <output_dir>

# Subject projections
decoct project -o <output_dir> -s <spec_file> [--type TYPE]
decoct infer-projections -o <output_dir> --type <type_id> [--model ...]
```

## Pipeline Phases

1. **Parse** — `formats.load_input()` per file (YAML, JSON, INI, XML)
2. **Section** — Top-level keys = sections (XML: YANG module:tag via `xml_sections.py`)
3. **Secrets** — `secrets.document_masker.mask_document()` on parsed sections
4. **Compress** — `compress(inputs)` from `compress.py`
5. **Reconstruct + Validate** — `validate_reconstruction()` from `reconstruct.py`
6. **XML Validation** — `validate_xml_roundtrip()` from `xml_reconstruct.py`
7. **Output** — Write `tier_b.yaml` + per-host `{hostname}.yaml`
8. **Stats** — Compression statistics via `stats.py`

## Output Format

```
output_dir/
  tier_b.yaml              # {ClassName: {field: value, _identity: [...]}}
  {hostname}.yaml           # {section: {_class: Name, overrides...}}
```

### YAML Rendering Rules (render.py)

1. **Dot-notation collapse** — single-child dict chains become `a.b.c: val`
2. **Flow maps at leaf dicts** — `{k: v}` when ≤6 leaf-only keys
3. **Flow maps for list items** — items with only leaves/small dicts as flow maps
4. **No subclass refs in Tier B** — class bodies must not contain `_list_class`/`_instances`/`_also`
5. **`_identity`/`_discriminators` as flow sequences** — `[a, b]` not block list

`reconstruct.unflatten_collapsed()` reverses dot-notation collapse when loading output back.

## Test Fixtures and Output

- `tests/fixtures/archetypal/` — Compression test fixture sets
- `tests/fixtures/ios-xr-program/` — XML + JSON fixture files
- `output/ios-xr-xml-archetypal/` — Sample compressed output

## Key Rules

- Secrets masking runs before compression via `src/decoct/secrets/`
- Reconstruction validation runs after compression to ensure fidelity
- The test suite must pass with 0 reconstruction mismatches before any PR
- LLM dependencies stay in `[llm]` extra — the deterministic pipeline works without them
