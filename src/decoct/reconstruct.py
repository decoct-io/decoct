"""Reconstruct Tier A from Tier B + Tier C and validate round-trip fidelity."""

from __future__ import annotations

import copy
from typing import Any

_SENTINEL = object()


class ReconstructionError(Exception):
    """Raised when round-trip reconstruction does not match the original corpus."""

    def __init__(self, mismatched_hosts: list[str], stats: Any = None) -> None:
        self.mismatched_hosts = mismatched_hosts
        self.stats = stats
        hosts = ", ".join(mismatched_hosts)
        super().__init__(f"Round-trip mismatch for: {hosts}")


# ---------------------------------------------------------------------------
# Dot-notation dict helpers
# ---------------------------------------------------------------------------


def deep_set(d: dict[str, Any], dotpath: str, value: Any) -> None:
    """Set a value in a nested dict using dot notation."""
    keys = dotpath.split(".")
    for key in keys[:-1]:
        if key not in d:
            d[key] = {}
        d = d[key]
    d[keys[-1]] = value


def deep_delete(d: dict[str, Any], dotpath: str) -> bool:
    """Delete a key from a nested dict using dot notation."""
    keys = dotpath.split(".")
    for key in keys[:-1]:
        if key not in d:
            return False
        d = d[key]
    if keys[-1] in d:
        del d[keys[-1]]
        return True
    return False


def deep_get(d: dict[str, Any], dotpath: str, default: Any = _SENTINEL) -> Any:
    """Get a value from a nested dict using dot notation."""
    keys = dotpath.split(".")
    for key in keys:
        if not isinstance(d, dict) or key not in d:
            if default is _SENTINEL:
                raise KeyError(dotpath)
            return default
        d = d[key]
    return d


# ---------------------------------------------------------------------------
# Normalisation for comparison
# ---------------------------------------------------------------------------


def normalize(obj: Any) -> Any:
    """Normalize for comparison — sort dict keys, recurse."""
    if isinstance(obj, dict):
        return {k: normalize(v) for k, v in sorted(obj.items())}
    elif isinstance(obj, list):
        return [normalize(item) for item in obj]
    return obj


# ---------------------------------------------------------------------------
# Section reconstruction
# ---------------------------------------------------------------------------


def reconstruct_section(tier_b: dict[str, Any], tier_c_section: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct original data for one dict section from class + overrides.

    Returns the reconstructed data. If *tier_c_section* has no ``_class``,
    returns it as-is (raw passthrough).
    """
    if "_class" not in tier_c_section:
        return copy.deepcopy(tier_c_section)

    class_name = tier_c_section["_class"]
    if class_name not in tier_b:
        raise ValueError(f"Class '{class_name}' not found in Tier B")

    result: dict[str, Any] = copy.deepcopy(tier_b[class_name])
    result.pop("_identity", None)

    # Apply removals
    for field in tier_c_section.get("_remove", []):
        if "." in field:
            deep_delete(result, field)
        else:
            result.pop(field, None)

    # Apply overrides
    for key, value in tier_c_section.items():
        if key in ("_class", "_remove", "instances"):
            continue
        if "." in key:
            deep_set(result, key, value)
        else:
            result[key] = value

    return result


def reconstruct_instances(tier_b: dict[str, Any], tier_c_section: dict[str, Any]) -> list[dict[str, Any]]:
    """Reconstruct instance list from class + per-instance overrides."""
    class_name = tier_c_section["_class"]
    class_def: dict[str, Any] = copy.deepcopy(tier_b[class_name])
    class_def.pop("_identity", None)

    instances: list[dict[str, Any]] = []
    for inst in tier_c_section.get("instances", []):
        record: dict[str, Any] = copy.deepcopy(class_def)
        removals: list[str] = inst.get("_remove", [])
        for k, v in inst.items():
            if k == "_remove":
                continue
            if "." in k:
                deep_set(record, k, v)
            else:
                record[k] = v
        for field in removals:
            if "." in field:
                deep_delete(record, field)
            else:
                record.pop(field, None)
        instances.append(record)
    return instances


# ---------------------------------------------------------------------------
# Host-level reconstruction
# ---------------------------------------------------------------------------


def reconstruct_host(tier_b: dict[str, Any], tier_c_host: dict[str, Any]) -> dict[str, Any]:
    """Rebuild all sections for one host from tier_b + tier_c."""
    result: dict[str, Any] = {}
    for section, tc in tier_c_host.items():
        if isinstance(tc, dict) and "instances" in tc:
            result[section] = reconstruct_instances(tier_b, tc)
        elif isinstance(tc, dict) and "_class" in tc:
            result[section] = reconstruct_section(tier_b, tc)
        else:
            result[section] = tc
    return result


# ---------------------------------------------------------------------------
# Round-trip validation
# ---------------------------------------------------------------------------


def validate_round_trip(
    corpus: dict[str, dict[str, Any]],
    tier_b: dict[str, Any],
    tier_c: dict[str, dict[str, Any]],
) -> list[str]:
    """Validate that Tier B + C reconstructs to the original corpus.

    Returns a list of hostnames that did not match (empty on success).
    """
    mismatched: list[str] = []
    for host in sorted(corpus):
        if host not in tier_c:
            mismatched.append(host)
            continue
        reconstructed = reconstruct_host(tier_b, tier_c[host])
        if normalize(reconstructed) != normalize(corpus[host]):
            mismatched.append(host)
    return mismatched
