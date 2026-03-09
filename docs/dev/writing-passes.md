# Writing Compression Passes

A step-by-step guide for developers adding new compression passes to decoct.

Every pass in decoct is a subclass of `BasePass` that transforms a YAML document
in-place. Passes are registered by name, ordered by declared constraints, and
executed sequentially by the pipeline. This guide covers the full lifecycle: from
the base class API through testing.

---

## Pass Base Class API

All passes extend `BasePass` and are paired with a `PassResult` dataclass.
Both live in `src/decoct/passes/base.py`.

### PassResult

```python
@dataclass
class PassResult:
    """Result from a single pass execution."""

    name: str
    items_removed: int = 0
    details: list[str] = field(default_factory=list)
```

- **`name`** -- the pass name (should match the class's `name` attribute).
- **`items_removed`** -- count of nodes removed, comments stripped, etc.
- **`details`** -- free-form strings for additional diagnostics (e.g. deviation
  annotations list each assertion ID and path).

### BasePass

```python
class BasePass:
    """Base class for all compression passes."""

    name: str = ""
    run_after: list[str] = []
    run_before: list[str] = []

    def run(self, doc: Any, **kwargs: Any) -> PassResult:
        raise NotImplementedError
```

Class attributes:

| Attribute    | Type         | Purpose |
|-------------|-------------|---------|
| `name`       | `str`        | Unique identifier used for registration and ordering (e.g. `"strip-comments"`). |
| `run_after`  | `list[str]`  | Names of passes that must execute **before** this one. |
| `run_before` | `list[str]`  | Names of passes that must execute **after** this one. |

The `run()` method contract:

1. **Receives** a ruamel.yaml `CommentedMap` (or `CommentedSeq`) as `doc`, plus
   arbitrary `**kwargs` forwarded from the pipeline.
2. **Modifies `doc` in-place** -- do not return a new document.
3. **Returns** a `PassResult` with statistics about what the pass did.

---

## Pass Registration

Passes register themselves into a module-level `_registry` dict via the
`@register_pass` decorator. This happens at import time.

```python
# src/decoct/passes/base.py

_registry: dict[str, type[BasePass]] = {}


def register_pass(cls: type[BasePass]) -> type[BasePass]:
    """Decorator to register a pass class by its name."""
    if not cls.name:
        msg = f"Pass class {cls.__name__} must define a 'name' attribute"
        raise ValueError(msg)
    _registry[cls.name] = cls
    return cls


def get_pass(name: str) -> type[BasePass]:
    """Look up a registered pass class by name."""
    if name not in _registry:
        msg = f"Unknown pass '{name}'. Registered: {sorted(_registry)}"
        raise KeyError(msg)
    return _registry[name]


def list_passes() -> list[str]:
    """Return sorted list of registered pass names."""
    return sorted(_registry)
```

Usage in a pass module:

```python
from decoct.passes.base import BasePass, PassResult, register_pass

@register_pass
class StripCommentsPass(BasePass):
    name = "strip-comments"
    run_after: list[str] = []
    run_before: list[str] = []

    def run(self, doc: Any, **kwargs: Any) -> PassResult:
        ...
```

**Every pass module must be imported somewhere for registration to occur.**
In decoct, the CLI module (`src/decoct/cli.py`) imports every pass module
explicitly to trigger registration:

```python
# Import all pass modules so they register with the registry
from decoct.passes import strip_comments as _sc    # noqa: F401
from decoct.passes import strip_defaults as _sd    # noqa: F401
from decoct.passes import drop_fields as _df       # noqa: F401
# ... etc.
```

When you create a new pass, add a corresponding import line in `cli.py`.

---

## Ordering Constraints

The pipeline sorts passes using topological sort (Kahn's algorithm) before
execution.

### How ordering works

- **`run_after`**: this pass executes after the listed passes. If
  `run_after = ["strip-secrets", "strip-comments"]`, both of those will run
  before this pass.
- **`run_before`**: this pass executes before the listed passes. If
  `run_before = ["annotate-deviations"]`, this pass will always precede
  annotation.
- **Constraints only apply to passes present in the pipeline.** If a pass
  listed in `run_after` is not in the current pipeline, the constraint is
  silently ignored.
- **Cycle detection**: if the constraints form a cycle, the pipeline raises
  `ValueError` with a message identifying the involved passes.

### The strip-secrets rule

`strip-secrets` must always run first. It declares an empty `run_after` (no
dependencies) and every other pass should either explicitly or transitively
come after it. This is the security boundary -- secrets are redacted before any
other processing or LLM contact.

### Examples from the codebase

```python
# strip-comments: no ordering constraints (runs early, after strip-secrets by convention)
class StripCommentsPass(BasePass):
    name = "strip-comments"
    run_after: list[str] = []
    run_before: list[str] = []

# strip-defaults: must run after strip-secrets and strip-comments
class StripDefaultsPass(BasePass):
    name = "strip-defaults"
    run_after = ["strip-secrets", "strip-comments"]
    run_before: list[str] = []

# annotate-deviations: must run after strip-conformant
class AnnotateDeviationsPass(BasePass):
    name = "annotate-deviations"
    run_after = ["strip-conformant"]
    run_before: list[str] = []
```

### Pipeline topological sort

The sort is implemented in `src/decoct/pipeline.py`:

```python
def _topological_sort(passes: list[BasePass]) -> list[BasePass]:
    """Sort passes respecting run_after and run_before constraints.

    Raises ValueError on cycles or unsatisfiable constraints.
    """
    name_to_pass = {p.name: p for p in passes}
    names = {p.name for p in passes}

    # Build adjacency: edges[a] = {b} means a must run before b
    edges: dict[str, set[str]] = {n: set() for n in names}

    for p in passes:
        for dep in p.run_after:
            if dep in names:
                edges[dep].add(p.name)
        for before in p.run_before:
            if before in names:
                edges[p.name].add(before)

    # Kahn's algorithm
    in_degree: dict[str, int] = {n: 0 for n in names}
    for deps in edges.values():
        for d in deps:
            in_degree[d] += 1

    queue = sorted(n for n in names if in_degree[n] == 0)
    result: list[str] = []

    while queue:
        node = queue.pop(0)
        result.append(node)
        for neighbor in sorted(edges[node]):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) != len(names):
        remaining = names - set(result)
        msg = f"Cycle detected in pass ordering. Involved passes: {sorted(remaining)}"
        raise ValueError(msg)

    return [name_to_pass[n] for n in result]
```

The pipeline constructor calls `_topological_sort` automatically:

```python
class Pipeline:
    def __init__(self, passes: list[BasePass]) -> None:
        self._passes = _topological_sort(passes)
```

---

## Working with CommentedMap / CommentedSeq

All YAML documents in decoct are `CommentedMap` / `CommentedSeq` instances from
ruamel.yaml, never plain `dict` or `list`. This preserves comments, key ordering,
and document structure.

### Imports

```python
from ruamel.yaml.comments import CommentedMap, CommentedSeq
```

### Iteration

```python
# Iterate keys
for key in doc:
    ...

# Iterate key-value pairs
for key, value in doc.items():
    ...

# Iterate sequence items
for item in doc["services"]:  # if doc["services"] is a CommentedSeq
    ...
```

### Type checking

```python
if isinstance(node, CommentedMap):
    # dict-like operations
    ...
elif isinstance(node, CommentedSeq):
    # list-like operations
    ...
```

You can also use the base Python types `dict` and `list` for isinstance checks
when you do not need comment-specific behaviour -- `CommentedMap` is a subclass
of `ordereddict` and `CommentedSeq` is a subclass of `list`. The `drop_fields.py`
pass uses this approach:

```python
if isinstance(node, dict):      # matches CommentedMap too
    ...
elif isinstance(node, list):    # matches CommentedSeq too
    ...
```

### Deleting keys

Always use `del` on the container. Never reconstruct a new dict:

```python
# Correct
del doc["metadata"]

# Wrong -- breaks CommentedMap, loses comments and ordering
doc = {k: v for k, v in doc.items() if k != "metadata"}
```

---

## Path Matching Utilities

The `drop_fields.py` module provides reusable path matching functions that other
passes import (e.g. `strip_defaults.py` imports `_path_matches`).

### `_path_matches(path, pattern)`

Checks whether a dotted path string matches a glob pattern.

```python
def _path_matches(path: str, pattern: str) -> bool:
    """Check if a dotted path matches a glob pattern.

    Supports:
        ``*`` -- matches a single path segment
        ``**`` -- matches any number of segments (including zero)
    """
    path_parts = path.split(".")
    pattern_parts = pattern.split(".")
    return _match_parts(path_parts, 0, pattern_parts, 0)
```

### `_match_parts(path, pi, pattern, qi)`

Recursive segment matcher that powers `_path_matches`:

```python
def _match_parts(path: list[str], pi: int, pattern: list[str], qi: int) -> bool:
    """Recursive path segment matcher."""
    while pi < len(path) and qi < len(pattern):
        if pattern[qi] == "**":
            # ** matches zero or more segments
            if qi == len(pattern) - 1:
                return True
            for i in range(pi, len(path) + 1):
                if _match_parts(path, i, pattern, qi + 1):
                    return True
            return False
        elif fnmatch(path[pi], pattern[qi]):
            pi += 1
            qi += 1
        else:
            return False

    # Skip trailing ** patterns
    while qi < len(pattern) and pattern[qi] == "**":
        qi += 1

    return pi == len(path) and qi == len(pattern)
```

### Pattern examples

| Pattern                     | Matches                                                |
|----------------------------|-------------------------------------------------------|
| `metadata.name`             | Exactly `metadata.name`                                |
| `metadata.*`                | Any single key under `metadata`                        |
| `**.annotations`            | `annotations` at any depth                             |
| `services.*.ports`          | `ports` under any service name                         |
| `**.labels.*`               | Any key under `labels` at any nesting level            |

You can import these from `drop_fields.py` in your own pass:

```python
from decoct.passes.drop_fields import _path_matches
```

---

## Adding Comments

The `annotate_deviations.py` pass demonstrates inserting comments into the YAML
output using ruamel.yaml's comment API.

### Inline (end-of-line) comments

```python
from ruamel.yaml.comments import CommentedMap

# parent is a CommentedMap, key is the dict key to annotate
parent.yaml_add_eol_comment(" [!] standard: true", key)
```

This produces output like:

```yaml
restart: always  # [!] standard: true
```

### How annotate-deviations uses it

```python
def annotate_deviations(doc: Any, assertions: list[Assertion]) -> list[Deviation]:
    deviations: list[Deviation] = []

    for assertion in assertions:
        if assertion.match is None:
            continue

        matches = find_matches(doc, "", assertion)
        for path, value, parent, key in matches:
            if not evaluate_match(assertion.match, value):
                if value is _SENTINEL:
                    comment = f" [!] missing: {assertion.assert_}"
                elif assertion.match.value is not None:
                    comment = f" [!] standard: {assertion.match.value}"
                else:
                    comment = f" [!] assertion: {assertion.assert_}"

                # For absent keys, we can't annotate -- skip YAML comment
                if value is not _SENTINEL and isinstance(parent, CommentedMap):
                    parent.yaml_add_eol_comment(comment, key)

                deviations.append(Deviation(
                    assertion_id=assertion.id,
                    path=path,
                    message=comment.strip(),
                ))

    return deviations
```

Key points:

- Check `isinstance(parent, CommentedMap)` before calling `yaml_add_eol_comment`.
- You can only add end-of-line comments to keys that exist in the document.
- For missing/absent keys, record the deviation but skip the YAML comment.

---

## Removing Nodes Safely

Modifying a dictionary while iterating over it raises `RuntimeError`. The
standard pattern in decoct is: **collect keys to delete, then delete after
iteration**.

### The collect-then-delete pattern

From `drop_fields.py`:

```python
def _walk_and_drop(node: Any, path: str, patterns: list[str]) -> int:
    count = 0

    if isinstance(node, dict):
        keys_to_drop = []
        for key in list(node.keys()):                  # snapshot keys
            child_path = f"{path}.{key}" if path else str(key)
            if any(_path_matches(child_path, p) for p in patterns):
                keys_to_drop.append(key)
            elif isinstance(node[key], (dict, list)):
                count += _walk_and_drop(node[key], child_path, patterns)

        for key in keys_to_drop:                       # delete after iteration
            del node[key]
            count += 1

    elif isinstance(node, list):
        for i, child in enumerate(node):
            child_path = f"{path}.{i}" if path else str(i)
            if isinstance(child, (dict, list)):
                count += _walk_and_drop(child, child_path, patterns)

    return count
```

The same pattern appears in `strip_defaults.py`:

```python
keys_to_drop: list[str] = []
for key in list(node.keys()):
    child_path = f"{path}.{key}" if path else str(key)
    child = node[key]
    if not isinstance(child, (dict, list)):
        for pattern, default_value in defaults.items():
            if _path_matches(child_path, pattern) and _values_equal(child, default_value):
                keys_to_drop.append(key)
                break
    elif isinstance(child, (dict, list)):
        count += _walk_and_strip_defaults(child, child_path, defaults)

for key in keys_to_drop:
    del node[key]
    count += 1
```

Rules of thumb:

1. Call `list(node.keys())` to snapshot keys before iterating.
2. Accumulate keys to remove in a list.
3. Delete in a separate loop after the iteration completes.
4. Use `del node[key]` -- never reconstruct the container.

---

## Pass Configuration

Passes accept configuration in two ways: constructor parameters and runtime
kwargs.

### Constructor parameters

Passes that need external data (schemas, assertions, patterns) accept them
in `__init__`:

```python
class StripDefaultsPass(BasePass):
    name = "strip-defaults"
    run_after = ["strip-secrets", "strip-comments"]

    def __init__(self, schema: Schema | None = None, *, skip_low_confidence: bool = False) -> None:
        self.schema = schema
        self.skip_low_confidence = skip_low_confidence
```

```python
class DropFieldsPass(BasePass):
    name = "drop-fields"

    def __init__(self, patterns: list[str] | None = None) -> None:
        self.patterns = patterns or []
```

### Profile-based configuration

When a profile is loaded, the `passes` section maps pass names to config dicts.
The CLI unpacks these into the constructor:

```python
# From cli.py -- building passes from a profile
for pass_name, config in profile.passes.items():
    pass_cls = get_pass(pass_name)
    if pass_cls == StripDefaultsPass and schema:
        passes.append(StripDefaultsPass(schema=schema, **config))
    elif pass_cls in (StripConformantPass, AnnotateDeviationsPass, DeviationSummaryPass):
        passes.append(pass_cls(assertions=assertions, **config))
    else:
        passes.append(pass_cls(**config))
```

The `**config` unpacking means your constructor keyword arguments become the
profile's YAML keys. For example, a profile entry:

```yaml
passes:
  strip-defaults:
    skip_low_confidence: true
```

becomes `StripDefaultsPass(schema=schema, skip_low_confidence=True)`.

### Runtime kwargs fallback

Passes can also accept data through `run()`'s `**kwargs`, forwarded from the
pipeline. This is a fallback for when the constructor was not given the data:

```python
def run(self, doc: Any, **kwargs: Any) -> PassResult:
    schema = self.schema or kwargs.get("schema")
    if schema is None:
        return PassResult(name=self.name, items_removed=0)
    ...
```

---

## Testing a Pass

Every pass needs tests in `tests/test_passes/`. The project uses YAML fixtures
and a consistent helper pattern.

### Test file structure

From `tests/test_passes/test_strip_comments.py`:

```python
"""Tests for the strip-comments pass."""

from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML

from decoct.passes.strip_comments import StripCommentsPass

FIXTURES = Path(__file__).parent.parent / "fixtures" / "yaml"


def _load_yaml(path: Path) -> dict:
    yaml = YAML(typ="rt")
    return yaml.load(path)


def _dump_yaml(doc: dict) -> str:
    yaml = YAML(typ="rt")
    stream = StringIO()
    yaml.dump(doc, stream)
    return stream.getvalue()
```

### Test patterns

**1. Load fixture, run pass, verify output:**

```python
def test_removes_comments_from_fixture(self) -> None:
    doc = _load_yaml(FIXTURES / "commented.yaml")
    result = StripCommentsPass().run(doc)
    output = _dump_yaml(doc)
    assert "#" not in output
    assert result.items_removed > 0
```

**2. Verify data is preserved:**

```python
def test_preserves_data(self) -> None:
    doc = _load_yaml(FIXTURES / "commented.yaml")
    StripCommentsPass().run(doc)
    assert doc["services"]["web"]["image"] == "nginx:1.25.3"
    assert doc["services"]["web"]["restart"] == "always"
```

**3. Edge case -- empty/trivial input:**

```python
def test_no_comments_is_noop(self) -> None:
    yaml = YAML(typ="rt")
    doc = yaml.load("key: value\nnested:\n  child: 1\n")
    result = StripCommentsPass().run(doc)
    assert doc["key"] == "value"
    assert result.items_removed == 0
```

**4. Inline YAML for small cases:**

```python
def test_inline_comments_removed(self) -> None:
    yaml = YAML(typ="rt")
    doc = yaml.load("key: value  # inline comment\n")
    StripCommentsPass().run(doc)
    output = _dump_yaml(doc)
    assert "#" not in output
    assert "value" in output
```

**5. Verify the pass name:**

```python
def test_pass_name(self) -> None:
    assert StripCommentsPass.name == "strip-comments"
```

### Checklist for pass tests

1. Create input YAML fixtures in `tests/fixtures/yaml/` if needed.
2. Test the happy path with a realistic fixture.
3. Test that non-targeted data is preserved.
4. Test edge cases: empty document, missing keys, deeply nested structures.
5. Test the `PassResult` -- correct `name`, reasonable `items_removed`.
6. Test configuration variations (if the pass accepts constructor args).
7. Place test files in `tests/test_passes/` with the naming convention
   `test_<pass_module_name>.py`.

---

## Example: Building a Pass from Scratch

This walkthrough creates a hypothetical `normalize-booleans` pass that converts
YAML's alternative boolean representations (`yes`/`no`, `on`/`off`) to canonical
`true`/`false`.

### Step 1: Create the pass module

Create `src/decoct/passes/normalize_booleans.py`:

```python
"""Normalize-booleans pass -- convert yes/no/on/off to true/false."""

from __future__ import annotations

from typing import Any

from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import ScalarString

from decoct.passes.base import BasePass, PassResult, register_pass

# Mapping of non-canonical boolean strings to their canonical form.
_BOOL_MAP: dict[str, bool] = {
    "yes": True,
    "no": False,
    "on": True,
    "off": False,
    "y": True,
    "n": False,
}


def _normalize_booleans(node: Any) -> int:
    """Recursively normalize boolean-like strings to actual booleans.

    Returns count of values normalized.
    """
    count = 0

    if isinstance(node, CommentedMap):
        for key in node:
            value = node[key]
            if isinstance(value, str) and not isinstance(value, ScalarString):
                lower = value.lower()
                if lower in _BOOL_MAP:
                    node[key] = _BOOL_MAP[lower]
                    count += 1
            elif isinstance(value, (CommentedMap, CommentedSeq)):
                count += _normalize_booleans(value)

    elif isinstance(node, CommentedSeq):
        for i, item in enumerate(node):
            if isinstance(item, str) and not isinstance(item, ScalarString):
                lower = item.lower()
                if lower in _BOOL_MAP:
                    node[i] = _BOOL_MAP[lower]
                    count += 1
            elif isinstance(item, (CommentedMap, CommentedSeq)):
                count += _normalize_booleans(item)

    return count


@register_pass
class NormalizeBooleansPass(BasePass):
    """Convert yes/no/on/off string values to true/false."""

    name = "normalize-booleans"
    run_after = ["strip-secrets"]
    run_before: list[str] = []

    def run(self, doc: Any, **kwargs: Any) -> PassResult:
        count = _normalize_booleans(doc)
        return PassResult(name=self.name, items_removed=count)
```

Key decisions:

- **`run_after = ["strip-secrets"]`** -- secrets must be redacted before we touch
  any values.
- **Checks `ScalarString`** -- quoted strings (`"yes"`) should be left alone;
  only bare YAML booleans-as-strings get normalized.
- **Modifies in-place** -- assigns directly to `node[key]` or `node[i]`.
- **Returns a `PassResult`** -- `items_removed` counts normalized values (the
  field name is generic; it tracks "items changed" here).

### Step 2: Register the import in cli.py

Add to the import block in `src/decoct/cli.py`:

```python
from decoct.passes import normalize_booleans as _nb  # noqa: F401
```

### Step 3: Create the test file

Create `tests/test_passes/test_normalize_booleans.py`:

```python
"""Tests for the normalize-booleans pass."""

from io import StringIO

from ruamel.yaml import YAML

from decoct.passes.normalize_booleans import NormalizeBooleansPass


def _load(text: str):
    yaml = YAML(typ="rt")
    return yaml.load(text)


def _dump(doc) -> str:
    yaml = YAML(typ="rt")
    stream = StringIO()
    yaml.dump(doc, stream)
    return stream.getvalue()


class TestNormalizeBooleans:
    def test_converts_yes_no(self) -> None:
        doc = _load("enabled: yes\ndisabled: no\n")
        result = NormalizeBooleansPass().run(doc)
        assert doc["enabled"] is True
        assert doc["disabled"] is False
        assert result.items_removed == 2

    def test_converts_on_off(self) -> None:
        doc = _load("feature: on\nlegacy: off\n")
        NormalizeBooleansPass().run(doc)
        assert doc["feature"] is True
        assert doc["legacy"] is False

    def test_preserves_true_false(self) -> None:
        doc = _load("flag: true\nother: false\n")
        result = NormalizeBooleansPass().run(doc)
        assert doc["flag"] is True
        assert doc["other"] is False
        assert result.items_removed == 0

    def test_preserves_quoted_strings(self) -> None:
        doc = _load('answer: "yes"\n')
        result = NormalizeBooleansPass().run(doc)
        assert doc["answer"] == "yes"
        assert result.items_removed == 0

    def test_nested_maps(self) -> None:
        doc = _load("outer:\n  inner: yes\n  deep:\n    flag: off\n")
        result = NormalizeBooleansPass().run(doc)
        assert doc["outer"]["inner"] is True
        assert doc["outer"]["deep"]["flag"] is False
        assert result.items_removed == 2

    def test_sequences(self) -> None:
        doc = _load("items:\n  - yes\n  - no\n  - maybe\n")
        NormalizeBooleansPass().run(doc)
        assert doc["items"][0] is True
        assert doc["items"][1] is False
        assert doc["items"][2] == "maybe"

    def test_empty_document(self) -> None:
        doc = _load("{}\n")
        result = NormalizeBooleansPass().run(doc)
        assert result.items_removed == 0

    def test_pass_name(self) -> None:
        assert NormalizeBooleansPass.name == "normalize-booleans"
```

### Step 4: Run the tests

```bash
pytest tests/test_passes/test_normalize_booleans.py -v
```

### Step 5: Verify integration

After adding the import to `cli.py`, verify the pass registers:

```python
from decoct.passes.base import list_passes
assert "normalize-booleans" in list_passes()
```

---

## Quick Reference Checklist

When adding a new pass:

1. Create `src/decoct/passes/<your_pass>.py`.
2. Subclass `BasePass`, set `name`, `run_after`, `run_before`.
3. Decorate with `@register_pass`.
4. Implement `run(self, doc, **kwargs) -> PassResult`.
5. Modify `doc` in-place using `CommentedMap`/`CommentedSeq` operations.
6. Return a `PassResult` with meaningful statistics.
7. Add `from decoct.passes import <your_pass> as _xx  # noqa: F401` to `cli.py`.
8. Create `tests/test_passes/test_<your_pass>.py` with fixture-based tests.
9. Run `pytest --cov=decoct -v` and `ruff check src/ tests/` before submitting.
