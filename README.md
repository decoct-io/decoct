# decoct

Infrastructure context compression for LLMs.

> **Status: Under active development.** API may change before 1.0.

decoct compresses fleets of infrastructure configurations (YAML, JSON, INI/config files)
into a three-tier YAML representation that separates shared structure from per-entity
differences. The compression is lossless — every entity can be reconstructed exactly from
the output. Typical savings: 70-80% on homogeneous corpora, 29-34% on heterogeneous
mixed-format corpora.

## Install

```bash
pip install decoct
```

For LLM-powered features (spec inference, QA evaluation):

```bash
pip install decoct[llm]
```

## Quick Start

decoct works on directories of configuration files. Point it at a folder and it discovers
entity types, extracts shared classes, and compresses the remainder into per-entity deltas.

```bash
# Run the pipeline on IOS-XR router configs
python scripts/run_pipeline.py

# Run on mixed-format infrastructure configs (YAML/JSON/INI)
python scripts/run_hybrid_infra.py

# Run on Entra ID / Intune policies
python scripts/run_entra_intune.py
```

### CLI Commands

```bash
# Compression statistics
decoct entity-graph stats -i <input_dir> -o <output_dir>

# Generate ground-truth Q&A pairs for evaluation
decoct entity-graph generate-questions -c <config_dir> -o questions.json

# Evaluate LLM comprehension on raw vs compressed (requires decoct[llm])
decoct entity-graph evaluate -q questions.json -c <config_dir> --output-dir <output_dir>

# Infer ingestion spec for unknown platforms (requires decoct[llm])
decoct entity-graph infer-spec -i <input_dir> [-o spec.yaml]

# Generate subject projections from compressed output
decoct entity-graph project -o <output_dir> -s <spec_file>

# Infer projection spec from Tier B (requires decoct[llm])
decoct entity-graph infer-projections -o <output_dir> --type <type_id>

# Generate enhanced Tier A with LLM-written summaries (requires decoct[llm])
decoct entity-graph review-tier-a -o <output_dir> [--output spec.yaml]
decoct entity-graph enhance-tier-a -o <output_dir> -s <tier_a_spec.yaml>
```

## What It Does

The entity-graph pipeline compresses fleets of configs through an 8-phase process:

1. **Canonicalise** — adapter parses input files into an entity graph (one file = one entity)
2. **Bootstrap Loop** — seed types via Jaccard clustering, profile, refine via anti-unification
3. **Composite Decomposition** — template extraction + per-entity deltas for high-cardinality structures
4. **Class Extraction** — greedy frequent-bundle clustering for shared attribute sets
5. **Delta Compression** — subclass promotion for residual differences (max depth 2)
6. **Normalisation** — build phone book for dense scalars, instance_attrs for sparse
7. **Reconstruction Validation** — gate test: 8 structural invariants + per-entity fidelity check
8. **Assembly** — emit Tier A (fleet overview), Tier B (class definitions), Tier C (per-entity differences)

### Three-Tier Output

| Tier | Purpose | Contents |
|------|---------|----------|
| **Tier A** | Fleet overview | Type inventory, compression stats, entity counts, assertions |
| **Tier B** | Shared structure | Class definitions with full attribute trees |
| **Tier C** | Per-entity differences | Entity-to-class assignments + delta overrides |

Input formats: YAML, JSON, and INI/config files (`.ini`, `.conf`, `.cfg`, `.cnf`, `.properties`).

### Adapters

| Adapter | Input | Example Corpus |
|---------|-------|----------------|
| IOS-XR | Cisco IOS-XR `.cfg` files | 86 router configs (tested fixture) |
| Hybrid-Infra | Mixed YAML/JSON/INI | 100 files across Docker Compose, Ansible, PostgreSQL, etc. |
| Entra-Intune | Microsoft Graph API `.json` | 88 Entra ID + Intune policy files |

New adapters can be added by extending `BaseAdapter` in `src/decoct/adapters/`.

### Example Output

Input: 86 IOS-XR router configuration files (~180K tokens raw)

Compressed output:
- **Tier A** — fleet overview with 5 entity types, compression stats
- **Tier B** — 12 shared classes capturing common BGP/OSPF/interface configurations
- **Tier C** — per-router deltas (only what differs from the class)
- **Result** — ~36K tokens (80% reduction), 100% reconstruction fidelity

## Features

- **Lossless compression** — every entity reconstructable from Tier B + C
- **Platform-agnostic** — discovers structure from data, no vendor-specific rules needed
- **Secret masking** — entropy + regex + path pattern detection, pre- and post-flatten
- **Subject projections** — slice compressed output by topic (e.g., "BGP config across all routers")
- **LLM-assisted spec inference** — infer ingestion specs, projection specs, and Tier A summaries
- **QA evaluation harness** — generate questions and measure LLM comprehension on raw vs compressed
- **Token counting** — tiktoken integration (cl100k_base default, o200k_base configurable)

## Documentation

- [Entity-Graph Architecture](docs/entity-graph-architecture.md) — authoritative design reference
- [Data Manual](docs/entity-graph-data-manual.md) — how to read and interpret the three-tier output
- [Contributing](CONTRIBUTING.md)

## Development

```bash
git clone https://github.com/decoct-io/decoct.git
cd decoct
pip install -e ".[dev]"
pytest --cov=decoct -v    # Run tests
ruff check src/ tests/    # Lint
mypy src/                 # Type check
```

## Licence

MIT -- see [LICENSE](LICENSE).
