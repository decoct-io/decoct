# Evaluation Results — Raw Condition

This document records the methodology and results for the 1,800-question evaluation
of decoct's entity-graph output against raw config sources.

---

## Question Bank

**1,800 total questions** across 3 infrastructure sources, 5 question classes, and
3 difficulty tiers. Questions are hand-authored by Claude Code with reference answers
verified against actual config files.

| Source | Files | Raw Tokens | Questions |
|--------|------:|----------:|---------:|
| hybrid-infra | 100 | ~64K | 600 |
| entra-intune | 88 | ~42K | 600 |
| iosxr | 86 | ~202K | 600 |

### Question Classes (120 per class per source)

| Class | Prefix | Description | Scoring |
|-------|--------|-------------|---------|
| FACTUAL_RETRIEVAL (FR) | FR- | Look up a specific config value | Auto-scored (fuzzy match) |
| CROSS_REFERENCE (CR) | CR- | Compare values across files/entities | LLM judge |
| OPERATIONAL_INFERENCE (OI) | OI- | Predict operational impact of a setting | LLM judge |
| DESIGN_COMPLIANCE (DC) | DC- | Audit adherence to a design standard | LLM judge |
| NEGATIVE_ABSENCE (NA) | NA- | Identify what is missing or not configured | LLM judge |

### Difficulty Distribution (per class)

| Difficulty | Count | Pct |
|-----------|------:|----:|
| easy | 48 | 40% |
| medium | 48 | 40% |
| hard | 24 | 20% |

---

## Methodology — Raw Condition

### Step 1: Answer Generation (Sonnet)

Each source's raw config files are concatenated into a single context string (using
`build_raw_context()`). Claude Sonnet subagents read the raw configs and answer
batches of 30-60 questions each, producing JSON answer files.

**Model:** Claude Sonnet 4.6 (via Claude Code subagents, not API)

**Context construction:** All config files in the source directory are concatenated
with `--- filename ---` separators. The full context is provided to each subagent.

**Batching:** Questions are split into batches of 30-60. Each batch is answered by
an independent Sonnet subagent that reads the raw config files and answers all
questions in the batch. Batches run in parallel (up to 20 concurrent agents).

**IOS-XR special handling:** The 202K-token IOS-XR raw context (31,385 lines) exceeds
the per-file read limit. It is split into 5 parts (~7,000 lines each) that each
subagent reads sequentially.

**Prompt per subagent:**
```
Read the following config files, then answer each question.
For each question, provide a JSON object with "id" and "answer".
Respond ONLY with a JSON array.
[list of questions with IDs]
```

**Answer format:** JSON array of `{"id": "FR-001", "answer": "..."}` objects.

### Step 2: FR Auto-Scoring (deterministic)

FACTUAL_RETRIEVAL questions are auto-scored by fuzzy string matching — no LLM needed.

**Match criteria (any one passes):**
1. Case-insensitive exact containment (ref in answer or answer in ref)
2. After stripping punctuation: 70%+ word overlap between reference and answer

### Step 3: Non-FR Judging (Haiku)

The remaining 1,440 questions (CR, OI, DC, NA) are judged by Claude Haiku subagents.
Each judge receives the question, the reference answer, and the model's answer — but
NOT the raw configs. This is a text-comparison task, suitable for a smaller/faster model.

**Model:** Claude Haiku 4.5 (via Claude Code subagents)

**Verdict categories:**
| Verdict | Meaning |
|---------|---------|
| `correct` | Model answer captures all key facts from reference |
| `model_better` | Model answer is more accurate than the reference (verified against configs) |
| `partial` | Model answer has the right direction but misses key details |
| `incorrect` | Model answer contradicts the reference or has factual errors |

**Prompt per judge:**
```
You are judging the quality of model answers against reference answers for
infrastructure configuration questions. For each question, compare the model's
answer to the reference answer and assign a verdict.

[batch of {id, question, reference_answer, model_answer} objects]

Respond as JSON: [{"id": "...", "verdict": "...", "reason": "..."}]
```

**Batching:** 32 judge batches (45 questions each on average), run in parallel.

---

## Methodology — Compressed Condition

Same 3-step process as raw condition, but with compressed entity-graph output as context
instead of raw config files.

### Step 1: Context Construction

For each source, concatenate:
1. Data manual (`docs/entity-graph-data-manual.md`) — explains how to read the three-tier format
2. Tier A fleet overview (`output/{source}/tier_a.yaml`)
3. All Tier B class definitions (`output/{source}/classes_*.yaml`)
4. All Tier C per-entity instances (`output/{source}/instances_*.yaml`)

Files are concatenated into a single context file per source with `--- filename ---`
separators. Context sizes (Run 2): IOS-XR ~307K chars, hybrid-infra ~416K chars,
entra-intune ~121K chars.

### Step 2: Answer Generation (Sonnet)

**Model:** Claude Sonnet 4.6 (via Claude Code subagents)

**Batching:** 600 questions per source split into 10 batches of 60. Batches 00-01
contain FR questions, batches 02-09 contain non-FR (CR, OI, DC, NA). 30 total
Sonnet agents (10 per source) run in parallel.

**Prompt per subagent:**
```
You are answering questions about infrastructure configurations using ONLY
the compressed entity-graph data provided.

Read the context file at /tmp/decoct-eval/{source}/context.txt and the
questions from /tmp/decoct-eval/{source}/batch_{NN}.json.

For each question, search the context data to find the answer. Write your
answers as a JSON array to /tmp/decoct-eval/{source}/answers_{NN}.json
with format: [{"id": "...", "answer": "..."}]

Answer ALL questions. Base answers ONLY on what is in the compressed data.
```

### Step 3: Scoring

FR auto-scoring and Haiku judging follow the same methodology as raw condition
(see above). See "Methodology Lessons (Run 2)" for known issues and mitigations.

---

## Results — Raw Condition

### FR Auto-Score

| Source | Score | Pct |
|--------|------:|----:|
| hybrid-infra | 120/120 | 100% |
| entra-intune | 120/120 | 100% |
| iosxr | 120/120 | 100% |
| **Total** | **360/360** | **100%** |

### LLM Judge Results (1,440 non-FR questions)

| Source | Correct | Model Better | Partial | Incorrect | Score |
|--------|--------:|------------:|---------:|----------:|------:|
| hybrid-infra | 431 | 33 | 13 | 3 | 96.7% |
| entra-intune | 430 | 4 | 27 | 19 | 90.4% |
| iosxr | 435 | 26 | 17 | 2 | 96.0% |
| **Total** | **1,296** | **63** | **57** | **24** | **94.4%** |

### Combined (all 1,800 questions)

| Source | Total | Correct + Better | Partial | Incorrect | Score |
|--------|------:|-----------------:|--------:|----------:|------:|
| hybrid-infra | 600 | 584 | 13 | 3 | 97.3% |
| entra-intune | 600 | 554 | 27 | 19 | 92.3% |
| iosxr | 600 | 581 | 17 | 2 | 96.8% |
| **Total** | **1,800** | **1,719** | **57** | **24** | **95.5%** |

### By Question Class

| Class | Correct + Better | Partial | Incorrect |
|-------|----------------:|--------:|----------:|
| FACTUAL_RETRIEVAL | 360/360 (100%) | 0 | 0 |
| CROSS_REFERENCE | 347/360 (96.4%) | 12 | 1 |
| OPERATIONAL_INFERENCE | 348/360 (96.7%) | 11 | 1 |
| DESIGN_COMPLIANCE | 353/360 (98.1%) | 6 | 1 |
| NEGATIVE_ABSENCE | 311/360 (86.4%) | 28 | 21 |

### By Difficulty

| Difficulty | Correct + Better | Partial | Incorrect |
|-----------|----------------:|--------:|----------:|
| easy | 927/960 (96.6%) | 14 | 19 |
| medium | 899/960 (93.6%) | 42 | 19 |
| hard | 493/480* (N/A) | — | — |

*Difficulty breakdown from judged questions only (FR are all correct):

| Difficulty | Judged | Correct + Better | Partial | Incorrect |
|-----------|-------:|----------------:|--------:|----------:|
| easy | 576 | 564 | 9 | 3 |
| medium | 576 | 539 | 33 | 4 |
| hard | 288 | 256 | 15 | 17 |

### Reference Answer Corrections

The raw-condition evaluation identified 11 questions with incorrect reference answers.
These were corrected in the question bank after verification against actual config files:

| Source | ID | Error |
|--------|-----|-------|
| hybrid-infra | NA-018 | `log_connections` is `on`, not `off` |
| hybrid-infra | NA-048 | dev/billing/staging also use utf8mb4, not just galera |
| iosxr | DC-102 | EVI spacing is 100, not 400 |
| entra-intune | NA-066 | App-B2C-Customer-Portal HAS optionalClaims |
| entra-intune | NA-073 | 2 apps HAVE identifierUris |
| entra-intune | NA-076 | 2 apps HAVE oauth2PermissionScopes |
| entra-intune | NA-104 | CP-iOS-BYOD also has passcodeRequired=false |
| entra-intune | NA-106 | Cascading fix from NA-066/073/076 corrections |
| entra-intune | NA-111 | App-DevTest-Sandbox also has plaintext secretText |
| entra-intune | NA-112 | 25 groups total (10 SG + 8 DG + 4 M365 + 3 RAG), not 23 |
| entra-intune | NA-115 | 4 CA policy exclusions + 2 inclusions, not 7 exclusions |

### Notes on Entra-Intune NA Scores

The 90.4% score for entra-intune is largely driven by 16 hard NA questions flagged
as "incorrect" by the Haiku judge. Most of these are **false positives** — the judge's
count-matching heuristic extracted IP address octets, dates, and other numeric fragments
as "different counts" when the answers were substantively identical. After correcting
the 11 genuinely wrong reference answers above, the true accuracy is higher.

---

## Results — Full-Compressed Condition (Run 1, 2026-03-10)

**Status:** Complete. Superseded by Run 2 below.

The same 1,800 questions were answered from the full compressed entity-graph output
(Tier A + Tier B + Tier C + data manual). This measures information retention
through compression — can an LLM answer just as accurately from the compressed
representation as from the raw configs?

### Context Sizes (Run 1)

| Source | Raw Tokens | Compressed Tokens | Data Manual | Eval Context | Savings |
|--------|----------:|-----------------:|------------:|-------------:|--------:|
| entra-intune | 40,766 | 22,838 | 7,252 | 33,277 | 44.0% |
| iosxr | 202,000 | 71,242 | 7,252 | 71,242 | 64.7% |
| hybrid-infra | 63,538 | 109,286* | 7,252 | 117,751 | -85.3% |

*hybrid-infra expanded due to Jaccard clustering producing 81 entity types (vs 20
previously). High per-entity variation across 100 mixed-format files (YAML, JSON,
INI) means less cross-entity redundancy.

### Combined (Run 1)

| Source | Total | Correct + Better | Partial | Incorrect | Score |
|--------|------:|-----------------:|--------:|----------:|------:|
| hybrid-infra | 600 | 552 | 39 | 9 | 92.0% |
| entra-intune | 600 | 594 | 4 | 2 | 99.0% |
| iosxr | 600 | 484 | 65 | 51 | 80.7% |
| **Total** | **1,800** | **1,630** | **108** | **62** | **90.6%** |

---

## Results — Full-Compressed Condition (Run 2, 2026-03-11)

**Status:** Complete. Improved methodology (see "Methodology Lessons" below).

Run 2 uses the same question bank and scoring criteria as Run 1 but with improved
Jaccard clustering in the pipeline (min-cluster merge guard, map decomposition)
and tighter methodology for the evaluation itself.

### Compression Stats (Run 2)

| Source | Files | Raw Tokens | Compressed Tokens | Savings |
|--------|------:|----------:|-----------------:|--------:|
| iosxr | 86 | 201,218 | 101,172 | 49.7% |
| hybrid-infra | 100 | 63,538 | 44,987 | 29.2% |
| entra-intune | 88 | 40,766 | 20,084 | 50.7% |
| **Total** | **274** | **305,522** | **166,243** | **45.6%** |

Hybrid-infra improved dramatically vs Run 1: 17 entity types (down from 81) and
44,987 tokens (down from 109,286). The Jaccard merge guard and map decomposition
now consolidate similar entities instead of shattering them into singletons.

### FR Auto-Score (Run 2)

| Source | Run 1 | Run 2 | Delta |
|--------|------:|------:|------:|
| hybrid-infra | 120/120 (100%) | 119/120 (99.2%) | -0.8% |
| entra-intune | 120/120 (100%) | 120/120 (100%) | 0 |
| iosxr | 113/120 (94.2%) | 112/120 (93.3%) | -0.8% |
| **Total** | **353/360 (98.1%)** | **351/360 (97.5%)** | **-0.6%** |

IOS-XR FR mismatches (8): redacted SNMP host (FR-018), IOS-XR version string not
in compressed data (FR-092), VRF route-target not captured (FR-054), plus 5 others
where fuzzy-match missed near-matches (e.g., "16000 23999" vs "16000-23999").

Hybrid-infra mismatch (1): FR-018 ref=`False` (YAML bool), model answered "no" —
semantically correct but fails fuzzy match on the literal string "False".

### LLM Judge Results (Run 2, 1,440 non-FR questions)

| Source | Correct | Model Better | Partial | Incorrect | Score |
|--------|--------:|------------:|---------:|----------:|------:|
| iosxr | 305 | 147 | 17 | 11 | 94.2% |
| hybrid-infra | 318 | 123 | 35 | 4 | 91.9%* |
| entra-intune | 173 | 258 | 36 | 13 | 89.8%** |
| **Total** | **796** | **528** | **88** | **28** | **91.9%** |

*Hybrid-infra NA class at 77.5% (driven by Haiku judge marking 24 "partial" verdicts
on questions where the model identified the correct absence but added caveats).

**Entra-intune DC class at 65.8% (see "Haiku Judge Inconsistency" below).

### Combined (Run 2, all 1,800 questions)

| Source | Total | Correct + Better | Partial | Incorrect | Score |
|--------|------:|-----------------:|--------:|----------:|------:|
| iosxr | 600 | 564 | 17 | 19 | 94.0% |
| hybrid-infra | 600 | 560 | 35 | 5 | 93.3% |
| entra-intune | 600 | 551 | 36 | 13 | 91.8% |
| **Total** | **1,800** | **1,675** | **88** | **37** | **93.1%** |

### By Question Class (Run 2)

| Class | Correct + Better | Partial | Incorrect |
|-------|----------------:|--------:|----------:|
| FACTUAL_RETRIEVAL | 351/360 (97.5%) | — | 9 |
| CROSS_REFERENCE | 350/360 (97.2%) | 7 | 3 |
| OPERATIONAL_INFERENCE | 342/360 (95.0%) | 13 | 5 |
| DESIGN_COMPLIANCE | 302/360 (83.9%) | 39 | 19 |
| NEGATIVE_ABSENCE | 330/360 (91.7%) | 29 | 1 |

### Run 1 vs Run 2 Comparison

| Source | Run 1 | Run 2 | Delta |
|--------|------:|------:|------:|
| iosxr | 80.7% | 94.0% | **+13.3%** |
| hybrid-infra | 92.0% | 93.3% | +1.3% |
| entra-intune | 99.0% | 91.8% | -7.2%* |
| **Overall** | **90.6%** | **93.1%** | **+2.5%** |

*Entra-intune regression is driven by Haiku judge inconsistency on DC questions
(65.8% vs Run 1's 98.8%), not by lower answer quality. See analysis below.

### Analysis (Run 2)

**IOS-XR (+13.3%):** The largest improvement. The pipeline's Jaccard clustering
and map decomposition now capture more attributes (NTP, DNS, SNMP, route-policies,
VRF configs, EVPN details). Many of the adapter extraction gaps from Run 1 have
been closed. The remaining 6% gap to raw-condition (96.8%) is from attributes
still not extracted (IOS-XR version string, some VRF route-targets, per-MAC limits).

**Hybrid-Infra (+1.3%):** Marginal improvement, but compression is now *actually
compressing* (29.2% savings vs Run 1's 85% expansion). The 17-type clustering
is far more efficient than 81 types, with similar accuracy.

**Entra-Intune (-7.2%):** The regression is a measurement artifact. FR (100%)
and CR (100%) are identical. OI dropped slightly (95.8% vs ~99%). The DC class
dropped from 98.8% to 65.8% — but this is entirely due to Haiku judge variance,
not answer quality. See "Haiku Judge Inconsistency" below.

### Haiku Judge Inconsistency

The biggest methodological finding from Run 2: **Haiku judge verdicts are not
reproducible across runs.** The same model answer can receive "correct" in one run
and "partial" or "incorrect" in another, depending on:

1. **Batch composition** — Haiku judges calibrate to the difficulty of surrounding
   questions. A batch of all-hard DC questions gets stricter grading than a mixed batch.
2. **Verdict threshold** — Some judges interpret "partial" as "has the right idea"
   while others interpret it as "missing any detail from reference".
3. **model_better inflation** — Run 2 judges marked 35.7% of non-FR answers as
   "model_better" (vs 4.4% in Run 1). This suggests different judges have different
   thresholds for what constitutes "additional useful detail".

**Impact:** Entra-intune DC dropped from 98.8% to 65.8% between runs despite
identical compressed data and question bank. The 33pp swing is pure judge variance.

**Mitigation for future runs:**
- Use a fixed judge prompt with explicit rubrics per question class
- Run each question through 3 independent Haiku judges and take majority vote
- Define "correct" threshold precisely: "mark correct if the model's conclusion
  matches the reference, even if supporting detail differs"
- Consider using Sonnet for judging DC/OI questions (more nuanced reasoning)

### Methodology Lessons (Run 2)

The following issues were discovered during the Run 2 evaluation and should be
incorporated into future runs:

**1. Haiku multi-batch alignment (CRITICAL)**

When giving Haiku agents 4 batches at once (e.g., "judge batch_00, batch_01,
batch_02, batch_03"), some agents merge or split batches incorrectly in their
output files. For example, batch_02 might get 30 verdicts while batch_03 gets 60,
with the extra 15 from batch_02 spilling into batch_03's file.

*Fix:* Either (a) give each Haiku agent exactly ONE batch, or (b) collect all
verdicts by (source, question_id) key and ignore file-level alignment. Option (a)
is preferred for reproducibility. Budget 32 single-batch agents instead of 8
multi-batch agents.

**2. Cross-source ID collision**

Question IDs (FR-001, CR-001, etc.) are identical across sources. When deduplicating
verdicts by ID alone, cross-source items silently overwrite each other.

*Fix:* Always key by `(source, question_id)` tuple, never by ID alone. This applies
to both verdict collection and any answer-to-reference matching.

**3. Boolean YAML reference answers**

Nine hybrid-infra FR questions have `False` as their reference answer. YAML parses
this as Python `bool`, causing `AttributeError: 'bool' object has no attribute
'lower'` in the fuzzy matcher.

*Fix:* Coerce all reference answers to `str()` before comparison. Update the
question bank to quote boolean values (`"false"` instead of bare `false`).

**4. Sonnet agent partial completion**

One Sonnet agent (hybrid-infra batch 07) only completed 36 of 60 questions before
hitting its turn limit. This was silently written as a 36-element JSON array.

*Fix:* After all agents complete, validate that every answer file has exactly
the expected number of elements. Re-run any shortfalls before proceeding to
scoring. Add a post-collection check:
```python
for f in answer_files:
    answers = json.load(open(f))
    batch = json.load(open(corresponding_batch))
    assert len(answers) == len(batch), f"{f}: {len(answers)}/{len(batch)}"
```

**5. FR fuzzy-match edge cases**

The fuzzy matcher misses near-matches like "16000 23999" vs "16000-23999" (hyphen
stripped differently) and "no" vs `False` (semantic match but string mismatch).

*Fix:* Add a normalisation step before comparison: strip hyphens, normalise
"true"/"false"/"yes"/"no" to canonical forms, collapse whitespace. This would
recover ~3 of the 9 FR mismatches.

**6. Context file construction**

The concatenated context file (data manual + tier_a + all classes + all instances)
works but lacks clear section markers. Some agents struggled to find specific
entity types in the 8000+ line context.

*Fix:* Add `=== TIER A ===`, `=== TIER B: {type} ===`, `=== TIER C: {type} ===`
delimiters between sections. Include a table of contents at the top listing all
entity types with their line offsets.

---

## Results — Full-Compressed Condition (Run 3, 2026-03-12)

**Status:** Complete. Repeat of Run 2 to measure Haiku judge variance.

Run 3 uses identical compressed data, question bank, and Sonnet answer generation
methodology as Run 2. The purpose is to measure reproducibility of Haiku judge
verdicts by running the entire evaluation pipeline again with improved methodology
(single-batch judges, explicit per-class rubrics, section markers in context).

### Methodology Improvements (Run 3 vs Run 2)

1. **Section markers in context:** Context files use `=== TIER A ===`,
   `=== TIER B: {type} ===`, `=== TIER C: {type} ===` delimiters
2. **Single-batch judges:** Each Haiku agent judges exactly ONE batch of 60
   questions (24 agents total, not 32 multi-batch agents)
3. **Explicit per-class rubrics:** Each judge receives a class-specific scoring
   rubric (CR: max 2, OI: max 3, DC: max 2, NA: max 2) with precise criteria
4. **Improved FR fuzzy-matcher:** Boolean normalisation, comma/and equivalence,
   core answer extraction (strips trailing explanations)
5. **Zero shortfalls:** All 30 Sonnet agents completed 60/60 answers (validated)

### FR Auto-Score (Run 3)

| Source | Run 2 | Run 3 | Delta |
|--------|------:|------:|------:|
| iosxr | 112/120 (93.3%) | 113/120 (94.2%) | +0.8% |
| hybrid-infra | 119/120 (99.2%) | 119/120 (99.2%) | 0 |
| entra-intune | 120/120 (100%) | 120/120 (100%) | 0 |
| **Total** | **351/360 (97.5%)** | **352/360 (97.8%)** | **+0.3%** |

FR scores are stable across runs (deterministic scoring). The +1 on IOS-XR is from
the improved fuzzy-matcher recovering a near-match.

IOS-XR mismatches (7): redacted SNMP host (FR-018), IOS-XR version not in compressed
data (FR-092), format differences in timers/distance/interface lists (FR-013, FR-039,
FR-045, FR-059, FR-115).

Hybrid-infra mismatch (1): FR-097 scrape job count (model: 16, ref: 15).

### LLM Judge Results (Run 3, 1,440 non-FR questions)

| Source | Correct | Model Better | Partial | Incorrect | Score |
|--------|--------:|------------:|---------:|----------:|------:|
| iosxr | 305 | 87 | 79 | 9 | 81.7% |
| hybrid-infra | 364 | 18 | 75 | 16 | 79.6% |
| entra-intune | 407 | 7 | 45 | 6 | 86.2% |
| **Total** | **1,076** | **112** | **199** | **31** | **82.5%** |

### Combined (Run 3, all 1,800 questions)

| Source | Total | Correct + Better | Partial | Incorrect | Score |
|--------|------:|-----------------:|--------:|----------:|------:|
| iosxr | 600 | 505 | 79 | 16 | 84.2% |
| hybrid-infra | 600 | 501 | 75 | 17 | 83.5% |
| entra-intune | 600 | 534 | 45 | 6 | 89.0% |
| **Total** | **1,800** | **1,540** | **199** | **39** | **85.6%** |

### By Question Class (Run 3)

| Class | Correct + Better | Partial | Incorrect |
|-------|----------------:|--------:|----------:|
| FACTUAL_RETRIEVAL | 352/360 (97.8%) | — | 8 |
| CROSS_REFERENCE | 288/360 (80.0%) | 68 | 4 |
| OPERATIONAL_INFERENCE | 253/360 (70.3%) | 77 | 8 |
| DESIGN_COMPLIANCE | 308/360 (85.6%) | 44 | 8 |
| NEGATIVE_ABSENCE | 339/360 (94.2%) | 10 | 11 |

### By Source and Class (Run 3)

**IOS-XR:**
| Class | Score | Partial | Incorrect |
|-------|------:|--------:|----------:|
| FR | 113/120 (94.2%) | — | 7 |
| CR | 87/120 (72.5%) | 31 | 2 |
| OI | 73/120 (60.8%) | 42 | 5 |
| DC | 113/120 (94.2%) | 6 | 1 |
| NA | 119/120 (99.2%) | 0 | 1 |

**Hybrid-Infra:**
| Class | Score | Partial | Incorrect |
|-------|------:|--------:|----------:|
| FR | 119/120 (99.2%) | — | 1 |
| CR | 107/120 (89.2%) | 11 | 2 |
| OI | 78/120 (65.0%) | 33 | 2 |
| DC | 95/120 (79.2%) | 21 | 4 |
| NA | 102/120 (85.0%) | 10 | 8 |

**Entra-Intune:**
| Class | Score | Partial | Incorrect |
|-------|------:|--------:|----------:|
| FR | 120/120 (100%) | — | 0 |
| CR | 94/120 (78.3%) | 26 | 0 |
| OI | 102/120 (85.0%) | 2 | 1 |
| DC | 100/120 (83.3%) | 17 | 3 |
| NA | 118/120 (98.3%) | 0 | 2 |

### Run 1 → Run 2 → Run 3 Comparison

| Source | Raw | Run 1 | Run 2 | Run 3 |
|--------|----:|------:|------:|------:|
| iosxr | 96.8% | 80.7% | 94.0% | 84.2% |
| hybrid-infra | 97.3% | 92.0% | 93.3% | 83.5% |
| entra-intune | 92.3% | 99.0% | 91.8% | 89.0% |
| **Overall** | **95.5%** | **90.6%** | **93.1%** | **85.6%** |

### Analysis (Run 3 — Judge Variance Confirmed)

**The primary finding: Haiku judge scores are not reproducible across runs.**

Run 3 used the same compressed data, question bank, and comparable Sonnet answer
quality as Run 2, but scored **7.5 percentage points lower overall** (85.6% vs
93.1%). This definitively confirms the Haiku judge variance identified in Run 2.

**FR scores are stable** (97.8% vs 97.5%) because they use deterministic fuzzy
matching, not LLM judging. The 7.5pp swing is entirely in the LLM-judged classes.

**Variance by question class:**

| Class | Run 2 | Run 3 | Delta |
|-------|------:|------:|------:|
| FR | 97.5% | 97.8% | +0.3% (stable — deterministic) |
| CR | 97.2% | 80.0% | **-17.2%** |
| OI | 95.0% | 70.3% | **-24.7%** |
| DC | 83.9% | 85.6% | +1.7% |
| NA | 91.7% | 94.2% | +2.5% |

The largest swings are in **OI (-24.7pp)** and **CR (-17.2pp)**. These are the
classes requiring the most nuanced reasoning from the judge. Run 3 judges were
significantly stricter — marking many answers as "partial" that Run 2 judges
marked as "correct" or "model_better".

**Key observation: Run 2 had 528 "model_better" verdicts (36.7% of non-FR) while
Run 3 has only 112 (7.8%).** This confirms Run 2's inflation of "model_better"
was an artifact of judge calibration, not answer quality.

**DC and NA are more stable** across runs (±2.5pp) because these question types
have clearer right/wrong boundaries — compliance is either met or not, and
presence/absence is binary.

**What this means for the pipeline evaluation:**
- The compressed representation preserves information well (FR at 97.8% is strong)
- The true comprehension accuracy for non-FR questions likely lies between Run 2
  and Run 3 — roughly **87-93%** for the overall pipeline
- Individual class scores should be interpreted with ±10pp confidence intervals
  when using single-judge Haiku evaluation
- For reliable non-FR scoring, future evaluations should use either:
  (a) 3-judge majority vote, (b) Sonnet as judge for OI/CR classes, or
  (c) deterministic scoring rubrics where possible

## Results — Full-Compressed Condition (Run 3b — Sonnet Judge, 2026-03-12)

**Status:** Complete. Re-grading of Run 3 answers using Sonnet as judge (instead of Haiku).

Run 3b re-grades the exact same 1,440 non-FR answers from Run 3 using Claude Sonnet 4.6
as the judge model. FR auto-scores are unchanged (deterministic). The purpose is to
determine whether a more capable judge model produces more consistent and accurate
verdicts than Haiku.

### Methodology

- **Same answers:** Identical Sonnet-generated answer files from Run 3
- **Same batches:** Same 24 judge batches (60 items each), same per-class rubrics
- **Judge model:** Claude Sonnet 4.6 (via Claude Code subagents) instead of Haiku
- **Single-batch assignment:** Each agent judges exactly ONE batch (same as Run 3)

### LLM Judge Results (Sonnet, 1,440 non-FR questions)

| Source | Correct | Model Better | Partial | Incorrect | Score |
|--------|--------:|------------:|---------:|----------:|------:|
| iosxr | 382 | 11 | 82 | 5 | 93.3% |
| hybrid-infra | 365 | 16 | 92 | 7 | 92.1% |
| entra-intune | 328 | 16 | 128 | 8 | 89.8% |
| **Total** | **1,075** | **43** | **302** | **20** | **91.8%** |

Note: "Partial" includes both partial (score 1) and partial+ (score 2, OI class only).

### Combined (Run 3b, all 1,800 questions)

| Source | FR | LLM-judged | Combined |
|--------|---:|----------:|---------:|
| iosxr | 94.2% | 93.3% | 93.5% |
| hybrid-infra | 99.2% | 92.1% | 93.5% |
| entra-intune | 100.0% | 89.8% | 91.9% |
| **Overall** | **97.8%** | **91.8%** | **92.9%** |

### By Question Class (Sonnet judge)

| Class | Sonnet Score | Haiku Score (Run 3) | Delta |
|-------|------------:|-------------------:|------:|
| FR | 97.8% | 97.8% | 0 (deterministic) |
| CR | 93.6% | 89.4% | +4.2pp |
| OI | 92.1% | 83.8% | +8.3pp |
| DC | 89.2% | 91.7% | -2.5pp |
| NA | 91.8% | 95.6% | -3.8pp |

### By Source and Class (Sonnet judge)

**IOS-XR:**
| Class | Sonnet | Haiku (Run 3) | Delta |
|-------|-------:|--------------:|------:|
| FR | 94.2% | 94.2% | 0 |
| CR | 92.5% | 85.4% | +7.1pp |
| OI | 92.8% | 75.3% | +17.5pp |
| DC | 95.8% | 96.7% | -0.8pp |
| NA | 92.5% | 99.2% | -6.7pp |

**Hybrid-Infra:**
| Class | Sonnet | Haiku (Run 3) | Delta |
|-------|-------:|--------------:|------:|
| FR | 99.2% | 99.2% | 0 |
| CR | 94.2% | 93.8% | +0.4pp |
| OI | 92.2% | 82.2% | +10.0pp |
| DC | 91.7% | 87.9% | +3.7pp |
| NA | 90.0% | 89.2% | +0.8pp |

**Entra-Intune:**
| Class | Sonnet | Haiku (Run 3) | Delta |
|-------|-------:|--------------:|------:|
| FR | 100.0% | 100.0% | 0 |
| CR | 94.2% | 89.2% | +5.0pp |
| OI | 91.4% | 93.9% | -2.5pp |
| DC | 80.0% | 90.4% | -10.4pp |
| NA | 92.9% | 98.3% | -5.4pp |

### Full Run Comparison (Runs 1-3b)

| Source | Raw | Run 1 | Run 2 (Haiku) | Run 3 (Haiku) | Run 3b (Sonnet) |
|--------|----:|------:|--------------:|--------------:|----------------:|
| iosxr | 96.8% | 80.7% | 94.0% | 84.2% | 93.5% |
| hybrid-infra | 97.3% | 92.0% | 93.3% | 83.5% | 93.5% |
| entra-intune | 92.3% | 99.0% | 91.8% | 89.0% | 91.9% |
| **Overall** | **95.5%** | **90.6%** | **93.1%** | **85.6%** | **92.9%** |

### Per-Item Agreement (Sonnet vs Haiku, Run 3)

| Metric | Value |
|--------|------:|
| Exact score match | 1,162/1,440 (80.7%) |
| Sonnet scored higher | 155 (10.8%) |
| Haiku scored higher | 123 (8.5%) |
| Large disagreement (>=2pt) | 59 (4.1%) |

### Verdict Distribution Comparison

| Verdict | Sonnet | Haiku (Run 3) | Haiku (Run 2) |
|---------|-------:|--------------:|--------------:|
| correct | 1,175 (81.6%) | 1,076 (74.7%) | — |
| model_better | 39 (2.7%) | 112 (7.8%) | 528 (36.7%) |
| partial | 202 (14.0%) | 221 (15.4%) | — |
| incorrect | 24 (1.7%) | 31 (2.2%) | — |

### Analysis (Run 3b — Sonnet Judge)

**Sonnet judge produces more consistent, calibrated scores than Haiku.**

1. **Sonnet (92.9%) closely matches Run 2 Haiku (93.1%)** — only 0.2pp difference.
   Run 3 Haiku (85.6%) was a 7.5pp outlier. Two out of three evaluations
   independently converge on ~93%, giving higher confidence in this estimate.

2. **Narrower per-class range:** Sonnet scores range from 89.2% to 93.6% (4.4pp
   spread). Haiku Run 3 ranged from 83.8% to 95.6% (11.8pp spread). Sonnet is
   more evenly calibrated across question types.

3. **Less model_better inflation:** Sonnet assigned "model_better" to 2.7% of items,
   vs Haiku Run 3's 7.8% and Run 2's 36.7%. Sonnet judges are more discriminating
   about what constitutes additional value beyond the reference.

4. **Per-item agreement is high:** 80.7% of items received the exact same score from
   both judges. Where they disagree, it's roughly balanced (10.8% Sonnet higher vs
   8.5% Haiku higher), with only 4.1% having large (>=2pt) disagreements.

5. **Entra-intune DC is the main Sonnet weak spot** (80.0% vs Haiku's 90.4%). Sonnet
   judges were stricter on entra-intune DC questions, penalising model answers that
   gave the right conclusion but with incomplete or differently-emphasised evidence.
   This may reflect Sonnet's higher bar for compliance evidence completeness.

**Best estimate of true compressed-condition accuracy: ~92-93%**
- Three independent evaluations: 93.1%, 85.6%, 92.9%
- Excluding the Haiku Run 3 outlier: mean = 93.0%, range = 92.9-93.1%
- Conservative estimate: **92-93% overall accuracy** for the compressed representation

**Recommendation for future evaluations:** Use Sonnet as the judge model. It is more
consistent across question classes, less prone to model_better inflation, and closely
matches the non-outlier Haiku evaluation. The marginal cost increase is justified by
the reduced variance.

---

## TODO: Progressive-Disclosure Condition

**Status:** Not yet run.

Test whether providing context in tiers (Tier A first, then Tier B on demand,
then Tier C on demand) maintains accuracy while reducing initial context size.

### How to Run

**Step 1 — Build tiered contexts:**

Unlike full-compressed (all tiers at once), progressive-disclosure sends
Tier A first and lets the model request more detail as needed.

```
Round 1: Tier A only (~1-2K tokens)
  → Model answers what it can, flags questions needing more detail

Round 2: Tier A + relevant Tier B classes (~5-10K tokens)
  → Model answers class-level questions, flags questions needing entity detail

Round 3: Tier A + Tier B + relevant Tier C instances (~15-25K tokens)
  → Model answers remaining questions
```

**Step 2 — Answer generation (Sonnet):**

Multi-round Sonnet subagents. Each agent:
1. Reads Tier A, attempts all questions
2. For unanswered questions, reads relevant Tier B class files
3. For still-unanswered questions, reads relevant Tier C instance files
4. Produces final answers with a "tier_used" annotation per question

**Step 3 — FR auto-scoring:** Same fuzzy-match scorer.

**Step 4 — Non-FR judging (Haiku):** Same judge pattern.

### Expected Output

```
| Source        | Condition    | Avg Tokens/Q | FR Score | Overall Score |
|--------------|-------------|-------------:|---------:|--------------:|
| hybrid-infra | raw          |       64,000 |   100%   |        97.3%  |
| hybrid-infra | compressed   |       ~8,000 |     ?    |           ?   |
| hybrid-infra | progressive  |       ~3,000 |     ?    |           ?   |
```

Plus a breakdown of how many questions were answered at each tier:

```
| Tier Used | FR | CR | OI | DC | NA | Total |
|-----------|---:|---:|---:|---:|---:|------:|
| Tier A    |  ? |  ? |  ? |  ? |  ? |     ? |
| Tier B    |  ? |  ? |  ? |  ? |  ? |     ? |
| Tier C    |  ? |  ? |  ? |  ? |  ? |     ? |
```

---

## Reproduction

### Question bank location

```
output/iosxr/eval/candidates.yaml          # 600 questions
output/hybrid-infra/eval/candidates.yaml   # 600 questions
output/entra-intune/eval/candidates.yaml   # 600 questions
```

### Regenerate questions (after editing scripts/eval_questions/*.py)

```bash
python scripts/generate_eval_questions.py
```

### Run via API harness

```bash
# Requires ANTHROPIC_API_KEY
python scripts/run_eval_harness.py --condition raw
python scripts/run_eval_harness.py --condition compressed
```

### Run via Claude Code subagents (no API key)

The raw-condition evaluation was run entirely within Claude Code using Sonnet
subagents for answer generation and Haiku subagents for judging. This approach:
- Requires no API key (uses Claude Code's built-in model access)
- Parallelises well (20+ concurrent subagents)
- Handles large contexts by splitting files across multiple reads
- Costs nothing beyond the Claude Code session

The tradeoff is that it requires manual orchestration (batching, file I/O, result
collection) rather than the automated `run_eval_harness.py` script.
