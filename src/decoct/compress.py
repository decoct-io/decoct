"""Compression engine.

Compresses fleets of infrastructure configs into classes (Tier B)
and per-host deltas (Tier C) for LLM-readable output.

Algorithm per dict section:
  A — Exact-value signature grouping (truly identical hosts)
  B'— Class extraction from large groups (majority-vote)
  Fallback — Single-group extraction if no exact-match groups
  C — Nearest-class assignment for remaining hosts
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from decoct.storage import DuckDBStore

logger = logging.getLogger(__name__)


def compress(
    inputs: dict[str, dict[str, Any]],
    *,
    threshold: float = 100.0,
    max_delta_pct: float = 20.0,
    min_group_size: int = 3,
    on_host: Callable[[int, int], None] | None = None,
    on_section: Callable[[str, str], None] | None = None,
    workers: int | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Compress fleet configs into (tier_b, tier_c).

    Args:
        inputs: {hostname: {section_name: section_data}}
        threshold: Majority-vote threshold (0-100). Fields shared by >= T%
            of hosts enter the class. Default 100.0 = strict intersection.
        max_delta_pct: Maximum delta percentage (0-100) for nearest-class
            assignment.  A singleton host is assigned to a class if its
            delta fields are <= this percentage of the class field count.
        min_group_size: Minimum group size for class extraction.  Groups
            smaller than this go through Phase C nearest-class assignment.
        on_host: Optional callback ``(done, total)`` during ingestion.
        on_section: Optional callback ``(section_name, event)`` where event
            is ``"start"`` or ``"done"``.
        workers: Number of worker processes for parallel compression.
            ``None`` or ``1`` = sequential (default).

    Returns:
        (tier_b, tier_c) where tier_b = {ClassName: class_def},
        tier_c = {hostname: {section_name: compressed_section}}
    """
    from decoct.storage import DuckDBStore

    store = DuckDBStore()
    store.ingest_fleet(inputs, on_host=on_host)
    result = compress_db(
        store, all_hosts=set(inputs.keys()),
        threshold=threshold, max_delta_pct=max_delta_pct,
        min_group_size=min_group_size,
        on_section=on_section,
        workers=workers,
    )
    store.close()
    return result


def compress_db(
    store: DuckDBStore,
    all_hosts: set[str] | None = None,
    *,
    threshold: float = 100.0,
    max_delta_pct: float = 20.0,
    min_group_size: int = 3,
    on_section: Callable[[str, str], None] | None = None,
    workers: int | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Compress fleet configs from a DuckDB store into (tier_b, tier_c).

    Args:
        store: Populated DuckDBStore with ingested fleet data.
        all_hosts: Optional set of all hostnames (to ensure tier_c
            includes entries for hosts with no sections).
        threshold: Majority-vote threshold (0-100). Default 100.0 = strict intersection.
        max_delta_pct: Maximum delta percentage for nearest-class assignment.
        min_group_size: Minimum group size for class extraction.
        on_section: Optional callback ``(section_name, event)`` where event
            is ``"start"`` or ``"done"``.
        workers: Number of worker processes for parallel compression.
            ``None`` or ``1`` = sequential (default).

    Returns:
        (tier_b, tier_c)
    """
    if all_hosts is None:
        all_hosts_set: set[str] = set()
        for section in store.get_sections():
            all_hosts_set.update(store.get_hosts_for_section(section))
    else:
        all_hosts_set = set(all_hosts)

    tier_b: dict[str, Any] = {}
    tier_c: dict[str, dict[str, Any]] = {host: {} for host in all_hosts_set}
    sections = store.get_sections()

    effective_workers = workers if workers is not None else 1
    use_parallel = effective_workers > 1 and len(sections) > 1

    if use_parallel:
        try:
            db_path = store.ensure_file_backed()
        except Exception:
            logger.warning(
                "Failed to export database for parallel mode, falling back to sequential",
            )
            use_parallel = False

    if use_parallel:
        from concurrent.futures import ProcessPoolExecutor, as_completed

        with ProcessPoolExecutor(max_workers=effective_workers) as executor:
            futures: dict[Any, str] = {}
            for section in sections:
                hosts = store.get_hosts_for_section(section)
                if not hosts:
                    continue
                section_type = store.get_section_type(section)
                if on_section:
                    on_section(section, "start")
                future = executor.submit(
                    _compress_section_worker,
                    db_path, section, section_type, hosts,
                    threshold, max_delta_pct, min_group_size,
                )
                futures[future] = section

            for future in as_completed(futures):
                section_name = futures[future]
                try:
                    section_b, section_c = future.result()
                    tier_b.update(section_b)
                    for host, data in section_c.items():
                        tier_c[host][section_name] = data
                    if on_section:
                        on_section(section_name, "done")
                except Exception as exc:
                    logger.warning(
                        "Worker failed for section %s: %s. Falling back to sequential.",
                        section_name, exc,
                    )
                    hosts = store.get_hosts_for_section(section_name)
                    section_type = store.get_section_type(section_name)
                    section_b, section_c = _compress_single_section(
                        store, section_name, hosts, section_type,
                        threshold=threshold, max_delta_pct=max_delta_pct,
                        min_group_size=min_group_size,
                    )
                    tier_b.update(section_b)
                    for host, data in section_c.items():
                        tier_c[host][section_name] = data
                    if on_section:
                        on_section(section_name, "done")
    else:
        for section in sections:
            hosts = store.get_hosts_for_section(section)
            if not hosts:
                continue

            if on_section:
                on_section(section, "start")

            if store.is_list_section(section):
                hosts_data = {h: store.get_section_data(section, h) for h in hosts}
                _compress_list_section(
                    section, hosts_data, tier_b, tier_c,
                    store=store, threshold=threshold,
                )
            elif store.get_section_type(section) == "dict":
                _compress_dict_section(
                    section, None, tier_b, tier_c,
                    flat=store.get_flat(section), store=store,
                    threshold=threshold, max_delta_pct=max_delta_pct,
                    min_group_size=min_group_size,
                )
            else:
                for host in hosts:
                    tier_c[host][section] = store.get_section_data(section, host)

            if on_section:
                on_section(section, "done")

    # Post-process: collapse zero-delta class references into _class_instances.
    _collapse_class_instances(tier_c)

    return tier_b, tier_c


def _compress_single_section(
    store: DuckDBStore,
    section: str,
    hosts: list[str],
    section_type: str,
    *,
    threshold: float = 100.0,
    max_delta_pct: float = 20.0,
    min_group_size: int = 3,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compress one section using the given store.

    Returns ``(section_b, result_c)`` where:
      ``section_b`` = ``{ClassName: class_def}``
      ``result_c``  = ``{host: section_data}``
    """
    section_b: dict[str, Any] = {}
    section_c: dict[str, dict[str, Any]] = {host: {} for host in hosts}

    if section_type == "list_of_dicts":
        hosts_data = {h: store.get_section_data(section, h) for h in hosts}
        _compress_list_section(
            section, hosts_data, section_b, section_c,
            store=store, threshold=threshold,
        )
    elif section_type == "dict":
        _compress_dict_section(
            section, None, section_b, section_c,
            flat=store.get_flat(section), store=store,
            threshold=threshold, max_delta_pct=max_delta_pct,
            min_group_size=min_group_size,
        )
    else:
        for host in hosts:
            section_c[host][section] = store.get_section_data(section, host)

    result_c: dict[str, Any] = {}
    for host in section_c:
        if section in section_c[host]:
            result_c[host] = section_c[host][section]
    return section_b, result_c


def _compress_section_worker(
    db_path: str,
    section: str,
    section_type: str,
    hosts: list[str],
    threshold: float,
    max_delta_pct: float,
    min_group_size: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Process one section in a worker process.

    Opens its own read-only DuckDB connection.  No callbacks — progress
    is tracked by the main process.
    """
    import duckdb

    from decoct.storage import DuckDBStore

    conn = duckdb.connect(db_path, read_only=True)
    store = DuckDBStore.from_connection(conn)
    try:
        return _compress_single_section(
            store, section, hosts, section_type,
            threshold=threshold, max_delta_pct=max_delta_pct,
            min_group_size=min_group_size,
        )
    finally:
        conn.close()


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


def _collapse_class_instances(tier_c: dict[str, dict[str, Any]]) -> None:
    """Collapse zero-delta class references into ``_class_instances`` lists."""
    for host in tier_c:
        zero_delta: list[str] = []
        remaining: dict[str, Any] = {}
        for section, tc in tier_c[host].items():
            if (
                isinstance(tc, dict)
                and set(tc.keys()) == {"_class"}
                and tc["_class"] == _make_class_name(section, 0)
            ):
                zero_delta.append(section)
            else:
                remaining[section] = tc
        if zero_delta:
            tier_c[host] = {"_class_instances": sorted(zero_delta), **remaining}
        else:
            tier_c[host] = remaining


# ---------------------------------------------------------------------------
# Identity helpers
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


def _make_class_name(section: str, index: int) -> str:
    parts = section.split("_")
    name = "".join(p.capitalize() for p in parts)
    if index > 0:
        name += f"_{index}"
    return name


# ---------------------------------------------------------------------------
# Reusable helpers: class extraction, delta computation, assignment cost
# ---------------------------------------------------------------------------


def _extract_class_fields(
    flat: dict[str, dict[str, Any]],
    group_hosts: list[str],
    identity: set[str],
    threshold: float,
) -> dict[str, Any]:
    """Extract class fields from a group using majority-vote.

    Returns a flat dict ``{dotted.path: value}`` of fields that qualify
    for the class body.
    """
    min_count = max(1, int(len(group_hosts) * threshold / 100.0))

    # Paths present in ALL hosts (shared paths, excluding identity)
    path_sets = [set(flat[h].keys()) for h in group_hosts]
    shared_paths = path_sets[0].copy()
    for ps in path_sets[1:]:
        shared_paths &= ps
    shared_paths -= identity

    class_flat: dict[str, Any] = {}
    for path in sorted(shared_paths):
        counter: dict[tuple[str, str], int] = {}
        value_map: dict[tuple[str, str], Any] = {}
        for h in group_hosts:
            val = flat[h][path]
            sig = (type(val).__name__, repr(val))
            counter[sig] = counter.get(sig, 0) + 1
            value_map[sig] = val

        best_sig = max(counter, key=counter.__getitem__)
        if counter[best_sig] >= min_count:
            class_flat[path] = value_map[best_sig]

    return class_flat


def _compute_delta(
    host_flat: dict[str, Any],
    class_flat: dict[str, Any],
    identity_fields: set[str],
    class_name: str,
) -> dict[str, Any]:
    """Build delta dict for a host against a class definition."""
    delta: dict[str, Any] = {"_class": class_name}

    for field in sorted(identity_fields):
        if field in host_flat:
            delta[field] = host_flat[field]

    for path in sorted(class_flat.keys()):
        if path in identity_fields:
            continue
        if path not in host_flat:
            continue  # unreachable for group members; Phase C rejects via inf cost
        if not _values_equal(host_flat[path], class_flat[path]):
            delta[path] = host_flat[path]

    for path in sorted(host_flat.keys()):
        if path in identity_fields or path in class_flat:
            continue
        delta[path] = host_flat[path]

    return delta


def _assignment_cost(
    host_flat: dict[str, Any],
    class_flat: dict[str, Any],
    identity_fields: set[str],
) -> float:
    """Number of delta entries needed to assign host to this class.

    Returns ``float('inf')`` if the host is missing any identity field
    declared by the class.
    """
    # If the host lacks an identity field, it can't be an instance of this class
    for field in identity_fields:
        if field not in host_flat:
            return float("inf")

    cost = 0
    for path in class_flat:
        if path in identity_fields:
            continue
        if path not in host_flat:
            return float("inf")  # host lacks class field — cannot assign
        elif not _values_equal(host_flat[path], class_flat[path]):
            cost += 1  # needs override

    # Fields in host but not in class → extra delta fields
    for path in host_flat:
        if path in identity_fields:
            continue
        if path not in class_flat:
            cost += 1

    return cost


# ---------------------------------------------------------------------------
# Raw emission helpers
# ---------------------------------------------------------------------------


def _emit_raw(
    section: str,
    hosts: list[str],
    tier_c: dict[str, dict[str, Any]],
    *,
    store: DuckDBStore | None = None,
    hosts_data: dict[str, Any] | None = None,
    flat: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Emit all hosts as uncompressed for a section."""
    for host in hosts:
        _emit_raw_host(section, host, tier_c, store=store, hosts_data=hosts_data, flat=flat)


def _emit_raw_host(
    section: str,
    host: str,
    tier_c: dict[str, dict[str, Any]],
    *,
    store: DuckDBStore | None = None,
    hosts_data: dict[str, Any] | None = None,
    flat: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Emit a single host as uncompressed for a section."""
    if flat is not None and host in flat:
        tier_c[host][section] = _unflatten(flat[host])
    elif store is not None:
        tier_c[host][section] = store.get_section_data(section, host)
    else:
        assert hosts_data is not None
        tier_c[host][section] = copy.deepcopy(hosts_data[host])


# ---------------------------------------------------------------------------
# Dict section compression
# ---------------------------------------------------------------------------


def _compress_dict_section(
    section: str,
    hosts_data: dict[str, Any] | None,
    tier_b: dict[str, Any],
    tier_c: dict[str, dict[str, Any]],
    *,
    flat: dict[str, dict[str, Any]] | None = None,
    store: DuckDBStore | None = None,
    threshold: float = 100.0,
    max_delta_pct: float = 20.0,
    min_group_size: int = 3,
) -> None:
    if flat is None:
        assert hosts_data is not None
        flat = {host: _flatten(data) for host, data in hosts_data.items()}
    hosts = sorted(flat.keys())

    if len(hosts) < min_group_size:
        _emit_raw(section, hosts, tier_c, store=store, hosts_data=hosts_data, flat=flat)
        return

    # Phase A: exact-value signature grouping
    sig_map: dict[tuple[tuple[str, str, str], ...], list[str]] = {}
    for host in hosts:
        sig = tuple(sorted((k, type(v).__name__, repr(v)) for k, v in flat[host].items()))
        sig_map.setdefault(sig, []).append(host)

    # Exact-match groups of 2+ always qualify — identical hosts definitionally
    # share all fields, so there is no false-positive risk.
    large_groups = [sorted(g) for g in sig_map.values() if len(g) >= 2]
    small_hosts = [h for g in sig_map.values() if len(g) < 2 for h in sorted(g)]

    # Phase B': extract classes from large exact-match groups
    classes: dict[str, dict[str, Any]] = {}
    class_identity: dict[str, set[str]] = {}
    class_idx = 0

    for group_hosts in large_groups:
        identity = _find_identity_fields(flat, group_hosts)
        class_flat = _extract_class_fields(flat, group_hosts, identity, threshold)

        if not class_flat:
            small_hosts.extend(sorted(group_hosts))
            continue

        class_name = _make_class_name(section, class_idx)
        class_idx += 1
        class_def = _unflatten(class_flat)
        if identity:
            class_def["_identity"] = sorted(identity)
        tier_b[class_name] = class_def
        classes[class_name] = class_flat
        class_identity[class_name] = identity

        for host in group_hosts:
            tier_c[host][section] = _compute_delta(flat[host], class_flat, identity, class_name)

    # Fallback: if no classes from Phase A/B', try single-group extraction
    if not classes:
        identity = _find_identity_fields(flat, hosts)
        class_flat = _extract_class_fields(flat, hosts, identity, threshold)

        if len(class_flat) < 3:
            _emit_raw(section, hosts, tier_c, store=store, hosts_data=hosts_data, flat=flat)
            return

        class_name = _make_class_name(section, 0)
        class_def = _unflatten(class_flat)
        if identity:
            class_def["_identity"] = sorted(identity)
        tier_b[class_name] = class_def
        classes[class_name] = class_flat
        class_identity[class_name] = identity

        for host in hosts:
            cost = _assignment_cost(flat[host], class_flat, identity)
            total_fields = len(class_flat) + len(identity)
            cost_pct = cost * 100.0 / total_fields if total_fields else float("inf")
            if cost_pct <= max_delta_pct:
                tier_c[host][section] = _compute_delta(
                    flat[host], class_flat, identity, class_name,
                )
            else:
                _emit_raw_host(section, host, tier_c, store=store, hosts_data=hosts_data, flat=flat)
        return

    # Phase C: nearest-class assignment for remaining small_hosts
    for host in small_hosts:
        best_class: str | None = None
        best_cost = float("inf")

        for cname, cflat in classes.items():
            ident = class_identity[cname]
            cost = _assignment_cost(flat[host], cflat, ident)
            total_fields = len(cflat) + len(ident)
            if total_fields == 0:
                continue
            cost_pct = cost * 100.0 / total_fields
            if cost_pct <= max_delta_pct and cost < best_cost:
                best_cost = cost
                best_class = cname

        if best_class is not None:
            tier_c[host][section] = _compute_delta(
                flat[host], classes[best_class],
                class_identity[best_class], best_class,
            )
        else:
            _emit_raw_host(section, host, tier_c, store=store, hosts_data=hosts_data, flat=flat)


# ---------------------------------------------------------------------------
# List-of-dicts section compression (with sub-grouping)
# ---------------------------------------------------------------------------


def _find_candidate_identity_fields(
    all_instances: list[tuple[str, int, dict[str, Any]]],
) -> set[str]:
    """Pre-scan: fields present in all instances with all-unique values.

    These are excluded from clustering signatures because they would
    prevent any instances from grouping together.
    """
    dicts = [item[2] for item in all_instances]
    if len(dicts) < 2:
        return set()

    shared = set(dicts[0].keys())
    for d in dicts[1:]:
        shared &= set(d.keys())

    candidates: set[str] = set()
    for field in shared:
        sigs: set[tuple[str, str]] = set()
        unique = True
        for d in dicts:
            sig = (type(d[field]).__name__, repr(d[field]))
            if sig in sigs:
                unique = False
                break
            sigs.add(sig)
        if unique:
            candidates.add(field)
    return candidates


def _cluster_list_instances(
    all_instances: list[tuple[str, int, dict[str, Any]]],
    exclude_fields: set[str],
) -> list[list[tuple[str, int, dict[str, Any]]]]:
    """Group list instances by structural similarity.

    Phase A: exact-match grouping by (field, type, value) signature,
    EXCLUDING candidate identity fields.  This ensures instances that
    differ only in identity (e.g. neighbor_address) cluster together.
    """
    sig_map: dict[tuple[tuple[str, str, str], ...], list[tuple[str, int, dict[str, Any]]]] = {}
    for item in all_instances:
        _host, _idx, inst = item
        sig = tuple(sorted(
            (k, type(v).__name__, repr(v))
            for k, v in inst.items()
            if k not in exclude_fields
        ))
        sig_map.setdefault(sig, []).append(item)

    return list(sig_map.values())


def _find_list_identity_fields(instances: list[dict[str, Any]]) -> list[str]:
    """Fields present in all instances with all-unique values (within cluster)."""
    if len(instances) < 2:
        return []

    shared = set(instances[0].keys())
    for inst in instances[1:]:
        shared &= set(inst.keys())

    id_fields: list[str] = []
    for field in sorted(shared):
        sigs: set[tuple[str, str]] = set()
        unique = True
        for inst in instances:
            sig = (type(inst[field]).__name__, repr(inst[field]))
            if sig in sigs:
                unique = False
                break
            sigs.add(sig)
        if unique:
            id_fields.append(field)

    return id_fields


def _extract_list_class_fields(
    instances: list[dict[str, Any]],
    id_fields: list[str],
    threshold: float,
) -> dict[str, Any]:
    """Extract class fields from a cluster of list instances.

    A field enters the class if:
    1. Present in ALL instances (100% presence — no _remove)
    2. The dominant value appears in >= threshold% of instances
    """
    total = len(instances)
    if total == 0:
        return {}

    id_set = set(id_fields)
    field_values: dict[str, list[Any]] = {}
    field_present: dict[str, int] = {}
    for inst in instances:
        for field, value in inst.items():
            if field in id_set:
                continue
            field_values.setdefault(field, []).append(value)
            field_present[field] = field_present.get(field, 0) + 1

    min_count = max(1, int(total * threshold / 100.0))
    class_fields: dict[str, Any] = {}
    for field, values in field_values.items():
        if field_present.get(field, 0) < total:
            continue  # Must be present in ALL instances
        counter: dict[tuple[str, str], int] = {}
        value_map: dict[tuple[str, str], Any] = {}
        for v in values:
            sig = (type(v).__name__, repr(v))
            counter[sig] = counter.get(sig, 0) + 1
            value_map[sig] = v
        best_sig = max(counter, key=counter.__getitem__)
        if counter[best_sig] >= min_count:
            class_fields[field] = value_map[best_sig]

    return class_fields


def _emit_list_tier_c(
    host: str,
    section: str,
    host_instances: list[dict[str, Any]],
    tier_c: dict[str, dict[str, Any]],
) -> None:
    """Emit list section tier_c for a host with backward-compat shim.

    When ALL instances reference the SAME class, emit the current format
    (section-level ``_class``).  Otherwise, emit per-instance ``_class``.
    """
    unique_classes: set[str] = set()
    all_have_class = True
    for inst in host_instances:
        if "_class" in inst:
            unique_classes.add(inst["_class"])
        else:
            all_have_class = False

    if all_have_class and len(unique_classes) == 1:
        # Backward-compat: section-level _class
        class_name = unique_classes.pop()
        stripped = []
        for inst in host_instances:
            d = {k: v for k, v in inst.items() if k != "_class"}
            stripped.append(d)
        tier_c[host][section] = {"_class": class_name, "instances": stripped}
    else:
        # New format: per-instance _class (or no _class for raw)
        tier_c[host][section] = {"instances": host_instances}


def _compress_list_section(
    section: str,
    hosts_data: dict[str, Any],
    tier_b: dict[str, Any],
    tier_c: dict[str, dict[str, Any]],
    *,
    store: DuckDBStore | None = None,
    threshold: float = 100.0,
    min_cluster_size: int = 3,
) -> None:
    """Compress a list-of-dicts section with instance sub-grouping.

    Clusters instances by similarity (excluding candidate identity fields),
    then extracts a separate class per cluster.  Each host's instances
    reference their cluster's class via per-instance ``_class``.
    """
    # 1. Gather all instances with provenance tracking
    all_instances: list[tuple[str, int, dict[str, Any]]] = []
    for host in sorted(hosts_data):
        for idx, inst in enumerate(hosts_data[host]):
            all_instances.append((host, idx, inst))

    if not all_instances:
        for host in hosts_data:
            if store is not None:
                tier_c[host][section] = store.get_section_data(section, host)
            else:
                tier_c[host][section] = copy.deepcopy(hosts_data[host])
        return

    # 2. Pre-scan for candidate identity fields, then cluster
    candidate_id_fields = _find_candidate_identity_fields(all_instances)
    clusters = _cluster_list_instances(all_instances, exclude_fields=candidate_id_fields)

    # 3. Per-cluster: extract class, compute instance deltas
    instance_deltas: dict[tuple[str, int], dict[str, Any]] = {}

    class_idx = 0
    for cluster in clusters:
        instances_dicts = [item[2] for item in cluster]

        if len(instances_dicts) < min_cluster_size:
            # Too small to form a class — emit raw
            for host, orig_idx, inst in cluster:
                instance_deltas[(host, orig_idx)] = copy.deepcopy(inst)
            continue

        # Identity: fields unique across cluster instances
        id_fields = _find_list_identity_fields(instances_dicts)

        # Class fields: present in ALL instances, value agreement >= threshold
        class_fields = _extract_list_class_fields(instances_dicts, id_fields, threshold)

        if len(class_fields) < 3:
            # Not enough shared structure — emit raw
            for host, orig_idx, inst in cluster:
                instance_deltas[(host, orig_idx)] = copy.deepcopy(inst)
            continue

        class_name = _make_class_name(section, class_idx)
        class_idx += 1

        # Build and emit class def
        class_def: dict[str, Any] = dict(class_fields)
        if id_fields:
            class_def["_identity"] = sorted(id_fields)
        tier_b[class_name] = class_def

        id_set = set(id_fields)
        # Per-instance delta (purely additive — no _remove)
        for host, orig_idx, inst in cluster:
            delta: dict[str, Any] = {"_class": class_name}
            for field in sorted(id_set):
                if field in inst:
                    delta[field] = inst[field]
            for field in sorted(class_fields):
                if field in id_set:
                    continue
                # Field is guaranteed present (100% presence rule)
                if not _values_equal(inst[field], class_fields[field]):
                    delta[field] = inst[field]
            for field in sorted(inst):
                if field in id_set or field in class_fields:
                    continue
                delta[field] = inst[field]
            instance_deltas[(host, orig_idx)] = delta

    # 4. Reassemble per-host instance lists (preserving original order)
    for host in sorted(hosts_data):
        host_instances: list[dict[str, Any]] = []
        for idx in range(len(hosts_data[host])):
            host_instances.append(instance_deltas[(host, idx)])
        _emit_list_tier_c(host, section, host_instances, tier_c)
