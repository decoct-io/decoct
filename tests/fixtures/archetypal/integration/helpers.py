"""
Reconstruction helpers for decoct archetypal test fixtures.

Provides:
  - reconstruct(): rebuild Tier A from Tier B + C
  - normalize(): deep-compare helper
  - load_case(): load a test case from a set directory
"""

import copy
import os
from glob import glob

import yaml


def deep_set(d, dotpath, value):
    """Set a value in a nested dict using dot notation."""
    keys = dotpath.split(".")
    for key in keys[:-1]:
        if key not in d:
            d[key] = {}
        d = d[key]
    d[keys[-1]] = value


def deep_delete(d, dotpath):
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


_SENTINEL = object()


def deep_get(d, dotpath, default=_SENTINEL):
    """Get a value from a nested dict using dot notation."""
    keys = dotpath.split(".")
    for key in keys:
        if not isinstance(d, dict) or key not in d:
            if default is _SENTINEL:
                raise KeyError(dotpath)
            return default
        d = d[key]
    return d


def normalize(obj):
    """Normalize for comparison — sort dict keys, recurse."""
    if isinstance(obj, dict):
        return {k: normalize(v) for k, v in sorted(obj.items())}
    elif isinstance(obj, list):
        return [normalize(item) for item in obj]
    return obj


def reconstruct_section(tier_b_classes, tier_c_section):
    """
    Reconstruct original data for one section from class + overrides.

    Returns the reconstructed data. If tier_c_section has no _class,
    returns it as-is (raw passthrough).
    """
    if "_class" not in tier_c_section:
        return copy.deepcopy(tier_c_section)

    class_name = tier_c_section["_class"]
    if class_name not in tier_b_classes:
        raise ValueError(f"Class '{class_name}' not found in Tier B")

    result = copy.deepcopy(tier_b_classes[class_name])
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


def reconstruct_instances(tier_b_classes, tier_c_section):
    """Reconstruct instance list from class + per-instance overrides.

    Supports flat and dot-notation overrides/removals within instances:
      - flat override:       record[k] = v
      - dot-notation override: deep_set(record, k, v)
      - flat removal:        record.pop(field)
      - dot-notation removal: deep_delete(record, field)
    """
    class_name = tier_c_section["_class"]
    class_def = copy.deepcopy(tier_b_classes[class_name])
    class_def.pop("_identity", None)

    instances = []
    for inst in tier_c_section.get("instances", []):
        record = copy.deepcopy(class_def)
        removals = inst.get("_remove", [])
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


class TestCase:
    """Loaded test case for one set."""

    def __init__(self, set_dir):
        self.set_dir = set_dir
        self.name = os.path.basename(set_dir)

        # Load expected metadata
        with open(os.path.join(set_dir, "expected.yaml")) as f:
            self.expected = yaml.safe_load(f)

        # Load Tier B
        with open(os.path.join(set_dir, "golden", "tier_b.yaml")) as f:
            self.tier_b = yaml.safe_load(f) or {}

        # Load inputs and Tier C
        self.inputs = {}
        self.tier_c = {}
        self.hosts = []

        for path in sorted(glob(os.path.join(set_dir, "input", "rtr-*.yaml"))):
            host = os.path.basename(path).replace(".yaml", "")
            self.hosts.append(host)
            with open(path) as f:
                self.inputs[host] = yaml.safe_load(f)

        for path in sorted(glob(os.path.join(set_dir, "golden", "tier_c", "rtr-*.yaml"))):
            host = os.path.basename(path).replace(".yaml", "")
            with open(path) as f:
                self.tier_c[host] = yaml.safe_load(f)

    @property
    def positive_sections(self):
        return self.expected.get("positive_sections", [])

    @property
    def negative_sections(self):
        return self.expected.get("negative_sections", [])

    @property
    def all_sections(self):
        return self.positive_sections + self.negative_sections


def load_case(set_dir):
    """Load a test case from a set directory."""
    return TestCase(set_dir)
