"""Archetypal compression engine.

Compresses fleets of infrastructure configs into classes (Tier B)
and per-host deltas (Tier C) for LLM-readable output.
"""

from __future__ import annotations

import copy
from typing import Any


def archetypal_compress(
    inputs: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Compress fleet configs into (tier_b, tier_c).

    Args:
        inputs: {hostname: {section_name: section_data}}

    Returns:
        (tier_b, tier_c) where tier_b = {ClassName: class_def},
        tier_c = {hostname: {section_name: compressed_section}}
    """
    all_sections: set[str] = set()
    for host_data in inputs.values():
        all_sections.update(host_data.keys())

    tier_b: dict[str, Any] = {}
    tier_c: dict[str, dict[str, Any]] = {host: {} for host in inputs}

    for section in sorted(all_sections):
        hosts_data: dict[str, Any] = {}
        for host, data in inputs.items():
            if section in data:
                hosts_data[host] = data[section]

        if not hosts_data:
            continue

        if _is_list_of_dicts_section(hosts_data):
            _compress_list_section(section, hosts_data, tier_b, tier_c)
        elif all(isinstance(v, dict) for v in hosts_data.values()):
            _compress_dict_section(section, hosts_data, tier_b, tier_c)
        else:
            for host, data in hosts_data.items():
                tier_c[host][section] = copy.deepcopy(data)

    return tier_b, tier_c


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def _is_list_of_dicts_section(hosts_data: dict[str, Any]) -> bool:
    """True if every host's data is a non-empty list of dicts."""
    return all(
        isinstance(v, list) and len(v) > 0 and all(isinstance(item, dict) for item in v)
        for v in hosts_data.values()
    )


def _values_equal(a: Any, b: Any) -> bool:
    """Type-sensitive equality.  True(bool) != 1(int) != 'true'(str)."""
    return type(a) is type(b) and a == b  # noqa: E721


def _flatten(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten nested dict to ``{dotted.path: leaf}``; lists are leaves."""
    result: dict[str, Any] = {}
    for key, value in d.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and value:
            result.update(_flatten(value, path))
        else:
            result[path] = value
    return result


def _unflatten(flat: dict[str, Any]) -> dict[str, Any]:
    """Reverse of :func:`_flatten`."""
    result: dict[str, Any] = {}
    for dotpath, value in sorted(flat.items()):
        keys = dotpath.split(".")
        d = result
        for key in keys[:-1]:
            if key not in d:
                d[key] = {}
            d = d[key]
        d[keys[-1]] = value
    return result


# ---------------------------------------------------------------------------
# Grouping helpers
# ---------------------------------------------------------------------------


def _count_consistent(flat: dict[str, dict[str, Any]], hosts: list[str]) -> int:
    """Count fields with identical type+value across *all* hosts."""
    if len(hosts) < 2:
        return sum(len(flat[h]) for h in hosts)

    path_sets = [set(flat[h].keys()) for h in hosts]
    shared = path_sets[0].copy()
    for ps in path_sets[1:]:
        shared &= ps

    count = 0
    for path in shared:
        ref = flat[hosts[0]][path]
        if all(_values_equal(flat[h][path], ref) for h in hosts[1:]):
            count += 1
    return count


def _is_compressible(flat: dict[str, dict[str, Any]], hosts: list[str]) -> bool:
    if len(hosts) >= 3:
        return True
    if len(hosts) >= 2:
        return _count_consistent(flat, hosts) >= 3
    return False


def _find_groups(flat: dict[str, dict[str, Any]], hosts: list[str]) -> list[list[str]]:
    """Phase A: exact-match grouping.  Phase B: greedy merge (>= 3 consistent)."""
    sig_map: dict[tuple[tuple[str, str, str], ...], list[str]] = {}
    for host in hosts:
        sig = tuple(sorted((k, type(v).__name__, repr(v)) for k, v in flat[host].items()))
        sig_map.setdefault(sig, []).append(host)
    groups: list[list[str]] = [sorted(g) for g in sig_map.values()]

    changed = True
    while changed:
        changed = False
        best: tuple[int, int] | None = None
        best_score = -1
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                score = _count_consistent(flat, groups[i] + groups[j])
                if score >= 3 and score > best_score:
                    best = (i, j)
                    best_score = score
        if best is not None:
            i, j = best
            groups[i] = sorted(groups[i] + groups[j])
            groups.pop(j)
            changed = True

    return groups


# ---------------------------------------------------------------------------
# Identity / reference selection
# ---------------------------------------------------------------------------


def _find_identity_fields(flat: dict[str, dict[str, Any]], hosts: list[str]) -> set[str]:
    """Fields present in all hosts with all-unique values."""
    if len(hosts) < 2:
        return set()
    path_sets = [set(flat[h].keys()) for h in hosts]
    shared = path_sets[0].copy()
    for ps in path_sets[1:]:
        shared &= ps

    identity: set[str] = set()
    for path in shared:
        sigs: set[tuple[str, str]] = set()
        all_unique = True
        for h in hosts:
            sig = (type(flat[h][path]).__name__, repr(flat[h][path]))
            if sig in sigs:
                all_unique = False
                break
            sigs.add(sig)
        if all_unique:
            identity.add(path)
    return identity


def _collapse_removals(removed: set[str], class_flat: dict[str, Any]) -> list[str]:
    """Collapse leaf removals to parent when *all* children are removed."""
    if not removed:
        return []
    result = set(removed)
    changed = True
    while changed:
        changed = False
        parents: set[str] = set()
        for path in result:
            parts = path.split(".")
            for i in range(1, len(parts)):
                parents.add(".".join(parts[:i]))
        for parent in sorted(parents, key=lambda x: -len(x)):
            children_class = {p for p in class_flat if p.startswith(parent + ".")}
            if not children_class:
                continue
            children_result = {p for p in result if p.startswith(parent + ".")}
            if children_class == children_result:
                result -= children_result
                result.add(parent)
                changed = True
                break
    return sorted(result)


def _delta_cost(
    class_flat: dict[str, Any],
    host_flat: dict[str, Any],
    identity_fields: set[str],
) -> int:
    cost = len(identity_fields)
    removed = set(class_flat.keys()) - set(host_flat.keys())
    cost += len(_collapse_removals(removed, class_flat))
    for path, value in host_flat.items():
        if path in identity_fields:
            continue
        if path in class_flat:
            if not _values_equal(value, class_flat[path]):
                cost += 1
        else:
            cost += 1
    return cost


def _choose_reference(
    flat: dict[str, dict[str, Any]],
    hosts: list[str],
    identity_fields: set[str],
) -> str:
    best_host = hosts[0]
    best_cost = float("inf")
    for candidate in hosts:
        cand_flat = {k: v for k, v in flat[candidate].items() if k not in identity_fields}
        total = sum(_delta_cost(cand_flat, flat[h], identity_fields) for h in hosts)
        if total < best_cost:
            best_cost = total
            best_host = candidate
    return best_host


def _make_class_name(section: str, index: int) -> str:
    parts = section.split("_")
    name = "".join(p.capitalize() for p in parts)
    if index > 0:
        name += f"_{index}"
    return name


# ---------------------------------------------------------------------------
# Dict section compression
# ---------------------------------------------------------------------------


def _compress_dict_section(
    section: str,
    hosts_data: dict[str, Any],
    tier_b: dict[str, Any],
    tier_c: dict[str, dict[str, Any]],
) -> None:
    flat = {host: _flatten(data) for host, data in hosts_data.items()}
    hosts = sorted(flat.keys())
    groups = _find_groups(flat, hosts)

    class_idx = 0
    for group_hosts in groups:
        if not _is_compressible(flat, group_hosts):
            for host in group_hosts:
                tier_c[host][section] = copy.deepcopy(hosts_data[host])
            continue

        class_name = _make_class_name(section, class_idx)
        class_idx += 1

        identity = _find_identity_fields(flat, group_hosts)
        ref = _choose_reference(flat, group_hosts, identity)
        class_flat = {k: v for k, v in flat[ref].items() if k not in identity}
        class_def = _unflatten(class_flat)
        if identity:
            class_def["_identity"] = sorted(identity)
        tier_b[class_name] = class_def

        for host in group_hosts:
            delta: dict[str, Any] = {"_class": class_name}

            for field in sorted(identity):
                if field in flat[host]:
                    delta[field] = flat[host][field]

            removed = set(class_flat.keys()) - set(flat[host].keys())
            collapsed = _collapse_removals(removed, class_flat)
            if collapsed:
                delta["_remove"] = collapsed

            for path in sorted(flat[host].keys()):
                if path in identity:
                    continue
                if path in class_flat:
                    if not _values_equal(flat[host][path], class_flat[path]):
                        delta[path] = flat[host][path]
                else:
                    delta[path] = flat[host][path]

            tier_c[host][section] = delta


# ---------------------------------------------------------------------------
# List-of-dicts section compression
# ---------------------------------------------------------------------------


def _compress_list_section(
    section: str,
    hosts_data: dict[str, Any],
    tier_b: dict[str, Any],
    tier_c: dict[str, dict[str, Any]],
) -> None:
    all_instances: list[dict[str, Any]] = []
    for host in sorted(hosts_data):
        all_instances.extend(hosts_data[host])

    total = len(all_instances)
    if total == 0:
        for host in hosts_data:
            tier_c[host][section] = copy.deepcopy(hosts_data[host])
        return

    field_values: dict[str, list[Any]] = {}
    field_present: dict[str, int] = {}
    for inst in all_instances:
        for field, value in inst.items():
            field_values.setdefault(field, []).append(value)
            field_present[field] = field_present.get(field, 0) + 1

    # Identity: present in all, all unique
    id_fields: list[str] = []
    for field, values in field_values.items():
        if field_present.get(field, 0) < total:
            continue
        sigs: set[tuple[str, str]] = set()
        unique = True
        for v in values:
            sig = (type(v).__name__, repr(v))
            if sig in sigs:
                unique = False
                break
            sigs.add(sig)
        if unique:
            id_fields.append(field)
    id_fields.sort()

    # Class fields: majority value
    class_fields: dict[str, Any] = {}
    for field, values in field_values.items():
        if field in id_fields:
            continue
        counts: dict[tuple[str, str], tuple[Any, int]] = {}
        for v in values:
            key = (type(v).__name__, repr(v))
            if key not in counts:
                counts[key] = (v, 0)
            counts[key] = (counts[key][0], counts[key][1] + 1)
        mode_val, mode_count = max(counts.values(), key=lambda x: x[1])
        if mode_count > total * 0.5:
            class_fields[field] = mode_val

    if len(class_fields) < 3:
        for host in hosts_data:
            tier_c[host][section] = copy.deepcopy(hosts_data[host])
        return

    class_name = _make_class_name(section, 0)
    class_def: dict[str, Any] = dict(class_fields)
    if id_fields:
        class_def["_identity"] = list(id_fields)
    tier_b[class_name] = class_def

    for host in sorted(hosts_data):
        instances: list[dict[str, Any]] = []
        for inst in hosts_data[host]:
            delta: dict[str, Any] = {}
            for field in id_fields:
                if field in inst:
                    delta[field] = inst[field]
            for field, value in inst.items():
                if field in id_fields:
                    continue
                if field in class_fields:
                    if not _values_equal(value, class_fields[field]):
                        delta[field] = value
                else:
                    delta[field] = value
            removed = [f for f in class_fields if f not in inst]
            if removed:
                delta["_remove"] = sorted(removed)
            instances.append(delta)

        tier_c[host][section] = {"_class": class_name, "instances": instances}
