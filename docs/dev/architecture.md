# Architecture Guide

Technical architecture reference for decoct contributors.

## Overview

decoct compresses infrastructure configuration data for LLM context windows through a
three-phase pipeline:

1. **Assertion Preparation** -- design standards are structured into machine-evaluable assertions.
2. **Schema Preparation** -- platform defaults are extracted from vendor schemas or learned via LLM.
3. **Deterministic Processing** -- a pipeline of ordered passes applies assertions and schemas as tree transformations on the document.

Phase 1 (the current implementation) focuses on the deterministic pipeline with
pre-authored schemas and assertions. LLM-assisted learning of schemas and assertions
is available as an optional dependency (`pip install decoct[llm]`).

## High-Level Architecture

```
                          +------------------+
                          |   CLI (cli.py)   |
                          +--------+---------+
                                   |
                    file(s) or stdin, options
                                   |
                                   v
                        +--------------------+
                        | Format Detection   |
                        | (formats.py)       |
                        +--------+-----------+
                                 |
                     detect_format() + detect_platform()
                     load JSON / INI / YAML
                                 |
                                 v
                        +--------------------+
                        | Normalize to       |
                        | CommentedMap       |
                        | (ruamel.yaml)      |
                        +--------+-----------+
                                 |
                                 v
                        +--------------------+
                        | Pipeline           |
                        | (pipeline.py)      |
                        |                    |
                        | Topological sort   |
                        | then run passes    |
                        | in order           |
                        +--------+-----------+
                                 |
              +------------------+------------------+
              |                  |                   |
              v                  v                   v
     +--------------+  +-----------------+  +----------------+
     | Generic      |  | Schema-Aware    |  | Assertion-     |
     | Passes       |  | Passes          |  | Aware Passes   |
     | strip-secrets|  | strip-defaults  |  | strip-conformant
     | strip-comments  | emit-classes    |  | annotate-devs  |
     | drop-fields  |  |                 |  | deviation-     |
     | keep-fields  |  |                 |  |   summary      |
     | prune-empty  |  |                 |  |                |
     +--------------+  +-----------------+  +----------------+
                                 |
                                 v
                        +--------------------+
                        | YAML Output        |
                        | + Token Stats      |
                        | (tokens.py)        |
                        +--------------------+
```

## Module Dependency Graph

```
cli.py
  |-- formats.py              (format detection, input loading)
  |-- pipeline.py             (pass orchestration)
  |     `-- passes/base.py    (BasePass, PassResult, registry)
  |-- tokens.py               (token counting, reports)
  |-- passes/*                (all pass modules, registered via import)
  |     |-- strip_secrets.py
  |     |-- strip_comments.py
  |     |-- strip_defaults.py   --> schemas/models.py
  |     |-- emit_classes.py     --> schemas/models.py
  |     |-- drop_fields.py
  |     |-- keep_fields.py
  |     |-- strip_conformant.py --> assertions/models.py, assertions/matcher.py
  |     |-- annotate_deviations.py --> assertions/models.py, assertions/matcher.py
  |     |-- deviation_summary.py   --> assertions/models.py
  |     `-- prune_empty.py
  |-- schemas/
  |     |-- models.py         (Schema dataclass)
  |     |-- loader.py         (YAML validation -> Schema)
  |     `-- resolver.py       (short name -> bundled file path)
  |-- assertions/
  |     |-- models.py         (Assertion, Match dataclasses)
  |     |-- loader.py         (YAML validation -> list[Assertion])
  |     `-- matcher.py        (evaluate_match, find_matches)
  |-- profiles/
  |     |-- loader.py         (Profile dataclass + YAML loader)
  |     `-- resolver.py       (short name -> bundled file path)
  `-- learn.py                (optional LLM dep: learn_schema, learn_assertions)
```

Key insight: passes depend on `schemas/models` and `assertions/models` but never on
each other's internals. `pipeline.py` depends on `passes/base.py` only. `cli.py` is
the composition root that imports everything and wires it together.

## Data Flow

The end-to-end flow for `decoct compress`:

1. **CLI receives input.** `cli.py` accepts file paths, directories (with optional
   `--recursive`), or stdin. Directories are expanded to matching files by extension
   (`.yaml`, `.yml`, `.json`, `.ini`, `.conf`, `.cfg`, `.cnf`, `.properties`).

2. **Format detection and normalisation.** `formats.py` detects the input format by
   file extension (`detect_format()`). JSON is parsed with `json.loads()` then
   converted to `CommentedMap`/`CommentedSeq` via `json_to_commented_map()`.
   INI/key-value files are parsed via `configparser` or flat line parsing into
   `CommentedMap` via `ini_to_commented_map()`. YAML is loaded directly with
   `ruamel.yaml` in round-trip mode. All paths produce a `CommentedMap` document.

3. **Platform auto-detection.** If no `--schema` is provided, `detect_platform()`
   inspects the document structure to identify the platform (Kubernetes, Docker
   Compose, Terraform, GitHub Actions, etc.) and returns a bundled schema name.

4. **Pass list construction.** `cli.py` calls `_build_passes()` which either:
   - Loads a profile (`--profile`) that bundles schema, assertions, and pass config.
   - Builds a default pipeline: `strip-secrets` + `strip-comments`, optionally
     `strip-defaults` + `emit-classes` (if schema available), optionally
     `strip-conformant` + `annotate-deviations` + `deviation-summary`
     (if assertions available), always ending with `prune-empty`.

5. **Topological sort.** `Pipeline.__init__()` sorts passes using Kahn's algorithm,
   respecting `run_after` and `run_before` constraints. Raises `ValueError` on cycles.

6. **In-place document transformation.** `Pipeline.run()` iterates the sorted passes.
   Each pass receives the `CommentedMap` document, mutates it in-place, and returns a
   `PassResult` with statistics (items removed, detail messages). Timing is recorded
   per pass.

7. **Output.** `cli.py` dumps the transformed document back to YAML via `ruamel.yaml`
   round-trip mode. If `--stats` or `--stats-only` is set, `tokens.py` computes a
   `TokenReport` comparing input and output token counts using tiktoken.

## Pass System

### BasePass

Defined in `src/decoct/passes/base.py`:

```python
class BasePass:
    name: str = ""
    run_after: list[str] = []
    run_before: list[str] = []

    def run(self, doc: Any, **kwargs: Any) -> PassResult:
        raise NotImplementedError
```

Every pass subclasses `BasePass`, sets a `name`, declares ordering constraints via
`run_after` and `run_before`, and implements `run()` to mutate the document in-place.

### PassResult

```python
@dataclass
class PassResult:
    name: str
    items_removed: int = 0
    details: list[str] = field(default_factory=list)
```

Returned by every pass to report what was changed. The `details` list carries
human-readable messages shown when `--show-removed` is active.

### Registry

The pass registry is a module-level dict in `passes/base.py`:

- `register_pass(cls)` -- decorator that registers a pass class by its `name`.
- `get_pass(name)` -- looks up a pass class by name; raises `KeyError` if unknown.
- `list_passes()` -- returns sorted list of all registered pass names.
- `clear_registry()` -- clears the registry (testing only).

Passes are registered at import time. `cli.py` imports all pass modules at the top
level to ensure they are registered before any pipeline is built.

### Topological Sort

`pipeline.py` implements `_topological_sort()` using Kahn's algorithm:

- Builds a directed graph from `run_after` (dependency runs first) and `run_before`
  (this pass runs first) constraints.
- Constraints referencing passes not in the current pipeline are silently ignored.
- Ties are broken alphabetically for deterministic ordering.
- Raises `ValueError` with the involved pass names if a cycle is detected.

### Registered Passes and Their Ordering

| Pass                  | `run_after`                                              | `run_before`                            |
|-----------------------|----------------------------------------------------------|-----------------------------------------|
| `strip-secrets`       | (none)                                                   | (none)                                  |
| `strip-comments`      | (none)                                                   | (none)                                  |
| `drop-fields`         | (none)                                                   | (none)                                  |
| `keep-fields`         | (none)                                                   | (none)                                  |
| `strip-defaults`      | `strip-secrets`, `strip-comments`                        | (none)                                  |
| `strip-conformant`    | `strip-defaults`                                         | (none)                                  |
| `prune-empty`         | `strip-defaults`, `strip-conformant`, `drop-fields`, `keep-fields` | (none)                      |
| `emit-classes`        | `strip-defaults`, `prune-empty`                          | `annotate-deviations`, `deviation-summary` |
| `annotate-deviations` | `strip-conformant`                                       | (none)                                  |
| `deviation-summary`   | `annotate-deviations`                                    | (none)                                  |

This produces the typical execution order:

```
strip-secrets -> strip-comments -> strip-defaults -> strip-conformant
  -> drop-fields / keep-fields -> prune-empty -> emit-classes
  -> annotate-deviations -> deviation-summary
```

## Schema System

### Schema Dataclass

Defined in `src/decoct/schemas/models.py`:

```python
Confidence = Literal["authoritative", "high", "medium", "low"]

@dataclass
class Schema:
    platform: str
    source: str
    confidence: Confidence
    defaults: dict[str, Any] = field(default_factory=dict)
    drop_patterns: list[str] = field(default_factory=list)
    system_managed: list[str] = field(default_factory=list)
```

- `defaults` -- dotted-path keys mapping to platform default values. Supports `*`
  (single-segment wildcard) and `**` (any-depth wildcard).
- `drop_patterns` -- paths that should always be removed (internal IDs, etc.).
- `system_managed` -- paths of fields generated/managed by the system.

### Loader

`schemas/loader.py` provides `load_schema(path) -> Schema`. It validates that the
YAML file is a mapping with required fields `platform`, `source`, and `confidence`,
and that `confidence` is one of the four valid levels.

### Resolver

`schemas/resolver.py` provides `resolve_schema(name_or_path) -> Path`. If the input
is a short name (no path separators, no file extension), it looks up the bundled
schema file. Otherwise it returns the input as a `Path`.

There are currently 25 bundled schemas covering: ansible-playbook, argocd,
aws-cloudformation, azure-arm, cloud-init, docker-compose, entra-id, fluent-bit,
gcp-resources, github-actions, gitlab-ci, grafana, intune, kafka, keycloak,
kubernetes, mariadb-mysql, mongodb, opentelemetry-collector, postgresql, prometheus,
redis, sshd-config, terraform-state, and traefik.

### Consumers

- `StripDefaultsPass` -- removes fields whose values match schema defaults.
- `EmitClassesPass` -- records stripped defaults as class definitions for reconstruction.

## Assertion System

### Assertion Dataclass

Defined in `src/decoct/assertions/models.py`:

```python
Severity = Literal["must", "should", "may"]

@dataclass
class Match:
    path: str
    value: Any = None
    pattern: str | None = None
    range: list[float | int] | None = None
    contains: Any = None
    not_value: Any = None
    exists: bool | None = None

@dataclass
class Assertion:
    id: str
    assert_: str
    rationale: str
    severity: Severity
    match: Match | None = None
    exceptions: str | None = None
    example: str | None = None
    related: list[str] | None = None
    source: str | None = None
```

`Match` supports six condition types: exact `value`, regex `pattern`, numeric `range`
(inclusive `[min, max]`), list `contains`, `not_value`, and `exists` (key
presence/absence). Only one condition is evaluated per `Match` -- the first non-None
field wins.

Assertions without a `match` field are LLM context only -- they are included in
deviation summaries but are not machine-evaluated.

### Matcher

`assertions/matcher.py` provides two functions:

- `evaluate_match(match, value) -> bool` -- tests whether a single value satisfies a
  match condition. Returns `True` if conformant.
- `find_matches(node, path, assertion) -> list[tuple]` -- walks the document tree,
  resolving wildcard paths, and returns `(path, value, parent_node, key)` tuples for
  all locations matching the assertion's path pattern. For `exists` assertions, the
  path is split into parent pattern + leaf key, and absent keys are represented with a
  sentinel value.

Path matching uses `*` for single-segment wildcards and `**` for any-depth wildcards,
delegating to `_path_matches()` from `drop_fields.py`.

### Loader

`assertions/loader.py` provides `load_assertions(path) -> list[Assertion]`. It
validates that the YAML file contains an `assertions` key with a list of assertion
mappings, each with required fields `id`, `assert`, `rationale`, and `severity`.

### Consumers

- `StripConformantPass` -- removes values that match assertions (conformant = not interesting).
- `AnnotateDeviationsPass` -- adds YAML comments to values that deviate from assertions.
- `DeviationSummaryPass` -- adds a top-level summary of all deviations found.

## Profile System

### Profile Dataclass

Defined in `src/decoct/profiles/loader.py`:

```python
@dataclass
class Profile:
    name: str | None = None
    schema_ref: str | None = None
    assertion_refs: list[str] = field(default_factory=list)
    passes: dict[str, dict[str, Any]] = field(default_factory=dict)
```

A profile bundles a schema reference, a list of assertion file references, and a
mapping of pass names to their configuration dicts. This lets users define a
reusable compression configuration for a specific platform or team.

### Loader

`profiles/loader.py` provides `load_profile(path) -> Profile`. It validates that
the YAML file is a mapping with optional keys `name`, `schema`, `assertions`
(list of file refs), and `passes` (mapping of pass name to config or null).

### Resolver

`profiles/resolver.py` provides `resolve_profile(name_or_path) -> Path`. Same logic
as the schema resolver -- short names map to bundled profiles, paths are returned
as-is. Currently one bundled profile: `docker-compose`.

### Path Resolution

Schema and assertion refs in a profile are resolved relative to the profile file's
parent directory. This allows bundled profiles to reference bundled schemas and
assertions using relative paths.

## Format Handling

Defined in `src/decoct/formats.py`.

### Format Detection

`detect_format(path) -> str` uses file extension:
- `.json` returns `"json"`
- `.ini`, `.conf`, `.cfg`, `.cnf`, `.properties` return `"ini"`
- Everything else returns `"yaml"`

### Platform Detection

`detect_platform(doc) -> str | None` inspects document structure to identify the
platform. Checks are ordered most-specific-first:

| Platform           | Heuristic                                                      |
|--------------------|----------------------------------------------------------------|
| `ansible-playbook` | List of dicts with `hosts` + `tasks`/`roles`                  |
| `docker-compose`   | `services` key containing a dict                               |
| `terraform-state`  | `terraform_version` + `resources` keys                         |
| `cloud-init`       | Two or more cloud-init keys (`packages`, `runcmd`, etc.)       |
| `kubernetes`       | `apiVersion` + `kind` keys                                     |
| `github-actions`   | `on` + `jobs` keys                                             |
| `traefik`          | `entryPoints` or `providers` + (`api` or `log`)                |
| `prometheus`       | `scrape_configs` key                                           |

### Converters

- `json_to_commented_map(data)` -- recursively converts `dict` to `CommentedMap` and
  `list` to `CommentedSeq`. Scalars pass through unchanged.
- `ini_to_commented_map(text)` -- parses INI text. Sectioned files (with `[section]`
  headers) produce nested `CommentedMap`; flat key=value files produce a flat
  `CommentedMap`. Values are coerced to native types (bool, int, float) where possible.

### Loading

`load_input(path) -> (doc, raw_text)` auto-detects format and returns the normalised
document alongside the original text (needed for token counting).

## Token Counting

Defined in `src/decoct/tokens.py`.

```python
def count_tokens(text: str, encoding: str = "cl100k_base") -> int
```

Wraps tiktoken. Default encoding is `cl100k_base` (GPT-4); `o200k_base` is
configurable via `--encoding` on the CLI.

```python
@dataclass
class TokenReport:
    input_tokens: int
    output_tokens: int

    @property
    def savings_tokens(self) -> int   # input - output
    @property
    def savings_pct(self) -> float    # percentage saved
```

- `create_report(input_text, output_text, encoding)` -- builds a `TokenReport`.
- `format_report(report)` -- formats for CLI display:
  `Tokens: 1234 -> 567 (saved 667, 54.1%)`.

Multi-file runs accumulate totals and print an aggregate line.

## LLM Integration

Defined in `src/decoct/learn.py`. This module is optional -- it requires the
`anthropic` SDK which is only installed via `pip install decoct[llm]`.

### Public API

- `learn_schema(examples, docs, platform, model)` -- sends example configs and/or
  documentation to Claude and receives a schema YAML string.
- `learn_assertions(standards, examples, corpus, platform, model)` -- sends standards
  docs, example configs, or a corpus of configs to Claude and receives an assertions
  YAML string.
- `merge_schemas(existing_path, new_yaml)` -- merges a newly learned schema into an
  existing schema file.
- `merge_assertions(existing_path, new_yaml)` -- merges newly learned assertions into
  an existing assertions file.

### Safety

- The `anthropic` module is never imported at the top level -- it is imported inside
  function bodies so that `import decoct` works without the LLM extra installed.
- `strip-secrets` always runs before any LLM contact in the pipeline. The learn
  commands operate on separate input files, not on pipeline output.

### CLI Commands

- `decoct schema learn` -- derive a schema from examples/docs.
- `decoct assertion learn` -- derive assertions from standards/examples/corpus.

Both commands accept `--output` to write to a file and `--merge` to merge into an
existing file. The default model is `claude-sonnet-4-20250514`.

## Key Design Decisions

1. **ruamel.yaml round-trip everywhere.** All document processing uses `CommentedMap`
   and `CommentedSeq` so that YAML comments, key ordering, and formatting are
   preserved through the pipeline. This is essential for the annotation passes that
   insert inline comments. Plain `dict` is never used for YAML processing.

2. **Dataclasses over Pydantic.** Core data models (`Schema`, `Assertion`, `Match`,
   `Profile`, `PassResult`, `TokenReport`, `PipelineStats`) are all plain dataclasses.
   This keeps the dependency footprint minimal -- Pydantic would only be justified if
   complex validation or serialisation were needed.

3. **strip-secrets ordering guarantee.** `StripSecretsPass` has no `run_after`
   constraints, ensuring it is always eligible to run first. The default pipeline in
   `cli.py` always adds it as the first pass. This is the security boundary -- secrets
   are redacted before any other processing or LLM contact.

4. **Optional LLM dependency.** `pip install decoct` gives the full deterministic
   pipeline. `pip install decoct[llm]` adds the `anthropic` SDK for schema/assertion
   learning. The `anthropic` import is deferred to function bodies so the base package
   never fails to import.

5. **Topological sort for pass ordering.** Rather than hard-coding a fixed pass order,
   each pass declares its constraints (`run_after`, `run_before`) and the pipeline
   sorts them using Kahn's algorithm. This makes the system extensible -- new passes
   can be added with ordering constraints without modifying existing passes. Cycles are
   detected and reported with the involved pass names.

6. **CommentedMap everywhere, never plain dict.** Input formats (JSON, INI) are
   converted to `CommentedMap`/`CommentedSeq` immediately after parsing. Every pass
   operates on these types. This invariant means passes never need to check whether
   they are working with a plain dict or a round-trip type.
