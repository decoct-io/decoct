# decoct Python API Reference

Complete API reference for the `decoct` library. All public classes, functions, and their signatures are documented below, grouped by module area.

---

## Core

### `decoct.pipeline`

Pipeline builder and runner.

#### `PipelineStats`

```python
@dataclass
class PipelineStats:
    pass_results: list[PassResult] = field(default_factory=list)
    pass_timings: dict[str, float] = field(default_factory=dict)
    total_time: float = 0.0
```

Collected statistics from a pipeline run. Accumulates per-pass results, per-pass timing, and overall wall-clock time.

#### `Pipeline`

```python
class Pipeline:
    def __init__(self, passes: list[BasePass]) -> None: ...

    @property
    def pass_names(self) -> list[str]: ...

    def run(self, doc: Any, **kwargs: Any) -> PipelineStats: ...
```

Ordered sequence of passes to execute on a document. The constructor sorts passes topologically using `run_after` / `run_before` constraints (Kahn's algorithm). Raises `ValueError` on cycles.

- **`pass_names`** -- Ordered pass names after topological sort.
- **`run`** -- Execute all passes in order on the document. The document is modified in-place. Returns collected statistics.

#### `_topological_sort`

```python
def _topological_sort(passes: list[BasePass]) -> list[BasePass]: ...
```

Sort passes respecting `run_after` and `run_before` constraints. Raises `ValueError` on cycles or unsatisfiable constraints.

---

### `decoct.tokens`

Token counting and statistics.

#### `count_tokens`

```python
def count_tokens(text: str, encoding: str = "cl100k_base") -> int: ...
```

Count tokens in a string using the specified tiktoken encoding.

#### `TokenReport`

```python
@dataclass
class TokenReport:
    input_tokens: int
    output_tokens: int

    @property
    def savings_tokens(self) -> int: ...

    @property
    def savings_pct(self) -> float: ...
```

Token usage statistics comparing input and output.

- **`savings_tokens`** -- Tokens saved by compression (`input_tokens - output_tokens`).
- **`savings_pct`** -- Percentage of tokens saved. Returns `0.0` when `input_tokens` is zero.

#### `create_report`

```python
def create_report(input_text: str, output_text: str, encoding: str = "cl100k_base") -> TokenReport: ...
```

Create a token report comparing input and output text.

#### `format_report`

```python
def format_report(report: TokenReport) -> str: ...
```

Format a token report for CLI display. Output example: `Tokens: 500 -> 250 (saved 250, 50.0%)`.

---

### `decoct.formats`

Input format detection and conversion.

#### `detect_format`

```python
def detect_format(path: Path) -> str: ...
```

Detect input format from file extension. Returns `"json"` for `.json` files, `"ini"` for INI/config files (`.ini`, `.conf`, `.cfg`, `.cnf`, `.properties`), and `"yaml"` for everything else.

#### `json_to_commented_map`

```python
def json_to_commented_map(data: Any) -> Any: ...
```

Recursively convert JSON-parsed data to ruamel.yaml round-trip types. `dict` becomes `CommentedMap`, `list` becomes `CommentedSeq`, scalars pass through.

#### `ini_to_commented_map`

```python
def ini_to_commented_map(text: str) -> CommentedMap: ...
```

Convert INI or flat key=value text to a `CommentedMap`. Sectioned INI files produce a nested `CommentedMap` (section to keys). Flat key=value files (no sections) produce a flat `CommentedMap`.

#### `detect_platform`

```python
def detect_platform(doc: Any) -> str | None: ...
```

Detect the platform from document content. Returns a bundled schema name (e.g., `"docker-compose"`, `"kubernetes"`, `"github-actions"`, `"terraform-state"`, `"cloud-init"`, `"ansible-playbook"`, `"traefik"`, `"prometheus"`) or `None` if unrecognised.

#### `load_input`

```python
def load_input(path: Path) -> tuple[Any, str]: ...
```

Load an input file, auto-detecting format. Returns `(document, raw_text)` tuple. JSON files are converted to `CommentedMap`/`CommentedSeq` for pipeline compatibility. INI files are converted to `CommentedMap`.

#### Private helpers

```python
def _coerce_ini_value(value: str) -> Any: ...
def _has_sections(text: str) -> bool: ...
def _parse_sectioned_ini(text: str) -> CommentedMap: ...
def _parse_flat_keyvalue(text: str) -> CommentedMap: ...
```

- **`_coerce_ini_value`** -- Coerce an INI string value to a native Python type. Detects booleans (`true`/`false`/`yes`/`no`/`on`/`off`), integers, and floats. Leaves everything else as a string.
- **`_has_sections`** -- Return `True` if the text contains INI-style `[section]` headers.
- **`_parse_sectioned_ini`** -- Parse standard INI with `[section]` headers using `configparser`.
- **`_parse_flat_keyvalue`** -- Parse flat key=value format (no sections). Skips comments and blank lines.

---

## Schemas

### `decoct.schemas.models`

Schema data model.

#### `Confidence`

```python
Confidence = Literal["authoritative", "high", "medium", "low"]
```

Type alias for schema confidence levels.

#### `Schema`

```python
@dataclass
class Schema:
    platform: str
    source: str
    confidence: Confidence
    defaults: dict[str, Any] = field(default_factory=dict)
    drop_patterns: list[str] = field(default_factory=list)
    system_managed: list[str] = field(default_factory=list)
```

Platform schema defining defaults and system-managed fields.

- **`platform`** -- Platform identifier (e.g., `"docker-compose"`, `"kubernetes"`).
- **`source`** -- Where the defaults were derived from (e.g., `"Docker Compose v2 specification"`).
- **`confidence`** -- How authoritative the defaults are.
- **`defaults`** -- Mapping of dotted path patterns to their default values.
- **`drop_patterns`** -- Path patterns for fields that should always be removed.
- **`system_managed`** -- Path patterns for system-generated fields.

---

### `decoct.schemas.loader`

Schema file loader.

#### `load_schema`

```python
def load_schema(path: str | Path) -> Schema: ...
```

Load and validate a schema YAML file. Requires `platform`, `source`, and `confidence` fields. Raises `ValueError` if the file is malformed or missing required fields.

---

### `decoct.schemas.resolver`

Schema name resolution -- bundled schema lookup.

#### `BUNDLED_SCHEMAS`

```python
BUNDLED_SCHEMAS: dict[str, str]
```

Mapping of short names to bundled schema filenames. Available short names: `ansible-playbook`, `argocd`, `aws-cloudformation`, `azure-arm`, `cloud-init`, `docker-compose`, `entra-id`, `fluent-bit`, `gcp-resources`, `github-actions`, `gitlab-ci`, `grafana`, `intune`, `kafka`, `keycloak`, `kubernetes`, `mariadb-mysql`, `mongodb`, `opentelemetry-collector`, `postgresql`, `prometheus`, `redis`, `sshd-config`, `terraform-state`, `traefik`.

#### `resolve_schema`

```python
def resolve_schema(name_or_path: str) -> Path: ...
```

Resolve a schema name or path to a file path. If `name_or_path` matches a bundled schema short name, returns the path to the bundled schema file. Otherwise returns the input as a `Path`. Raises `KeyError` if the name looks like a short name (no path separators, no file extension) but does not match any bundled schema.

---

## Assertions

### `decoct.assertions.models`

Assertion data models.

#### `Severity`

```python
Severity = Literal["must", "should", "may"]
```

Type alias for assertion severity levels.

#### `Match`

```python
@dataclass
class Match:
    path: str
    value: Any = None
    pattern: str | None = None
    range: list[float | int] | None = None
    contains: Any = None
    not_value: Any = None
    exists: bool | None = None
```

Match condition for an assertion. Exactly one condition type should be used per match:

- **`value`** -- Exact value match.
- **`pattern`** -- Regex pattern match.
- **`range`** -- Numeric range `[min, max]`.
- **`contains`** -- Value must appear in a list.
- **`not_value`** -- Value must NOT equal this.
- **`exists`** -- Field must be present (`True`) or absent (`False`).

#### `Assertion`

```python
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

A design standard assertion. The `assert_` field maps to the `assert` key in YAML files (renamed to avoid Python keyword collision). Assertions without `match` are LLM context only, not machine-evaluated.

---

### `decoct.assertions.loader`

Assertion file loader.

#### `load_assertions`

```python
def load_assertions(path: str | Path) -> list[Assertion]: ...
```

Load and validate an assertions YAML file. The file must contain an `assertions` key with a list of assertion mappings. Raises `ValueError` on malformed input or missing required fields.

#### Private helpers

```python
def _parse_match(data: dict[str, Any]) -> Match: ...
def _parse_assertion(data: dict[str, Any], index: int) -> Assertion: ...
```

- **`_parse_match`** -- Parse a match dict into a `Match` object. Validates `path` (required), `range` (must be `[min, max]`), and `exists` (must be boolean).
- **`_parse_assertion`** -- Parse a single assertion dict. Requires `id`, `assert`, `rationale`, `severity`.

---

### `decoct.assertions.matcher`

Assertion match evaluator.

#### `evaluate_match`

```python
def evaluate_match(match: Match, value: Any) -> bool: ...
```

Evaluate whether a value satisfies a match condition. Returns `True` if the value is conformant (matches the assertion). For `exists` matches, the sentinel `_SENTINEL` signals an absent key.

#### `find_matches`

```python
def find_matches(
    node: Any,
    path: str,
    assertion: Assertion,
) -> list[tuple[str, Any, Any, str]]: ...
```

Find all `(path, value, parent_node, key)` tuples matching an assertion's path pattern. For `exists` assertions the path pattern is split: the prefix (all segments except the last) locates parent nodes, and the final segment is the key whose presence is tested. Absent keys are represented with the `_SENTINEL` value.

#### Private helpers

```python
_SENTINEL: object

def _values_equal(actual: Any, expected: Any) -> bool: ...

def _find_exists_matches(
    node: Any,
    path: str,
    pattern: str,
) -> list[tuple[str, Any, Any, str]]: ...

def _walk_for_matches(
    node: Any,
    current_path: str,
    pattern: str,
    results: list[tuple[str, Any, Any, str]],
) -> None: ...
```

- **`_SENTINEL`** -- Sentinel object representing an absent key.
- **`_values_equal`** -- Compare values with type coercion for YAML types.
- **`_find_exists_matches`** -- Find matches for exists assertions by splitting the pattern into parent and leaf.
- **`_walk_for_matches`** -- Walk tree collecting `(path, value, parent, key)` for paths matching a pattern.

---

## Profiles

### `decoct.profiles.loader`

Profile data model and loader.

#### `Profile`

```python
@dataclass
class Profile:
    name: str | None = None
    schema_ref: str | None = None
    assertion_refs: list[str] = field(default_factory=list)
    passes: dict[str, dict[str, Any]] = field(default_factory=dict)
```

Named bundle of schema ref, assertion refs, and pass configuration. The `schema_ref` maps to the `schema` key in YAML files. The `assertion_refs` maps to the `assertions` key. The `passes` mapping contains pass name to configuration dict entries.

#### `load_profile`

```python
def load_profile(path: str | Path) -> Profile: ...
```

Load and validate a profile YAML file. Raises `ValueError` if the file is not a YAML mapping or if `passes` or `assertions` have invalid types.

---

### `decoct.profiles.resolver`

Profile name resolution -- bundled profile lookup.

#### `BUNDLED_PROFILES`

```python
BUNDLED_PROFILES: dict[str, str]
```

Mapping of short names to bundled profile filenames. Currently available: `docker-compose`.

#### `resolve_profile`

```python
def resolve_profile(name_or_path: str) -> Path: ...
```

Resolve a profile name or path to a file path. If `name_or_path` matches a bundled profile short name, returns the path to the bundled profile file. Otherwise returns the input as a `Path`. Raises `KeyError` if the name looks like a short name but does not match any bundled profile.

---

## Passes

### `decoct.passes.base`

Pass base class and registry.

#### `PassResult`

```python
@dataclass
class PassResult:
    name: str
    items_removed: int = 0
    details: list[str] = field(default_factory=list)
```

Result from a single pass execution.

#### `BasePass`

```python
class BasePass:
    name: str = ""
    run_after: list[str] = []
    run_before: list[str] = []

    def run(self, doc: Any, **kwargs: Any) -> PassResult: ...
```

Base class for all compression passes. Subclasses must implement `run` and set `name`. Ordering is declared via class-level `run_after` and `run_before`.

#### `register_pass`

```python
def register_pass(cls: type[BasePass]) -> type[BasePass]: ...
```

Decorator to register a pass class by its name. Raises `ValueError` if the class has no `name` attribute set.

#### `get_pass`

```python
def get_pass(name: str) -> type[BasePass]: ...
```

Look up a registered pass class by name. Raises `KeyError` if the name is not registered.

#### `list_passes`

```python
def list_passes() -> list[str]: ...
```

Return sorted list of registered pass names.

#### `clear_registry`

```python
def clear_registry() -> None: ...
```

Clear the pass registry. For testing only.

---

### `decoct.passes.annotate_deviations`

Annotate values that deviate from assertions with inline YAML comments.

#### `Deviation`

```python
@dataclass
class Deviation:
    assertion_id: str
    path: str
    message: str
```

A detected deviation from an assertion.

#### `annotate_deviations`

```python
def annotate_deviations(doc: Any, assertions: list[Assertion]) -> list[Deviation]: ...
```

Annotate deviating values with inline comments. Adds `[!]` comments to the YAML document for non-conformant values. For absent keys (exists assertions), the deviation is recorded but no YAML comment is added. Returns list of deviations found.

#### `AnnotateDeviationsPass`

```python
@register_pass
class AnnotateDeviationsPass(BasePass):
    name = "annotate-deviations"
    run_after = ["strip-conformant"]
    run_before: list[str] = []

    def __init__(self, assertions: list[Assertion] | None = None) -> None: ...
    def run(self, doc: Any, **kwargs: Any) -> PassResult: ...
```

Annotate values that deviate from assertions with comments. Accepts assertions via constructor or `kwargs["assertions"]`.

---

### `decoct.passes.deviation_summary`

Add a summary comment block at document start listing all deviations.

#### `deviation_summary`

```python
def deviation_summary(doc: Any, assertions: list[Assertion]) -> list[str]: ...
```

Collect all deviations and add a summary comment block at document start. Returns list of summary lines. Only adds comments if the document is a `CommentedMap`.

#### `DeviationSummaryPass`

```python
@register_pass
class DeviationSummaryPass(BasePass):
    name = "deviation-summary"
    run_after = ["annotate-deviations"]
    run_before: list[str] = []

    def __init__(self, assertions: list[Assertion] | None = None) -> None: ...
    def run(self, doc: Any, **kwargs: Any) -> PassResult: ...
```

Add deviation summary comment block at document start. Accepts assertions via constructor or `kwargs["assertions"]`.

---

### `decoct.passes.drop_fields`

Prune paths matching glob patterns.

#### `_path_matches`

```python
def _path_matches(path: str, pattern: str) -> bool: ...
```

Check if a dotted path matches a glob pattern. Supports `*` (single path segment) and `**` (any number of segments, including zero).

#### `drop_fields`

```python
def drop_fields(doc: Any, patterns: list[str]) -> int: ...
```

Drop fields matching glob patterns from a YAML document in-place. Returns count of fields removed.

#### `DropFieldsPass`

```python
@register_pass
class DropFieldsPass(BasePass):
    name = "drop-fields"
    run_after: list[str] = []
    run_before: list[str] = []

    def __init__(self, patterns: list[str] | None = None) -> None: ...
    def run(self, doc: Any, **kwargs: Any) -> PassResult: ...
```

Remove fields matching glob patterns. Accepts patterns via constructor or `kwargs["drop_patterns"]`.

#### Private helpers

```python
def _match_parts(path: list[str], pi: int, pattern: list[str], qi: int) -> bool: ...
def _walk_and_drop(node: Any, path: str, patterns: list[str]) -> int: ...
```

- **`_match_parts`** -- Recursive path segment matcher supporting `*` and `**`.
- **`_walk_and_drop`** -- Walk a YAML tree, dropping nodes whose paths match any pattern. Returns count removed.

---

### `decoct.passes.emit_classes`

Add default class definitions as header comments. After `strip-defaults` removes known platform defaults, this pass adds a comment block listing what was stripped, grouped by category, enabling LLMs to reconstruct full configs.

#### `emit_classes`

```python
def emit_classes(doc: Any, schema: Schema) -> int: ...
```

Add default class definitions as header comments on the document. Returns the number of classes emitted. Only operates on `CommentedMap` documents with non-empty schema defaults.

#### `EmitClassesPass`

```python
@register_pass
class EmitClassesPass(BasePass):
    name = "emit-classes"
    run_after = ["strip-defaults", "prune-empty"]
    run_before = ["annotate-deviations", "deviation-summary"]

    def __init__(self, schema: Schema | None = None) -> None: ...
    def run(self, doc: Any, **kwargs: Any) -> PassResult: ...
```

Add default class definitions as document header comments. Accepts schema via constructor or `kwargs["schema"]`.

#### Private helpers

```python
def _classify_defaults(defaults: dict[str, Any]) -> dict[str, dict[str, Any]]: ...
def _derive_class_name(parts: list[str]) -> str: ...
def _format_class_block(platform: str, classes: dict[str, dict[str, Any]]) -> str: ...
```

- **`_classify_defaults`** -- Group schema defaults into named classes by path prefix. Returns mapping of `class_name` to `{path: default_value}`.
- **`_derive_class_name`** -- Derive a human-readable class name from path segments. Groups by first meaningful segment after stripping wildcards.
- **`_format_class_block`** -- Format the class definition comment block. Lines prefixed with `@class`.

---

### `decoct.passes.keep_fields`

Retain only paths matching patterns, prune everything else.

#### `keep_fields`

```python
def keep_fields(doc: Any, patterns: list[str]) -> int: ...
```

Keep only fields matching patterns, prune everything else. Returns count of fields removed. Ancestor and descendant paths of matched nodes are preserved.

#### `KeepFieldsPass`

```python
@register_pass
class KeepFieldsPass(BasePass):
    name = "keep-fields"
    run_after: list[str] = []
    run_before: list[str] = []

    def __init__(self, patterns: list[str] | None = None) -> None: ...
    def run(self, doc: Any, **kwargs: Any) -> PassResult: ...
```

Retain only fields matching patterns, drop everything else. Accepts patterns via constructor or `kwargs["keep_patterns"]`.

#### Private helpers

```python
def _collect_keep_paths(node: Any, path: str, patterns: list[str], keep: set[str]) -> None: ...
def _strip_list_indices(path: str) -> str: ...
def _mark_ancestors(path: str, keep: set[str]) -> None: ...
def _mark_descendants(node: Any, path: str, keep: set[str]) -> None: ...
def _prune(node: Any, path: str, keep: set[str]) -> int: ...
```

- **`_collect_keep_paths`** -- Collect all paths (and their ancestors) that match keep patterns.
- **`_strip_list_indices`** -- Remove `[N]` list index notation from a path.
- **`_mark_ancestors`** -- Mark a path and all its ancestor paths.
- **`_mark_descendants`** -- Mark all descendant paths of a node.
- **`_prune`** -- Remove all paths not in the keep set. Returns count removed.

---

### `decoct.passes.prune_empty`

Remove empty dicts and lists left after other passes.

#### `prune_empty`

```python
def prune_empty(node: Any) -> int: ...
```

Recursively remove empty dict/list values from a YAML tree. Returns count of pruned nodes. Recurses depth-first, then prunes newly-empty containers.

#### `PruneEmptyPass`

```python
@register_pass
class PruneEmptyPass(BasePass):
    name = "prune-empty"
    run_after = ["strip-defaults", "strip-conformant", "drop-fields", "keep-fields"]
    run_before: list[str] = []

    def run(self, doc: Any, **kwargs: Any) -> PassResult: ...
```

Remove empty dicts and lists left by other passes.

---

### `decoct.passes.strip_comments`

Remove all YAML comments.

#### `StripCommentsPass`

```python
@register_pass
class StripCommentsPass(BasePass):
    name = "strip-comments"
    run_after: list[str] = []
    run_before: list[str] = []

    def run(self, doc: Any, **kwargs: Any) -> PassResult: ...
```

Remove all comments from a YAML document.

#### Private helpers

```python
def _strip_comments(node: Any) -> int: ...
def _count_comments(comment: Any) -> int: ...
def _count_comment_attribs(ca: Any) -> int: ...
```

- **`_strip_comments`** -- Recursively remove all comments from a ruamel.yaml node. Handles both `CommentedMap` and `CommentedSeq`. Returns count removed.
- **`_count_comments`** -- Count `CommentToken` instances in a comment attribute.
- **`_count_comment_attribs`** -- Count comments in a `CommentAttrib` object.

---

### `decoct.passes.strip_conformant`

Remove values conforming to must-severity assertions.

#### `strip_conformant`

```python
def strip_conformant(doc: Any, assertions: list[Assertion]) -> int: ...
```

Strip conformant values for `must` assertions with match conditions. Returns count of fields removed. Skips `exists` assertions (nothing to strip for presence/absence checks).

#### `StripConformantPass`

```python
@register_pass
class StripConformantPass(BasePass):
    name = "strip-conformant"
    run_after = ["strip-defaults"]
    run_before: list[str] = []

    def __init__(self, assertions: list[Assertion] | None = None) -> None: ...
    def run(self, doc: Any, **kwargs: Any) -> PassResult: ...
```

Remove values that conform to must-severity assertions. Accepts assertions via constructor or `kwargs["assertions"]`.

---

### `decoct.passes.strip_defaults`

Remove values matching platform schema defaults.

#### `strip_defaults`

```python
def strip_defaults(doc: Any, schema: Schema, *, skip_low_confidence: bool = False) -> int: ...
```

Strip default values from a YAML document using a schema. Also applies the schema's `drop_patterns` and `system_managed` lists. Returns total count of fields removed.

- **`doc`** -- YAML document to modify in-place.
- **`schema`** -- Loaded schema with defaults, drop_patterns, system_managed.
- **`skip_low_confidence`** -- If `True`, skip stripping when schema confidence is `"low"` or `"medium"`.

#### `StripDefaultsPass`

```python
@register_pass
class StripDefaultsPass(BasePass):
    name = "strip-defaults"
    run_after = ["strip-secrets", "strip-comments"]
    run_before: list[str] = []

    def __init__(self, schema: Schema | None = None, *, skip_low_confidence: bool = False) -> None: ...
    def run(self, doc: Any, **kwargs: Any) -> PassResult: ...
```

Remove values matching platform schema defaults. Accepts schema via constructor or `kwargs["schema"]`.

#### Private helpers

```python
def _walk_and_strip_defaults(node: Any, path: str, defaults: dict[str, Any]) -> int: ...
def _values_equal(actual: Any, default: Any) -> bool: ...
```

- **`_walk_and_strip_defaults`** -- Walk a YAML tree, removing leaves that match schema defaults. Returns count removed.
- **`_values_equal`** -- Compare values, handling type coercion between YAML types.

---

### `decoct.passes.strip_secrets`

Redact secrets from YAML documents. This pass MUST run before any LLM contact. Audit entries record `(path, method)` only -- actual secret values are never logged.

#### `REDACTED`

```python
REDACTED: str = "[REDACTED]"
```

Sentinel replacement value for redacted secrets.

#### `DEFAULT_SECRET_PATHS`

```python
DEFAULT_SECRET_PATHS: list[str] = [
    "*.password",
    "*.secret",
    "*.secrets",
    "*.secrets.*",
    "*.credentials",
    "*.credentials.*",
    "*.private_key",
    "*.api_key",
    "*.connection_string",
    "*.env.*",
]
```

Default path patterns that always indicate secrets.

#### `AuditEntry`

```python
@dataclass
class AuditEntry:
    path: str
    detection_method: str
```

Record of a redacted value. Never stores the actual secret.

#### `shannon_entropy`

```python
def shannon_entropy(s: str) -> float: ...
```

Calculate Shannon entropy of a string. Returns `0.0` for empty strings.

#### `strip_secrets`

```python
def strip_secrets(
    doc: Any,
    *,
    secret_paths: list[str] | None = None,
    entropy_threshold: float = 4.5,
    min_entropy_length: int = 16,
) -> list[AuditEntry]: ...
```

Strip secrets from a YAML document in-place. Returns audit log of redacted entries (path + method, never values).

- **`doc`** -- ruamel.yaml `CommentedMap` (or dict) to process.
- **`secret_paths`** -- Path patterns that always indicate secrets. Defaults to `DEFAULT_SECRET_PATHS`.
- **`entropy_threshold`** -- Shannon entropy threshold for detection.
- **`min_entropy_length`** -- Minimum string length for entropy check.

#### `StripSecretsPass`

```python
@register_pass
class StripSecretsPass(BasePass):
    name = "strip-secrets"
    run_after: list[str] = []
    run_before: list[str] = []

    def __init__(
        self,
        *,
        secret_paths: list[str] | None = None,
        entropy_threshold: float = 4.5,
        min_entropy_length: int = 16,
    ) -> None: ...

    def run(self, doc: Any, **kwargs: Any) -> PassResult: ...
```

Redact secrets from YAML documents. Must run first in every pipeline.

#### Private helpers

```python
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]]
_ENTROPY_EXEMPT_PATHS: list[str]

def _path_matches_secret(path: str, patterns: list[str]) -> bool: ...
def _check_regex(value: str) -> str | None: ...
def _is_entropy_exempt(path: str) -> bool: ...
def _detect_secret(
    value: str,
    path: str,
    secret_paths: list[str],
    entropy_threshold: float,
    min_entropy_length: int,
) -> str | None: ...
def _walk_and_redact(
    node: Any,
    path: str,
    audit: list[AuditEntry],
    secret_paths: list[str],
    entropy_threshold: float,
    min_entropy_length: int,
) -> None: ...
```

- **`_SECRET_PATTERNS`** -- Compiled regex patterns for known secret formats: AWS access keys, Azure connection strings, private key blocks, bearer tokens, GitHub tokens, generic credential pairs.
- **`_ENTROPY_EXEMPT_PATHS`** -- Paths exempt from entropy-based detection (e.g., healthcheck commands, entrypoints).
- **`_path_matches_secret`** -- Check if a dotted path matches any secret path pattern.
- **`_check_regex`** -- Check value against known secret patterns. Returns pattern name or `None`.
- **`_is_entropy_exempt`** -- Check if a path is exempt from entropy-based detection.
- **`_detect_secret`** -- Detect if a value is a secret. Returns detection method string or `None`.
- **`_walk_and_redact`** -- Recursively walk a YAML tree, redacting secrets in-place.

---

## Learning

### `decoct.learn`

LLM-assisted learning -- derive schemas and assertions from examples and docs. Requires the `decoct[llm]` extra (`pip install decoct[llm]`).

#### `learn_schema`

```python
def learn_schema(
    *,
    examples: list[Path] | None = None,
    docs: list[Path] | None = None,
    platform: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> str: ...
```

Derive a schema from example files and/or documentation using an LLM. Returns schema YAML string.

- **`examples`** -- Configuration file paths to analyse.
- **`docs`** -- Documentation file paths to analyse.
- **`platform`** -- Optional platform name hint.
- **`model`** -- Anthropic model to use.

Raises `ImportError` if the anthropic SDK is not installed. Raises `ValueError` if no input files are provided or schema generation fails.

#### `learn_schema_to_file`

```python
def learn_schema_to_file(
    output: Path,
    *,
    examples: list[Path] | None = None,
    docs: list[Path] | None = None,
    platform: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> Path: ...
```

Derive a schema and write it to a file. Returns the output path.

#### `merge_schemas`

```python
def merge_schemas(base: Path, additions: str) -> str: ...
```

Merge additional defaults into an existing schema. New defaults are added only if their key is not already present in the base. Also merges `system_managed` and `drop_patterns` lists (deduplicating). Returns the merged schema YAML string.

#### `learn_assertions`

```python
def learn_assertions(
    *,
    standards: list[Path] | None = None,
    examples: list[Path] | None = None,
    corpus: list[Path] | None = None,
    platform: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> str: ...
```

Derive assertions from standards documents, examples, or corpus using an LLM. Returns assertions YAML string.

- **`standards`** -- Standards/policy document paths to analyse.
- **`examples`** -- Example configuration file paths to analyse.
- **`corpus`** -- Config files for cross-file pattern analysis (mutually exclusive with `examples`).
- **`platform`** -- Optional platform name hint.
- **`model`** -- Anthropic model to use.

Raises `ImportError` if the anthropic SDK is not installed. Raises `ValueError` if no input files are provided, or if `corpus` and `examples` are both given.

#### `merge_assertions`

```python
def merge_assertions(base: Path, additions: str) -> str: ...
```

Merge additional assertions into an existing assertions file. Merges by assertion `id` -- additions with an id already in the base are skipped. Returns the merged assertions YAML string.

#### Private helpers

```python
_CORPUS_MAX_CHARS: int = 300_000

def _read_file(path: Path) -> str: ...
def _extract_yaml_block(response_text: str) -> str: ...
def _validate_schema(schema_yaml: str) -> dict[str, Any]: ...
def _validate_assertions(assertions_yaml: str) -> list[dict[str, Any]]: ...
def _prepare_corpus(files: list[Path]) -> str: ...
```

- **`_read_file`** -- Read a file and return labelled content with the filename as a markdown heading.
- **`_extract_yaml_block`** -- Extract YAML from a markdown code block or raw response.
- **`_extract_schema_yaml`** -- Backward-compatible alias for `_extract_yaml_block`.
- **`_validate_schema`** -- Parse and validate generated schema YAML. Requires `platform` and `defaults` keys.
- **`_validate_assertions`** -- Parse and validate generated assertions YAML. Requires `assertions` key containing a list of assertion dicts with `id`, `assert`, `rationale`, `severity`.
- **`_prepare_corpus`** -- Read corpus files, truncating proportionally if total exceeds 300,000 characters.
