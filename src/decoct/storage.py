"""DuckDB columnar storage backend for the compression engine.

Replaces in-memory nested dicts with columnar storage to reduce peak
memory at fleet scale (100K+ devices).
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from typing import Any

import duckdb

_INSERT_CHUNK_SIZE = 500


def _flatten_for_storage(d: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    """Flatten nested dict to ``[(dotted.path, leaf_value), ...]``; lists are leaves."""
    result: list[tuple[str, Any]] = []
    for key, value in d.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and value:
            result.extend(_flatten_for_storage(value, path))
        else:
            result.append((path, value))
    return result


def _unflatten(flat: dict[str, Any]) -> dict[str, Any]:
    """Reverse of flatten: dotted paths → nested dict."""
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


def _serialise_value(v: Any) -> tuple[str, str, int]:
    """Return (value_type, value_repr, value_hash) for a Python value."""
    vtype = type(v).__name__
    vrepr = json.dumps(v, sort_keys=True, separators=(",", ":"))
    vhash = hash((vtype, vrepr))
    return vtype, vrepr, vhash


def _deserialise_value(value_type: str, value_repr: str) -> Any:
    """Reconstruct a Python value from its stored type and JSON string."""
    val = json.loads(value_repr)
    if value_type == "tuple" and isinstance(val, list):
        val = tuple(val)
    return val


def _sql_escape(s: str) -> str:
    """Escape single quotes for SQL string literals."""
    return s.replace("'", "''")


class DuckDBStore:
    """Columnar storage for fleet config data backed by DuckDB."""

    def __init__(self, path: str = ":memory:") -> None:
        self._path = path
        self._conn = duckdb.connect(path)
        self._conn.execute("""
            CREATE TABLE host_data (
                host       TEXT NOT NULL,
                section    TEXT NOT NULL,
                path       TEXT NOT NULL,
                value_type TEXT NOT NULL,
                value_repr TEXT NOT NULL,
                value_hash BIGINT NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE TABLE section_meta (
                section   TEXT PRIMARY KEY,
                data_type TEXT NOT NULL
            )
        """)
        self._pending_rows: list[tuple[str, str, str, str, str, int]] = []
        self._section_meta_cache: dict[str, str] = {}
        self._flushed = True
        self._temp_file: str | None = None

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest_host(self, hostname: str, sections: dict[str, Any]) -> None:
        """Flatten and buffer one host's sections for bulk insert."""
        for section, data in sections.items():
            if isinstance(data, list) and len(data) > 0 and all(isinstance(item, dict) for item in data):
                self._track_section_meta(section, "list_of_dicts")
                for idx, item in enumerate(data):
                    for field, value in item.items():
                        path = f"[{idx}].{field}"
                        vtype, vrepr, vhash = _serialise_value(value)
                        self._pending_rows.append((hostname, section, path, vtype, vrepr, vhash))
            elif isinstance(data, dict):
                self._track_section_meta(section, "dict")
                for path, value in _flatten_for_storage(data):
                    vtype, vrepr, vhash = _serialise_value(value)
                    self._pending_rows.append((hostname, section, path, vtype, vrepr, vhash))
            else:
                self._track_section_meta(section, "scalar")
                vtype, vrepr, vhash = _serialise_value(data)
                self._pending_rows.append((hostname, section, "", vtype, vrepr, vhash))

        self._flushed = False

    def ingest_fleet(
        self,
        inputs: dict[str, dict[str, Any]],
        on_host: Callable[[int, int], None] | None = None,
    ) -> None:
        """Convenience: ingest all hosts from the legacy dict format."""
        total = len(inputs)
        for i, (hostname, sections) in enumerate(inputs.items()):
            self.ingest_host(hostname, sections)
            if on_host:
                on_host(i + 1, total)
        self._flush()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_sections(self) -> list[str]:
        """All distinct section names, sorted."""
        self._ensure_flushed()
        result = self._conn.execute(
            "SELECT DISTINCT section FROM host_data ORDER BY section"
        ).fetchall()
        return [row[0] for row in result]

    def get_hosts_for_section(self, section: str) -> list[str]:
        """All hosts that have data for the given section, sorted."""
        self._ensure_flushed()
        result = self._conn.execute(
            "SELECT DISTINCT host FROM host_data WHERE section = ? ORDER BY host",
            [section],
        ).fetchall()
        return [row[0] for row in result]

    def get_flat(self, section: str, hosts: list[str] | None = None) -> dict[str, dict[str, Any]]:
        """Return ``{host: {path: value}}`` for a dict section.

        This is the bridge method replacing inline ``_flatten()`` calls
        in the compression engine.
        """
        self._ensure_flushed()
        if hosts is not None:
            result = self._conn.execute(
                "SELECT host, path, value_type, value_repr FROM host_data "
                "WHERE section = ? AND host IN (SELECT unnest(?::TEXT[])) ORDER BY host, path",
                [section, hosts],
            ).fetchall()
        else:
            result = self._conn.execute(
                "SELECT host, path, value_type, value_repr FROM host_data "
                "WHERE section = ? ORDER BY host, path",
                [section],
            ).fetchall()

        flat: dict[str, dict[str, Any]] = {}
        for host, path, vtype, vrepr in result:
            if host not in flat:
                flat[host] = {}
            flat[host][path] = _deserialise_value(vtype, vrepr)
        return flat

    def get_section_data(self, section: str, host: str) -> Any:
        """Reconstruct the original data for one host+section."""
        self._ensure_flushed()
        meta_type = self.get_section_type(section)

        rows = self._conn.execute(
            "SELECT path, value_type, value_repr FROM host_data "
            "WHERE section = ? AND host = ? ORDER BY path",
            [section, host],
        ).fetchall()

        if not rows:
            return {}

        if meta_type == "scalar":
            return _deserialise_value(rows[0][1], rows[0][2])

        if meta_type == "list_of_dicts":
            return self._reconstruct_list(rows)

        # dict section
        flat: dict[str, Any] = {}
        for path, vtype, vrepr in rows:
            flat[path] = _deserialise_value(vtype, vrepr)
        return _unflatten(flat)

    def is_list_section(self, section: str) -> bool:
        """True if this section was detected as list-of-dicts at ingestion time."""
        return self.get_section_type(section) == "list_of_dicts"

    def get_section_type(self, section: str) -> str:
        """Get the data_type for a section from section_meta."""
        if section in self._section_meta_cache:
            return self._section_meta_cache[section]
        self._ensure_flushed()
        result = self._conn.execute(
            "SELECT data_type FROM section_meta WHERE section = ?",
            [section],
        ).fetchone()
        if result is None:
            return "dict"
        return str(result[0])

    def close(self) -> None:
        """Close the DuckDB connection and clean up temp files."""
        self._conn.close()
        if self._temp_file is not None:
            try:
                os.unlink(self._temp_file)
            except OSError:
                pass
            self._temp_file = None

    @classmethod
    def from_connection(cls, conn: duckdb.DuckDBPyConnection) -> DuckDBStore:
        """Create store from an existing connection (for worker processes)."""
        instance = cls.__new__(cls)
        instance._path = ""
        instance._conn = conn
        instance._pending_rows = []
        instance._section_meta_cache = {}
        instance._flushed = True
        instance._temp_file = None
        return instance

    def ensure_file_backed(self) -> str:
        """Export to a temp file for parallel worker access.

        If in-memory, creates a temp file copy and returns its path.
        If already file-backed, returns the existing path.
        The temp file is cleaned up when :meth:`close` is called.
        """
        self._ensure_flushed()

        if self._temp_file is not None:
            return self._temp_file

        if self._path != ":memory:":
            return self._path

        fd, tmp_path = tempfile.mkstemp(suffix=".duckdb")
        os.close(fd)
        os.unlink(tmp_path)

        safe_path = tmp_path.replace("'", "''")
        self._conn.execute(f"ATTACH '{safe_path}' AS _export_db")
        self._conn.execute(
            "CREATE TABLE _export_db.host_data AS SELECT * FROM host_data"
        )
        self._conn.execute(
            "CREATE TABLE _export_db.section_meta AS SELECT * FROM section_meta"
        )
        self._conn.execute("DETACH _export_db")

        self._temp_file = tmp_path
        return tmp_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _track_section_meta(self, section: str, data_type: str) -> None:
        """Track section metadata in cache; conflicts resolve to 'scalar'."""
        existing = self._section_meta_cache.get(section)
        if existing is None:
            self._section_meta_cache[section] = data_type
        elif existing != data_type:
            self._section_meta_cache[section] = "scalar"

    def _flush(self) -> None:
        """Bulk-insert all pending rows into DuckDB via SQL VALUES."""
        if self._flushed:
            return

        # Write section_meta
        for section, data_type in self._section_meta_cache.items():
            self._conn.execute(
                "INSERT OR REPLACE INTO section_meta VALUES (?, ?)",
                [section, data_type],
            )

        # Bulk insert host_data via chunked SQL VALUES
        rows = self._pending_rows
        for start in range(0, len(rows), _INSERT_CHUNK_SIZE):
            chunk = rows[start : start + _INSERT_CHUNK_SIZE]
            vals = ",".join(
                f"('{_sql_escape(r[0])}','{_sql_escape(r[1])}','{_sql_escape(r[2])}',"
                f"'{_sql_escape(r[3])}','{_sql_escape(r[4])}',{r[5]})"
                for r in chunk
            )
            self._conn.execute(f"INSERT INTO host_data VALUES {vals}")
        self._pending_rows.clear()

        # Create indexes after bulk load
        try:
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_host_section ON host_data(host, section)")
        except duckdb.CatalogException:
            pass
        try:
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_section_path ON host_data(section, path)")
        except duckdb.CatalogException:
            pass

        self._flushed = True

    def _ensure_flushed(self) -> None:
        """Flush pending rows if any."""
        if not self._flushed:
            self._flush()

    @staticmethod
    def _reconstruct_list(rows: list[tuple[str, str, str]]) -> list[dict[str, Any]]:
        """Reconstruct a list-of-dicts from ``[idx].field`` paths."""
        items: dict[int, dict[str, Any]] = {}
        for path, vtype, vrepr in rows:
            bracket_end = path.index("]")
            idx = int(path[1:bracket_end])
            field = path[bracket_end + 2 :]  # skip "]."
            if idx not in items:
                items[idx] = {}
            items[idx][field] = _deserialise_value(vtype, vrepr)
        return [items[i] for i in sorted(items.keys())]
