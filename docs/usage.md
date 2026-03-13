# decoct usage guide

## Installation

```bash
pip install decoct
```

For development:

```bash
git clone https://github.com/decoct-io/decoct.git
cd decoct
pip install -e ".[dev]"
```

## Basic usage

Compress a directory of infrastructure config files:

```bash
decoct compress -i <input_dir> -o <output_dir>
```

decoct reads every file in the input directory, detects the format automatically
(YAML, JSON, XML, or INI/config), runs archetypal compression, and writes:

- `<output_dir>/tier_b.yaml` — shared class definitions (the archetype)
- `<output_dir>/tier_c/<hostname>.yaml` — per-entity deltas

### Example

```bash
decoct compress -i configs/routers/ -o compressed/
```

## Output structure

### Tier B (classes)

Tier B contains the shared structure extracted across entities. Each class
captures the fields that are consistent (same type and value) across all
members of a group:

```yaml
Network:
  mask: 255.255.255.0
  gateway: 10.0.0.254
  mtu: 1500
  _identity:
  - ip
```

The `_identity` list names fields whose values are unique per entity (e.g. IP
addresses, hostnames). These are stored in each entity's Tier C delta.

### Tier C (deltas)

Each entity file in Tier C references its class and records only the
differences:

```yaml
network:
  _class: Network
  ip: 10.0.0.1          # identity field
  mtu: 9000             # override (differs from class)
dns:
  primary: 8.8.8.8      # raw passthrough (no class extracted)
  secondary: 8.8.4.4
```

Delta operations:
- **`_class`** — references the Tier B class
- **`_remove`** — list of fields present in the class but absent from this entity
- **dot-notation keys** (e.g. `nested.field`) — override a value deep in a nested structure
- **`instances`** — for list-of-dicts sections, per-item deltas against the class

### Reconstruction

decoct validates every compression run with an automatic round-trip check:
reconstruct the original input from Tier B + Tier C and compare against the
source. Any mismatch is reported per-host and the CLI exits with code 1.

## Supported formats

| Extension | Format |
|-----------|--------|
| `.yaml`, `.yml` | YAML |
| `.json` | JSON |
| `.xml` | XML |
| `.ini`, `.conf`, `.cfg`, `.cnf`, `.properties` | INI/config |

## Compression statistics

Every run prints a full statistics report covering:

- **Round-trip validation** — per-host OK/FAIL status
- **Byte compression** — input vs compressed size, ratio
- **Token compression** — tiktoken cl100k_base token counts for LLM context budgeting
- **Leaf counts** — scalar value reduction
- **Per-host breakdown** — bytes and tokens per entity
- **Per-section breakdown** — aggregated savings by config section
- **Class utilisation** — bytes, leaves, and host count per Tier B class

### Reading the output

```
========================================================================
ROUND-TRIP VALIDATION
========================================================================
  OK    pe-ald
  OK    pe-brk
  ...
16/16 hosts match
Round-trip: PASS

========================================================================
COMPRESSION STATISTICS
========================================================================

Tier A (input):  1,436,280 bytes  (16 files)
Tier B (classes):  62,552 bytes  (1 classes)
Tier C (deltas):  451,990 bytes  (16 files)
B + C combined:   514,542 bytes
Compression:        64.2%
Ratio:              2.79x

--- Token counts ---
Input tokens:      412,098
Tier B tokens:      17,886
Tier C tokens:     135,808
B + C tokens:      153,694
Token reduction:     62.7%
Token ratio:         2.68x
```

**Compression %** is the byte-level reduction: `(1 - compressed/input) * 100`.
**Token ratio** is what matters for LLM context windows: how many more entities
you can fit in the same budget.

## Initial benchmark results

Tested on a fleet of 16 IOS-XR router configurations in two source formats.

### JSON corpus (16 routers)

| Metric | Input | Compressed (B+C) | Reduction |
|--------|------:|------------------:|----------:|
| Bytes | 1,436,280 | 514,542 | 64.2% (2.79x) |
| Tokens | 412,098 | 153,694 | 62.7% (2.68x) |
| Leaves | 16,958 | 6,518 | 61.6% |

Per-host token savings:
- PE routers (pe-*): ~73.5% token reduction
- P/BNG routers (p-bas-*, p-rdg-*): ~48-53% token reduction
- Route reflectors (srr-*, trr-*): ~73.4% token reduction

### XML corpus (16 routers, same fleet)

| Metric | Input | Compressed (B+C) | Reduction |
|--------|------:|------------------:|----------:|
| Bytes | 312,005 | 116,138 | 62.8% (2.69x) |
| Tokens | 76,186 | 30,859 | 59.5% (2.47x) |
| Leaves | 5,844 | 2,408 | 58.8% |

Per-host token savings:
- PE routers (pe-*): ~70.3% token reduction
- P/BNG routers (p-bas-*, p-rdg-*): ~43-50% token reduction
- Route reflectors (srr-*, trr-*): ~70.0% token reduction

### Observations

- Compression ratios are consistent across source formats (~60-64%)
- Token reduction tracks slightly below byte reduction — tiktoken's subword
  units already compress YAML structural characters efficiently, leaving less
  overhead to eliminate
- Entities with more unique configuration (P/BNG routers with extra policy-maps,
  QoS config) compress less than simpler PE/RR roles
- Round-trip validation: **16/16 hosts PASS** for both corpora — zero
  reconstruction errors

## Python API

```python
from decoct.pipeline import run_pipeline

sources = ["configs/rtr-a.json", "configs/rtr-b.json", "configs/rtr-c.json"]
result = run_pipeline(sources, "output/")

# result keys:
#   "entities"  — number of input entities
#   "classes"   — number of Tier B classes extracted
#   "tier_b"    — the class definitions dict
#   "tier_c"    — {hostname: delta_dict}
#   "stats"     — CompressionStats dataclass

stats = result["stats"]
print(f"Token reduction: {stats.token_reduction_pct:.1f}%")
print(f"Round-trip OK: {len(stats.round_trip_ok)}/{stats.entity_count}")
```

### Reconstruction

```python
from decoct.reconstruct import reconstruct_host, validate_round_trip

# Rebuild a single host
original = reconstruct_host(tier_b, tier_c["rtr-a"])

# Validate all hosts
mismatched = validate_round_trip(corpus, tier_b, tier_c)
assert mismatched == []  # empty = all OK
```

### Statistics

```python
from decoct.stats import compute_stats, format_stats

stats = compute_stats(corpus, tier_b, tier_c)
print(format_stats(stats))
```
