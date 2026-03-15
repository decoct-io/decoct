"""Budget-aware retrieval layer for compressed fleet data.

Provides :class:`CompressedFleet`, a queryable handle over compressed
fleet output (Tier B classes + Tier C per-host deltas) backed by DuckDB.

Typical usage::

    from decoct.fleet import compress_to_file

    fleet = compress_to_file(inputs, "fleet.db")
    payload = fleet.retrieve(hosts=["pe-lon-01"], token_budget=100_000)

The retrieval layer assembles a self-contained YAML payload within a
token budget — an LLM receiving it can fully reconstruct the original
configs for the included hosts.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import duckdb

from decoct.reconstruct import _section_to_class_name


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """Estimate token count from text length.  ~1 token per 4 chars."""
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Helpers for extracting class references from tier_c data
# ---------------------------------------------------------------------------

def _extract_class_refs(section_data: Any) -> set[str]:
    """Extract all class names referenced by a host's section data."""
    refs: set[str] = set()
    if isinstance(section_data, dict):
        if "_class" in section_data:
            refs.add(section_data["_class"])
        if "instances" in section_data:
            for inst in section_data["instances"]:
                if isinstance(inst, dict) and "_class" in inst:
                    refs.add(inst["_class"])
    return refs


def _count_delta_fields(section_data: Any) -> int:
    """Count delta fields for ranking.  Higher = more unusual host."""
    if not isinstance(section_data, dict):
        return 0
    count = 0
    skip_keys = {"_class", "_identity", "_class_instances", "instances"}
    count += sum(1 for k in section_data if k not in skip_keys)
    if "instances" in section_data:
        for inst in section_data["instances"]:
            if isinstance(inst, dict):
                count += sum(1 for k in inst if k not in {"_class"})
    return count


def _section_from_class_name(class_name: str) -> str:
    """Infer section name from a class name.

    Reverses ``_make_class_name``: ``BgpNeighbors_1`` -> ``bgp_neighbors``.
    Strips trailing ``_N`` index, then lowercases and splits on capitals.
    """
    name = class_name
    # Strip _N suffix
    if "_" in name:
        parts = name.rsplit("_", 1)
        if parts[1].isdigit():
            name = parts[0]
    # Split on capital letters
    result: list[str] = []
    current = ""
    for ch in name:
        if ch.isupper() and current:
            result.append(current.lower())
            current = ch
        else:
            current += ch
    if current:
        result.append(current.lower())
    return "_".join(result)


# ---------------------------------------------------------------------------
# HostInfo dataclass
# ---------------------------------------------------------------------------

@dataclass
class HostInfo:
    """Metadata for a single host in the compressed fleet."""

    hostname: str
    class_profile: list[str]
    total_delta: int
    section_count: int
    is_zero_delta: bool


# ---------------------------------------------------------------------------
# CompressedFleet
# ---------------------------------------------------------------------------

class CompressedFleet:
    """Handle to compressed fleet data.  Provides query and retrieval."""

    def __init__(self, db_path: str) -> None:
        """Open existing compressed fleet database."""
        self._db_path = db_path
        self._conn = duckdb.connect(db_path)

    @classmethod
    def from_results(
        cls,
        db_path: str,
        tier_b: dict[str, Any],
        tier_c: dict[str, dict[str, Any]],
    ) -> CompressedFleet:
        """Create fleet DB from ``compress_db()`` output.

        Populates output tables (classes, host_compressed, host_meta,
        class_members) from the tier_b/tier_c dicts, then returns
        a queryable handle.
        """
        conn = duckdb.connect(db_path)
        _create_output_tables(conn)
        _populate_tables(conn, tier_b, tier_c)
        conn.close()
        return cls(db_path)

    # --- Metadata queries ---

    def host_count(self) -> int:
        """Total number of hosts."""
        row = self._conn.execute("SELECT count(*) FROM host_meta").fetchone()
        return int(row[0]) if row else 0

    def class_count(self) -> int:
        """Total number of Tier B classes."""
        row = self._conn.execute("SELECT count(*) FROM classes").fetchone()
        return int(row[0]) if row else 0

    def hosts(self) -> list[str]:
        """All hostnames, sorted."""
        rows = self._conn.execute(
            "SELECT host FROM host_meta ORDER BY host"
        ).fetchall()
        return [r[0] for r in rows]

    def classes(self) -> list[str]:
        """All class names, sorted."""
        rows = self._conn.execute(
            "SELECT class_name FROM classes ORDER BY class_name"
        ).fetchall()
        return [r[0] for r in rows]

    def sections(self) -> list[str]:
        """All distinct section names."""
        rows = self._conn.execute(
            "SELECT DISTINCT section FROM host_compressed ORDER BY section"
        ).fetchall()
        return [r[0] for r in rows]

    def host_info(self, host: str) -> HostInfo:
        """Return metadata for a single host."""
        row = self._conn.execute(
            "SELECT host, class_profile, total_delta, section_count, is_zero_delta "
            "FROM host_meta WHERE host = ?",
            [host],
        ).fetchone()
        if row is None:
            raise KeyError(f"Host '{host}' not found")
        return HostInfo(
            hostname=row[0],
            class_profile=row[1].split(",") if row[1] else [],
            total_delta=int(row[2]),
            section_count=int(row[3]),
            is_zero_delta=bool(row[4]),
        )

    def hosts_by_class(self, class_name: str) -> list[str]:
        """All hosts that reference this class in any section."""
        rows = self._conn.execute(
            "SELECT DISTINCT host FROM class_members "
            "WHERE class_name = ? ORDER BY host",
            [class_name],
        ).fetchall()
        return [r[0] for r in rows]

    def hosts_by_delta_size(self, min_delta: int = 1) -> list[str]:
        """Hosts with total delta >= min_delta, ordered by delta size desc."""
        rows = self._conn.execute(
            "SELECT host FROM host_meta "
            "WHERE total_delta >= ? ORDER BY total_delta DESC, host",
            [min_delta],
        ).fetchall()
        return [r[0] for r in rows]

    # --- Retrieval ---

    def retrieve(
        self,
        hosts: list[str] | None = None,
        sections: list[str] | None = None,
        token_budget: int = 100_000,
        include_tier_a: bool = True,
        prioritise: str = "delta",
    ) -> str:
        """Assemble a self-contained YAML payload within token budget.

        Args:
            hosts: Specific hosts to include.  If None, selects by
                *prioritise* strategy up to budget.
            sections: Only include these sections.  None = all.
            token_budget: Soft token limit (allows ~5% overshoot).
            include_tier_a: Prepend Tier A summary if True.
            prioritise: Host selection strategy when *hosts* is None.
                ``"delta"`` = most-different first,
                ``"alphabetical"`` = sorted,
                ``"random"`` = random sample.

        Returns:
            YAML string that is self-contained: an LLM receiving it can
            reconstruct included hosts exactly.
        """
        from decoct.render import render_yaml

        parts: list[str] = []
        remaining = token_budget

        # --- Tier A ---
        if include_tier_a:
            tier_a_yaml = self.generate_tier_a()
            tier_a_tokens = _estimate_tokens(tier_a_yaml)
            parts.append("# Tier A — Fleet Summary\n" + tier_a_yaml)
            remaining -= tier_a_tokens

        # --- Select hosts ---
        if hosts is not None:
            selected_hosts = list(hosts)
        else:
            selected_hosts = self._select_hosts(prioritise)

        # --- Collect host data and referenced classes ---
        host_yamls: list[tuple[str, str]] = []  # (hostname, yaml_string)
        referenced_classes: set[str] = set()

        for hostname in selected_hosts:
            tc_data = self._load_host_tier_c(hostname, sections)
            if not tc_data:
                continue
            # Collect class refs
            for section_data in tc_data.values():
                if section_data == "_class_instances_marker":
                    continue
                referenced_classes |= _extract_class_refs(section_data)

            # _class_instances also reference classes
            ci = tc_data.get("_class_instances")
            if isinstance(ci, list):
                for sec_name in ci:
                    referenced_classes.add(_section_to_class_name(sec_name))

            yaml_str = render_yaml({hostname: tc_data})
            host_yamls.append((hostname, yaml_str))

        # --- Render Tier B (only referenced classes) ---
        tier_b_data = self._load_tier_b(referenced_classes)
        tier_b_yaml = ""
        if tier_b_data:
            tier_b_yaml = render_yaml(tier_b_data)
        tier_b_tokens = _estimate_tokens(tier_b_yaml)

        # Reserve for Tier B
        remaining -= tier_b_tokens

        # --- Fill with hosts up to budget ---
        included_hosts: list[str] = []
        included_yamls: list[str] = []
        for hostname, yaml_str in host_yamls:
            cost = _estimate_tokens(yaml_str)
            if remaining - cost < -(token_budget * 0.05):
                break  # Would exceed budget by more than 5%
            included_yamls.append(yaml_str)
            included_hosts.append(hostname)
            remaining -= cost

        # --- Assemble output ---
        if tier_b_yaml:
            parts.append("# Tier B — Class Definitions\n" + tier_b_yaml)
        if included_yamls:
            parts.append(
                f"# Tier C — Host Configs ({len(included_hosts)} hosts)\n"
                + "\n".join(included_yamls)
            )

        return "\n---\n".join(parts) + "\n"

    def retrieve_for_query(
        self,
        query: str,
        token_budget: int = 100_000,
    ) -> str:
        """Given a natural language query, select relevant hosts/sections.

        Simple keyword matching:
        - Hostname in query -> include that host
        - Section name in query -> filter to that section
        - "different"/"outlier"/"non-standard" -> delta prioritisation
        - Class name in query -> include hosts using that class
        - Fallback: delta-prioritised retrieval
        """
        query_lower = query.lower()
        target_hosts: list[str] | None = None
        target_sections: list[str] | None = None
        prioritise = "delta"

        # Check for hostname matches
        all_hosts = self.hosts()
        matched_hosts = [h for h in all_hosts if h.lower() in query_lower]
        if matched_hosts:
            target_hosts = matched_hosts

        # Check for section name matches
        all_sections = self.sections()
        matched_sections = [s for s in all_sections if s.lower() in query_lower]
        if matched_sections:
            target_sections = matched_sections

        # Check for class name matches
        if target_hosts is None:
            all_classes = self.classes()
            for cls in all_classes:
                if cls.lower() in query_lower:
                    target_hosts = self.hosts_by_class(cls)
                    break

        # Check for outlier keywords
        outlier_keywords = {"different", "outlier", "non-standard", "unusual", "exception"}
        if any(kw in query_lower for kw in outlier_keywords):
            prioritise = "delta"

        return self.retrieve(
            hosts=target_hosts,
            sections=target_sections,
            token_budget=token_budget,
            prioritise=prioritise,
        )

    # --- Tier A generation ---

    def generate_tier_a(self) -> str:
        """Generate Tier A summary from compressed fleet metadata.

        Metadata-only — no config values, just structure.
        """
        from decoct.render import render_yaml

        summary: dict[str, Any] = {}

        # Fleet size
        summary["fleet_size"] = self.host_count()

        # Section inventory
        summary["sections"] = self.sections()

        # Class inventory
        class_info: dict[str, Any] = {}
        for cls_name in self.classes():
            members = self.hosts_by_class(cls_name)
            row = self._conn.execute(
                "SELECT section, definition FROM classes WHERE class_name = ?",
                [cls_name],
            ).fetchone()
            section = row[0] if row else ""
            defn = json.loads(row[1]) if row else {}
            field_count = sum(1 for k in defn if not k.startswith("_"))
            class_info[cls_name] = {
                "section": section,
                "members": len(members),
                "fields": field_count,
            }
        summary["classes"] = class_info

        # Zero-delta host count
        row = self._conn.execute(
            "SELECT count(*) FROM host_meta WHERE is_zero_delta = true"
        ).fetchone()
        summary["zero_delta_hosts"] = int(row[0]) if row else 0

        # Top-10 highest-delta hosts
        rows = self._conn.execute(
            "SELECT host, total_delta FROM host_meta "
            "ORDER BY total_delta DESC LIMIT 10"
        ).fetchall()
        summary["top_delta_hosts"] = [
            {"host": r[0], "delta": int(r[1])} for r in rows
        ]

        # Class distribution
        rows = self._conn.execute(
            "SELECT class_name, count(DISTINCT host) as cnt "
            "FROM class_members GROUP BY class_name ORDER BY cnt DESC"
        ).fetchall()
        summary["class_distribution"] = {r[0]: int(r[1]) for r in rows}

        return render_yaml(summary)

    # --- Export ---

    def export_tier_b_yaml(self) -> str:
        """Export all Tier B classes as YAML."""
        from decoct.render import render_yaml

        all_classes = self.classes()
        tier_b = self._load_tier_b(set(all_classes))
        return render_yaml(tier_b) if tier_b else ""

    def export_host_yaml(self, host: str) -> str:
        """Export one host's Tier C as YAML."""
        from decoct.render import render_yaml

        tc = self._load_host_tier_c(host)
        return render_yaml({host: tc}) if tc else ""

    def close(self) -> None:
        """Close the DuckDB connection."""
        self._conn.close()

    # --- Internal helpers ---

    def _select_hosts(self, prioritise: str) -> list[str]:
        """Select hosts by strategy."""
        all_hosts = self.hosts()
        if prioritise == "alphabetical":
            return all_hosts
        elif prioritise == "random":
            shuffled = list(all_hosts)
            random.shuffle(shuffled)
            return shuffled
        else:
            # "delta" — representative zero-delta first, then by delta desc
            rows = self._conn.execute(
                "SELECT host, total_delta, is_zero_delta FROM host_meta "
                "ORDER BY total_delta DESC, host"
            ).fetchall()

            # Pick up to 3 zero-delta hosts as representatives
            zero_delta = [r[0] for r in rows if r[2]]
            non_zero = [r[0] for r in rows if not r[2]]

            result: list[str] = []
            result.extend(zero_delta[:3])
            result.extend(non_zero)
            # Add remaining zero-delta
            result.extend(zero_delta[3:])
            return result

    def _load_host_tier_c(
        self,
        host: str,
        sections: list[str] | None = None,
    ) -> dict[str, Any]:
        """Load a host's Tier C data from DuckDB."""
        if sections is not None:
            placeholders = ",".join("?" for _ in sections)
            rows = self._conn.execute(
                f"SELECT section, delta FROM host_compressed "
                f"WHERE host = ? AND section IN ({placeholders}) "
                f"ORDER BY section",
                [host, *sections],
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT section, delta FROM host_compressed "
                "WHERE host = ? ORDER BY section",
                [host],
            ).fetchall()

        tc: dict[str, Any] = {}
        for section, delta_json in rows:
            tc[section] = json.loads(delta_json)

        # Reconstruct _class_instances from host_meta
        meta_row = self._conn.execute(
            "SELECT class_profile, is_zero_delta FROM host_meta WHERE host = ?",
            [host],
        ).fetchone()

        # Check if there are _class_instances to reconstruct
        if "_class_instances" in tc:
            pass  # Already loaded from host_compressed
        elif meta_row and meta_row[1]:
            # Zero-delta host — all sections are class instances if they were stored
            pass

        return tc

    def _load_tier_b(self, class_names: set[str]) -> dict[str, Any]:
        """Load specific Tier B class definitions."""
        if not class_names:
            return {}
        placeholders = ",".join("?" for _ in class_names)
        rows = self._conn.execute(
            f"SELECT class_name, definition FROM classes "
            f"WHERE class_name IN ({placeholders}) "
            f"ORDER BY class_name",
            list(class_names),
        ).fetchall()
        result: dict[str, Any] = {}
        for class_name, definition in rows:
            result[class_name] = json.loads(definition)
        return result


# ---------------------------------------------------------------------------
# DuckDB table creation and population
# ---------------------------------------------------------------------------

def _create_output_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the output tables for compressed fleet data."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS classes (
            class_name TEXT PRIMARY KEY,
            section    TEXT NOT NULL,
            definition TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS host_compressed (
            host       TEXT NOT NULL,
            section    TEXT NOT NULL,
            delta      TEXT NOT NULL,
            delta_size INT NOT NULL,
            PRIMARY KEY (host, section)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS host_meta (
            host          TEXT PRIMARY KEY,
            class_profile TEXT NOT NULL,
            total_delta   INT NOT NULL,
            section_count INT NOT NULL,
            is_zero_delta BOOLEAN NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS class_members (
            class_name TEXT NOT NULL,
            host       TEXT NOT NULL,
            section    TEXT NOT NULL,
            PRIMARY KEY (class_name, host, section)
        )
    """)


def _populate_tables(
    conn: duckdb.DuckDBPyConnection,
    tier_b: dict[str, Any],
    tier_c: dict[str, dict[str, Any]],
) -> None:
    """Populate output tables from tier_b/tier_c."""
    # --- Populate classes table ---
    for class_name, class_def in tier_b.items():
        if class_name.startswith("_"):
            continue  # skip _list_classes etc.
        section = _section_from_class_name(class_name)
        conn.execute(
            "INSERT INTO classes VALUES (?, ?, ?)",
            [class_name, section, json.dumps(class_def, default=str)],
        )

    # --- Populate host_compressed, host_meta, class_members ---
    for host, host_data in tier_c.items():
        all_refs: set[str] = set()
        total_delta = 0
        section_count = 0

        # Handle _class_instances
        class_instances = host_data.get("_class_instances", [])
        if isinstance(class_instances, list):
            for sec_name in class_instances:
                cls = _section_to_class_name(sec_name)
                all_refs.add(cls)
                conn.execute(
                    "INSERT OR IGNORE INTO class_members VALUES (?, ?, ?)",
                    [cls, host, sec_name],
                )

        for section, section_data in host_data.items():
            if section == "_class_instances":
                # Store as a special section
                conn.execute(
                    "INSERT INTO host_compressed VALUES (?, ?, ?, ?)",
                    [host, "_class_instances", json.dumps(section_data, default=str), 0],
                )
                continue

            section_count += 1
            delta_size = _count_delta_fields(section_data)
            total_delta += delta_size

            conn.execute(
                "INSERT INTO host_compressed VALUES (?, ?, ?, ?)",
                [host, section, json.dumps(section_data, default=str), delta_size],
            )

            # Collect class refs
            refs = _extract_class_refs(section_data)
            all_refs |= refs
            for cls in refs:
                conn.execute(
                    "INSERT OR IGNORE INTO class_members VALUES (?, ?, ?)",
                    [cls, host, section],
                )

        # Also count _class_instances sections
        if isinstance(class_instances, list):
            section_count += len(class_instances)

        is_zero_delta = total_delta == 0 and all(
            section == "_class_instances" or (
                isinstance(host_data[section], dict)
                and set(host_data[section].keys()) == {"_class"}
            )
            for section in host_data
            if section != "_class_instances"
        )

        class_profile = ",".join(sorted(all_refs))
        conn.execute(
            "INSERT INTO host_meta VALUES (?, ?, ?, ?, ?)",
            [host, class_profile, total_delta, section_count, is_zero_delta],
        )


# ---------------------------------------------------------------------------
# Convenience entry points
# ---------------------------------------------------------------------------

def compress_to_file(
    inputs: dict[str, dict[str, Any]],
    output_path: str,
    *,
    threshold: float = 100.0,
    max_delta_pct: float = 20.0,
    min_group_size: int = 3,
    on_host: Callable[[int, int], None] | None = None,
    on_section: Callable[[str, str], None] | None = None,
    workers: int | None = None,
) -> CompressedFleet:
    """Compress fleet and persist to disk.  Returns queryable handle."""
    from decoct.compress import compress

    tier_b, tier_c = compress(
        inputs,
        threshold=threshold,
        max_delta_pct=max_delta_pct,
        min_group_size=min_group_size,
        on_host=on_host,
        on_section=on_section,
        workers=workers,
    )
    return CompressedFleet.from_results(output_path, tier_b, tier_c)
