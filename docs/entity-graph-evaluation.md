# Entity-Graph Statistics and QA Evaluation

This guide covers two features for measuring the effectiveness of the entity-graph compression pipeline:

1. **`decoct entity-graph stats`** — compression statistics comparing raw input to compressed output
2. **`decoct entity-graph generate-questions` / `evaluate`** — a QA comprehension harness that tests whether an LLM can answer factual questions about the compressed data as accurately as it can about the raw data

Both features support the Phase 6 goal of benchmarks and evaluation for the entity-graph pipeline.

---

## Entity-Graph Stats

### What It Does

The `stats` command reads a directory of raw input configs and a directory of entity-graph output files, then reports compression statistics: file counts, byte counts, token counts, compression ratios, and per-type structural metrics.

This lets you answer questions like:
- How many tokens did compression save?
- Which entity types contribute the most to output size?
- How wide is the phone book for each type?
- What is the class hierarchy depth?

### Usage

```bash
decoct entity-graph stats \
  --input-dir tests/fixtures/iosxr/configs \
  --output-dir output/iosxr
```

### Options

#### `-i, --input-dir <PATH>` (required)

- **Type:** Directory path (must exist)
- **Description:** Directory containing raw input config files. All files with recognised extensions (`.cfg`, `.yaml`, `.yml`, `.json`, `.ini`, `.conf`, `.cnf`, `.properties`) are counted.

#### `-o, --output-dir <PATH>` (required)

- **Type:** Directory path (must exist)
- **Description:** Directory containing entity-graph output files (`tier_a.yaml`, `*_classes.yaml`, `*_instances.yaml`).

#### `--format <markdown|json>`

- **Type:** Choice
- **Default:** `markdown`
- **Description:** Output format. Markdown produces human-readable tables. JSON produces a structured object suitable for further processing.

#### `--output <PATH>`

- **Type:** File path
- **Default:** None (stdout)
- **Description:** Write the report to a file instead of stdout.

#### `--encoding <NAME>`

- **Type:** String
- **Default:** `cl100k_base`
- **Description:** Tiktoken encoding name for token counting. Use `o200k_base` for newer OpenAI models.

### Markdown Output

The markdown report contains five sections:

**Input Corpus** — file count, total bytes, lines, and tokens for the raw input directory.

**Output Summary** — file count, bytes, and tokens broken down by tier (A, B, C) with totals.

**Compression Ratios** — side-by-side input vs output comparison with savings percentages for both bytes and tokens.

**Per-Type Breakdown** — one row per entity type showing entity count, class count, subclass count, base attribute count, phone book width, and per-tier token counts.

**Entity-Graph Structure** — aggregate counts: total types, entities, classes, subclasses, overrides, and relationships.

### JSON Output

The JSON report mirrors the markdown sections as a structured object:

```json
{
  "timestamp": "2026-03-10T12:00:00+00:00",
  "encoding": "cl100k_base",
  "input_stats": {
    "file_count": 86,
    "total_bytes": 643210,
    "total_lines": 15432,
    "total_tokens": 98765
  },
  "output": {
    "tier_a": { "file_count": 1, "total_bytes": 1286, ... },
    "tier_b": { "file_count": 5, "total_bytes": 30698, ... },
    "tier_c": { "file_count": 5, "total_bytes": 120805, ... },
    "total_bytes": 152789,
    "total_tokens": 24567,
    "total_files": 11
  },
  "compression": {
    "ratio_bytes": 0.2375,
    "ratio_tokens": 0.2488,
    "savings_pct_bytes": 76.3,
    "savings_pct_tokens": 75.1
  },
  "type_stats": [
    {
      "type_id": "iosxr-access-pe",
      "entity_count": 60,
      "class_count": 3,
      "subclass_count": 3,
      "base_attr_count": 120,
      "base_only_ratio": 0.0,
      "phone_book_width": 18,
      "override_count": 0,
      "relationship_count": 120,
      "max_inheritance_depth": 2,
      "tier_b_bytes": 6488,
      "tier_b_tokens": 1234,
      "tier_c_bytes": 90069,
      "tier_c_tokens": 15678
    }
  ]
}
```

### Examples

Generate a markdown report:

```bash
decoct entity-graph stats -i configs/ -o output/iosxr/
```

Generate a JSON report and save to file:

```bash
decoct entity-graph stats -i configs/ -o output/iosxr/ --format json --output report.json
```

Use a different token encoding:

```bash
decoct entity-graph stats -i configs/ -o output/iosxr/ --encoding o200k_base
```

### Key Metrics Explained

| Metric | Meaning |
|---|---|
| `base_attr_count` | Number of attributes in the base class (shared by all entities of this type). Higher = more homogeneous. |
| `base_only_ratio` | Fraction of entities assigned to `_base_only` (no real classes). 1.0 = completely homogeneous. 0.0 = all entities have meaningful class assignments. |
| `phone_book_width` | Number of columns in the Tier C phone book (dense per-entity table). Wider = more per-entity variation. |
| `override_count` | Total per-entity attribute overrides across all entities of this type. Lower = better class coverage. |
| `relationship_count` | Total inter-entity relationships stored for this type. |
| `max_inheritance_depth` | Depth of the class hierarchy (base → class → subclass = depth 2). |

---

## QA Comprehension Harness

The QA harness answers a critical question: **does compression preserve comprehensibility?** It generates factual questions from raw configs, then measures whether an LLM can answer them correctly when given the compressed representation vs the raw configs.

The harness has two steps:
1. **Generate questions** — deterministic, no LLM needed
2. **Evaluate** — sends questions + context to an LLM, compares answers to ground truth

### Step 1: Generate Questions

#### What It Does

Parses all `.cfg` files in a directory using the IOS-XR adapter, extracts entities and their attributes, then generates ground-truth Q&A pairs across five categories:

| Category | Example Question | Example Answer |
|---|---|---|
| `SINGLE_VALUE` | What is the Loopback0 IPv4 address for RR-01? | address 10.0.0.11 255.255.255.255 |
| `MULTI_ENTITY` | Which iosxr-access-pe devices have TenGigE0/0/0/0 MTU set to 9216? | APE-R1-01, APE-R1-02, ... |
| `EXISTENCE` | Does RR-01 have EVPN configured? | no |
| `COMPARISON` | Do all iosxr-rr devices share the same clock timezone? | yes |
| `COUNT` | How many TenGigE interfaces does P-CORE-01 have? | 6 |

Questions are generated deterministically from the parsed data. The same seed always produces the same question bank, enabling reproducible benchmarks.

#### Usage

```bash
decoct entity-graph generate-questions \
  --config-dir tests/fixtures/iosxr/configs \
  --output questions.json
```

#### Options

##### `-c, --config-dir <PATH>` (required)

- **Type:** Directory path (must exist)
- **Description:** Directory containing `.cfg` files to parse.

##### `-o, --output <PATH>` (required)

- **Type:** File path
- **Description:** Output path for the question bank JSON file.

##### `--max-questions <N>`

- **Type:** Integer
- **Default:** `200`
- **Description:** Maximum number of questions to generate. If more candidates are available, sampling ensures all five categories are represented.

##### `--seed <N>`

- **Type:** Integer
- **Default:** `42`
- **Description:** Random seed for reproducible sampling. Same seed + same input = same questions.

#### Question Bank Format

The output is a JSON file:

```json
{
  "source_dir": "tests/fixtures/iosxr/configs",
  "entity_count": 86,
  "type_count": 5,
  "pairs": [
    {
      "id": "sv-0001",
      "category": "SINGLE_VALUE",
      "question": "What is the hostname for APE-R1-01?",
      "ground_truth": {
        "answer": "APE-R1-01",
        "evidence_paths": ["APE-R1-01.hostname"]
      },
      "entity_ids": ["APE-R1-01"]
    }
  ]
}
```

Each pair includes:
- **`id`** — unique identifier with category prefix (`sv-`, `me-`, `ex-`, `cmp-`, `cnt-`)
- **`category`** — one of the five question categories
- **`question`** — the natural language question
- **`ground_truth.answer`** — the expected answer extracted directly from the parsed config
- **`ground_truth.evidence_paths`** — dotted attribute paths that justify the answer
- **`entity_ids`** — which entities the question references

### Step 2: Evaluate

#### What It Does

Sends questions to an LLM along with either the raw configs or the compressed entity-graph output as context. Compares LLM answers to ground truth using fuzzy matching (case-insensitive, whitespace-normalised, boolean-equivalent). Reports accuracy overall and by category.

**Requires `decoct[llm]`** (`pip install decoct[llm]`). Uses the Anthropic API and requires the `ANTHROPIC_API_KEY` environment variable.

#### Usage

Evaluate both conditions (raw and compressed):

```bash
decoct entity-graph evaluate \
  --questions questions.json \
  --config-dir tests/fixtures/iosxr/configs \
  --output-dir output/iosxr \
  --condition both
```

Evaluate compressed only, with reader manual:

```bash
decoct entity-graph evaluate \
  --questions questions.json \
  --output-dir output/iosxr \
  --manual docs/entity-graph-data-manual.md \
  --condition compressed
```

#### Options

##### `-q, --questions <PATH>` (required)

- **Type:** File path (must exist)
- **Description:** Path to the question bank JSON file generated by `generate-questions`.

##### `-c, --config-dir <PATH>`

- **Type:** Directory path (must exist)
- **Description:** Directory of raw config files. Required when `--condition` is `raw` or `both`. Used to build the raw context (concatenated configs with filename separators).

##### `--output-dir <PATH>`

- **Type:** Directory path (must exist)
- **Description:** Entity-graph output directory. Required when `--condition` is `compressed` or `both`. Used to build the compressed context (tier_a + all tier_b + all tier_c).

##### `--manual <PATH>`

- **Type:** File path (must exist)
- **Default:** None
- **Description:** Reader manual `.md` file to prepend to the compressed context. This gives the LLM instructions on how to read the three-tier format. See `docs/entity-graph-data-manual.md` for the bundled manual.

##### `--condition <raw|compressed|both>`

- **Type:** Choice
- **Default:** `both`
- **Description:** Which conditions to evaluate. `both` runs two evaluation passes and includes a comparison section in the report.

##### `--model <MODEL_ID>`

- **Type:** String
- **Default:** `claude-sonnet-4-20250514`
- **Description:** Anthropic model ID to use for evaluation.

##### `--format <markdown|json>`

- **Type:** Choice
- **Default:** `markdown`
- **Description:** Output format for the evaluation report.

##### `-o, --output <PATH>`

- **Type:** File path
- **Default:** None (stdout)
- **Description:** Write the report to a file instead of stdout.

##### `--encoding <NAME>`

- **Type:** String
- **Default:** `cl100k_base`
- **Description:** Tiktoken encoding for context token counting.

#### Answer Matching

The harness uses fuzzy matching to compare LLM answers against ground truth:

| Rule | Example |
|---|---|
| Case insensitive | "Yes" matches "yes" |
| Whitespace normalised | "  hello  world  " matches "hello world" |
| Boolean equivalence | "yes" matches "true", "1", "enabled" |
| Numeric equivalence | "9216" matches "9216.0" |
| Substring containment | "9216" matches "The MTU is 9216" |

#### Report Format

The markdown report includes:

**Summary** — per-condition accuracy, model, context tokens, and total answer tokens.

**Accuracy by Category** — breakdown showing which question types the LLM handles best/worst for each condition.

**Comparison** (when both conditions are evaluated) — accuracy delta and context token ratio between compressed and raw.

Example:

```
## Summary

| Condition | Model | Context Tokens | Accuracy | Answer Tokens |
|-----------|-------|---------------:|---------:|--------------:|
| raw       | claude-sonnet-4-20250514 | 98,765 | 87.5% | 1,234 |
| compressed | claude-sonnet-4-20250514 | 24,567 | 85.0% | 1,189 |

## Comparison

- **Accuracy delta** (compressed vs raw): -2.5%
- **Context token ratio**: 0.25x (24,567 / 98,765)
```

---

## Python API

All features are available as importable functions for scripting and integration.

### Stats

```python
from pathlib import Path
from decoct.entity_graph_stats import compute_stats, format_stats_markdown, format_stats_json

report = compute_stats(
    input_dir=Path("configs/"),
    output_dir=Path("output/iosxr/"),
    encoding="cl100k_base",
)

print(f"Input: {report.input_stats.total_tokens} tokens")
print(f"Output: {report.output_total_tokens} tokens")
print(f"Savings: {report.savings_pct_tokens:.1f}%")
print(f"Types: {len(report.type_stats)}")

# Full report
print(format_stats_markdown(report))
```

### Question Generation

```python
from pathlib import Path
from decoct.qa.questions import generate_question_bank, save_question_bank, load_question_bank

bank = generate_question_bank(
    Path("configs/"),
    max_questions=200,
    seed=42,
)

print(f"Generated {len(bank.pairs)} questions from {bank.entity_count} entities")

# Save and reload
save_question_bank(bank, Path("questions.json"))
bank = load_question_bank(Path("questions.json"))
```

### Evaluation

```python
from pathlib import Path
from decoct.qa.evaluate import (
    build_raw_context,
    build_compressed_context,
    evaluate_questions,
    format_evaluation_markdown,
    EvaluationReport,
)
from decoct.qa.questions import load_question_bank
from datetime import datetime, timezone

bank = load_question_bank(Path("questions.json"))

# Build contexts
raw_ctx = build_raw_context(Path("configs/"))
compressed_ctx = build_compressed_context(
    Path("output/iosxr/"),
    manual_path=Path("docs/entity-graph-data-manual.md"),
)

# Evaluate (requires ANTHROPIC_API_KEY)
raw_run = evaluate_questions(raw_ctx, bank, condition="raw", model="claude-sonnet-4-20250514")
comp_run = evaluate_questions(compressed_ctx, bank, condition="compressed", model="claude-sonnet-4-20250514")

report = EvaluationReport(
    timestamp=datetime.now(tz=timezone.utc).isoformat(),
    question_count=len(bank.pairs),
    runs=[raw_run, comp_run],
)

print(format_evaluation_markdown(report))
```

---

## Interpreting Results

### What Good Stats Look Like

- **Token savings > 70%** — the entity-graph pipeline is designed for high-redundancy corpora
- **Phone book width < 20** — narrow phone books mean most per-entity variation is captured in a few attributes
- **Override count near 0** — classes cover entities well, with few individual exceptions
- **base_only_ratio < 0.5** for types with >10 entities — the pipeline found meaningful subgroups

### What Good QA Results Look Like

- **Compressed accuracy within 5% of raw accuracy** — compression preserves comprehensibility
- **SINGLE_VALUE accuracy > 80%** — the LLM can look up specific facts
- **COUNT and EXISTENCE accuracy > 90%** — structural questions should be straightforward
- **Context token ratio < 0.3** — significant compression while maintaining accuracy

### When Results Are Concerning

- **Compressed accuracy significantly lower than raw** — the reader manual may need improvement, or the compressed format is confusing for the question types that fail
- **Low MULTI_ENTITY accuracy** — the LLM struggles to aggregate across entities in the compressed format. Consider improving class naming or phone book structure
- **Low override count but low accuracy** — compression is aggressive but the LLM can't navigate the result. Add more structure to the reader manual

---

## End-to-End Example

Complete workflow from raw configs to evaluation:

```bash
# 1. Run the entity-graph pipeline (produces output/iosxr/)
# (assumes you've already done this step)

# 2. Check compression statistics
decoct entity-graph stats \
  -i tests/fixtures/iosxr/configs \
  -o output/iosxr \
  --format markdown

# 3. Generate questions
decoct entity-graph generate-questions \
  -c tests/fixtures/iosxr/configs \
  -o questions.json \
  --max-questions 200

# 4. Evaluate comprehension (requires ANTHROPIC_API_KEY)
decoct entity-graph evaluate \
  -q questions.json \
  -c tests/fixtures/iosxr/configs \
  --output-dir output/iosxr \
  --manual docs/entity-graph-data-manual.md \
  --condition both \
  --output evaluation-report.md

# 5. Review the report
cat evaluation-report.md
```
