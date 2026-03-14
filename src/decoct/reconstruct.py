"""Reconstruction and validation for compressed output.

Rebuilds original data from tier_b (class definitions) + tier_c (per-host deltas)
and validates that reconstruction matches the original inputs exactly.
"""

from __future__ import annotations

import copy
from typing import Any

_SENTINEL = object()


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
        if not isinstance(d, dict) or key not in d:
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


def normalize(obj: Any) -> Any:
    """Normalize for comparison -- sort dict keys, recurse."""
    if isinstance(obj, dict):
        return {k: normalize(v) for k, v in sorted(obj.items())}
    elif isinstance(obj, list):
        return [normalize(item) for item in obj]
    return obj


def reconstruct_section(tier_b_classes: dict[str, Any], tier_c_section: dict[str, Any]) -> Any:
    """Reconstruct original data for one section from class + delta additions.

    Returns the reconstructed data. If tier_c_section has no _class,
    returns it as-is (raw passthrough).

    Handles embedded ``_list_class`` values in delta overrides — these are
    expanded back to the original list structure using the list class
    definitions in ``tier_b_classes['_list_classes']``.
    """
    if "_class" not in tier_c_section:
        return copy.deepcopy(tier_c_section)

    class_name = tier_c_section["_class"]
    if class_name not in tier_b_classes:
        raise ValueError(f"Class '{class_name}' not found in Tier B")

    result = copy.deepcopy(tier_b_classes[class_name])
    result.pop("_identity", None)

    # Apply overrides/additions
    for key, value in tier_c_section.items():
        if key in ("_class", "instances"):
            continue
        # Check for embedded list class structures
        if isinstance(value, dict) and "_list_class" in value:
            expanded = _reconstruct_list_class(tier_b_classes, value)
            if "." in key:
                deep_set(result, key, expanded)
            else:
                result[key] = expanded
        elif "." in key:
            deep_set(result, key, value)
        else:
            result[key] = value

    return result


def reconstruct_instances(tier_b_classes: dict[str, Any], tier_c_section: dict[str, Any]) -> list[dict[str, Any]]:
    """Reconstruct instance list from class + per-instance additions."""
    class_name = tier_c_section["_class"]
    class_def = copy.deepcopy(tier_b_classes[class_name])
    class_def.pop("_identity", None)

    instances: list[dict[str, Any]] = []
    for inst in tier_c_section.get("instances", []):
        record = copy.deepcopy(class_def)
        for k, v in inst.items():
            if "." in k:
                deep_set(record, k, v)
            else:
                record[k] = v
        instances.append(record)
    return instances


def _section_to_class_name(section: str, index: int = 0) -> str:
    """Derive a class name from a section name.

    Mirrors ``compress._make_class_name`` so reconstruction can map
    section names back to tier_b keys.
    """
    parts = section.split("_")
    name = "".join(p.capitalize() for p in parts)
    if index > 0:
        name += f"_{index}"
    return name


def reconstruct_host(tier_b: dict[str, Any], tier_c_host: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct all sections for a single host.

    Handles:
    - ``_class_instances``: list of section names that expand verbatim from tier_b
    - ``_list_class`` + ``_instances``: intra-document list class reconstruction
    - Standard ``_class`` + delta sections
    - ``instances`` list sections
    - Raw passthrough
    """
    result: dict[str, Any] = {}

    # Expand _class_instances — list of section names (class name derived)
    class_instances = tier_c_host.get("_class_instances", [])
    if isinstance(class_instances, list):
        for section_name in class_instances:
            class_name = _section_to_class_name(section_name)
            if class_name in tier_b:
                class_def = copy.deepcopy(tier_b[class_name])
                class_def.pop("_identity", None)
                result[section_name] = class_def
            else:
                result[section_name] = {}
    elif isinstance(class_instances, dict):
        # Legacy dict format: {section_name: class_name}
        for section_name, class_name in class_instances.items():
            if class_name in tier_b:
                class_def = copy.deepcopy(tier_b[class_name])
                class_def.pop("_identity", None)
                result[section_name] = class_def
            else:
                result[section_name] = {}

    for section, tc in tier_c_host.items():
        if section == "_class_instances":
            continue
        if isinstance(tc, dict) and "_list_class" in tc:
            result[section] = _reconstruct_list_class(tier_b, tc)
        elif isinstance(tc, dict) and "instances" in tc:
            result[section] = reconstruct_instances(tier_b, tc)
        elif isinstance(tc, dict) and "_class" in tc:
            result[section] = reconstruct_section(tier_b, tc)
        else:
            result[section] = tc
    return result


def _reconstruct_list_class(tier_b: dict[str, Any], tc_section: dict[str, Any]) -> list[dict[str, Any]]:
    """Reconstruct a list from _list_class + _instances + optional _also.

    The list class definition is looked up in tier_b['_list_classes'].
    """
    list_classes = tier_b.get("_list_classes", {})
    class_name = tc_section["_list_class"]
    class_def = list_classes.get(class_name, {})
    class_body = class_def.get("_body", {})
    discriminators = class_def.get("_discriminators", [])

    items: list[dict[str, Any]] = []
    raw_instances = tc_section.get("_instances", [])

    if len(discriminators) == 1 and all(not isinstance(inst, dict) for inst in raw_instances):
        # Scalar instance list: each entry is the value of the single discriminator
        disc_key = discriminators[0]
        for val in raw_instances:
            item = copy.deepcopy(class_body)
            item[disc_key] = val
            items.append(_unflatten_dict(item))
    else:
        # Dict instance list: each entry is a dict of discriminator+override values
        for inst in raw_instances:
            item = copy.deepcopy(class_body)
            if isinstance(inst, dict):
                item.update(inst)
            items.append(_unflatten_dict(item))

    # Append residuals (_also items) as-is
    for also_item in tc_section.get("_also", []):
        items.append(copy.deepcopy(also_item))

    return items


def _unflatten_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Unflatten dotted keys in a dict.  Non-dotted keys pass through."""
    has_dots = any("." in k for k in d)
    if not has_dots:
        return d
    result: dict[str, Any] = {}
    for key, value in d.items():
        if "." in key:
            deep_set(result, key, value)
        else:
            result[key] = value
    return result


def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    """Recursively merge *source* into *target*, mutating *target* in place."""
    for key, value in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value


def unflatten_collapsed(data: Any) -> Any:
    """Recursively unflatten dotted keys at every nesting level.

    This reverses the dot-notation collapse performed by
    :func:`decoct.render.collapse_single_child_dicts`.  It operates at
    every dict in the tree so that nested collapsed keys are also expanded.
    """
    if isinstance(data, list):
        return [unflatten_collapsed(item) for item in data]
    if not isinstance(data, dict):
        return data

    # Recurse into values first
    processed = {k: unflatten_collapsed(v) for k, v in data.items()}

    if not any("." in k for k in processed):
        return processed

    result: dict[str, Any] = {}
    for key, value in processed.items():
        if "." in key:
            # Build the nested structure for this dotted key
            nested: dict[str, Any] = {}
            deep_set(nested, key, value)
            _deep_merge(result, nested)
        elif key in result and isinstance(result[key], dict) and isinstance(value, dict):
            _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def validate_reconstruction(
    inputs: dict[str, dict[str, Any]],
    tier_b: dict[str, Any],
    tier_c: dict[str, dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Validate that reconstruction from tier_b + tier_c matches original inputs.

    Returns:
        (all_pass, errors) where errors is a list of mismatch descriptions.
    """
    errors: list[str] = []

    for host in sorted(inputs):
        if host not in tier_c:
            errors.append(f"{host}: missing from tier_c")
            continue

        reconstructed = reconstruct_host(tier_b, tier_c[host])
        original = inputs[host]

        if normalize(reconstructed) != normalize(original):
            all_sections = sorted(set(list(original.keys()) + list(reconstructed.keys())))
            for section in all_sections:
                orig_sec = original.get(section)
                recon_sec = reconstructed.get(section)
                if orig_sec is None:
                    errors.append(f"{host}/{section}: extra in reconstructed")
                elif recon_sec is None:
                    errors.append(f"{host}/{section}: missing from reconstructed")
                elif normalize(orig_sec) != normalize(recon_sec):
                    errors.append(f"{host}/{section}: mismatch")

    return len(errors) == 0, errors
