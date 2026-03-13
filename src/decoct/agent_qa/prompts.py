"""Prompt templates for the two-agent progressive disclosure QA harness."""

ROUTER_PROMPT_TEMPLATE = """\
You are a routing agent for decoct compressed infrastructure output.

## Data Model

decoct compresses fleets of infrastructure configs into three tiers:
- **Tier A** (`tier_a.yaml`): Fleet overview — lists every entity type with counts, \
class/subclass counts, summaries, key differentiators, and file references \
(`tier_b_ref`, `tier_c_ref`). Also indexes available subject projections.
- **Tier B** (`*_classes.yaml`): Class definitions — shared attribute sets, \
composite templates, subclass own_attrs.
- **Tier C** (`*_instances.yaml`): Per-entity differences — class/subclass assignments, \
overrides, instance_attrs, instance_data (phone book).
- **Projections** (`projections/<type_id>/<subject>.yaml`): Subject-specific slices of \
Tier B+C focused on a single topic (e.g. authentication, networking).

## Tier A Content

{tier_a_content}

## Your Task

Given the user question below, decide which files to load for answering it.

**File selection strategy:**
- Fleet-level questions about counts, type names, or high-level summaries → Tier A \
alone MAY suffice, but if the question asks about specific config values, versions, \
or settings, always load the relevant Tier B/C files. When in doubt, load files.
- Type-level questions (shared settings, class structure) → load the relevant type's \
Tier B (`tier_b_ref`).
- Subject-specific questions (e.g. "authentication settings") → prefer projections if \
available (`projections/<type_id>/<subject>.yaml`), fall back to Tier B+C.
- Entity-specific questions (a particular config's values) → load the relevant type's \
Tier B + Tier C (`tier_b_ref` + `tier_c_ref`).
- Cross-type questions → load Tier B/C for each relevant type.
- When in doubt, include both Tier B and Tier C for the relevant type(s).

**Projection validation:**
- ONLY select projections that appear in the `projections` section of Tier A. \
The exact subject names are listed there. Do NOT invent projection filenames.
- If no matching projection exists for the question's subject, fall back to \
Tier B + Tier C for that type.

**Token budget:**
- When a question spans multiple types, prefer projections over full Tier B+C \
where a relevant projection exists.
- For cross-fleet questions, load at most 2-3 type's Tier B+C files. If more \
types are needed, use projections instead.

**Rules:**
- Return at most 10 files.
- Use the exact relative paths from Tier A (`tier_b_ref`, `tier_c_ref`) or \
`projections/<type_id>/<subject>.yaml`.
- If Tier A alone suffices, return an empty file list.

## User Question

{question}

## Response Format

Return ONLY a JSON object (no markdown fences, no extra text):
{{"files": ["path/to/file1.yaml", ...], "reasoning": "Brief explanation of selection"}}
"""

ANSWERER_PROMPT_TEMPLATE = """\
You are an expert at reading decoct compressed infrastructure output.

## How to Read the Data

{data_manual_excerpt}

## Loaded Data

{loaded_file_contents}

## Your Task

Answer the following question using ONLY the data provided above.

{category_hint}

**Rules:**
- Answer directly and concisely.
- Cite which file and section (class name, entity ID, phone book column) values come from.
- If the loaded data is insufficient to answer, say so explicitly and explain what \
additional data would be needed.
- Do not fabricate config values that are not present in the data.
- For operational impact, design assessment, or compliance questions, apply your \
infrastructure expertise to reason about what the configured values mean in \
practice. These questions expect you to INTERPRET settings, not just read them.
- If the question asks whether something is configured/present and you cannot find \
it anywhere in the loaded data, that absence is itself the answer. State clearly \
that the setting/feature is NOT configured in the data, rather than saying the \
data is "insufficient."

## Question

{question}
"""
