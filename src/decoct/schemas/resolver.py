"""Schema name resolution — bundled schema lookup."""

from __future__ import annotations

from pathlib import Path

_BUNDLED_DIR = Path(__file__).parent / "bundled"

BUNDLED_SCHEMAS: dict[str, str] = {
    "docker-compose": "docker-compose.yaml",
    "terraform-state": "terraform-state.yaml",
    "cloud-init": "cloud-init.yaml",
    "ansible-playbook": "ansible-playbook.yaml",
    "sshd-config": "sshd-config.yaml",
    "kubernetes": "kubernetes.yaml",
}


def resolve_schema(name_or_path: str) -> Path:
    """Resolve a schema name or path to a file path.

    If ``name_or_path`` matches a bundled schema short name, returns the
    path to the bundled schema file. Otherwise returns the input as a Path.

    Raises:
        KeyError: If the name looks like a short name (no path separators,
            no file extension) but doesn't match any bundled schema.
    """
    # Check if it's a bundled short name (no slashes, no dots that look like extensions)
    is_short_name = "/" not in name_or_path and "\\" not in name_or_path and "." not in name_or_path

    if is_short_name:
        if name_or_path in BUNDLED_SCHEMAS:
            return _BUNDLED_DIR / BUNDLED_SCHEMAS[name_or_path]
        msg = (
            f"Unknown bundled schema '{name_or_path}'. "
            f"Available: {sorted(BUNDLED_SCHEMAS)}"
        )
        raise KeyError(msg)

    return Path(name_or_path)
