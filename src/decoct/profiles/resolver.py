"""Profile name resolution — bundled profile lookup."""

from __future__ import annotations

from pathlib import Path

_BUNDLED_DIR = Path(__file__).parent / "bundled"

BUNDLED_PROFILES: dict[str, str] = {
    "docker-compose": "docker-compose.yaml",
}


def resolve_profile(name_or_path: str) -> Path:
    """Resolve a profile name or path to a file path.

    If ``name_or_path`` matches a bundled profile short name, returns the
    path to the bundled profile file. Otherwise returns the input as a Path.

    Raises:
        KeyError: If the name looks like a short name (no path separators,
            no file extension) but doesn't match any bundled profile.
    """
    is_short_name = "/" not in name_or_path and "\\" not in name_or_path and "." not in name_or_path

    if is_short_name:
        if name_or_path in BUNDLED_PROFILES:
            return _BUNDLED_DIR / BUNDLED_PROFILES[name_or_path]
        msg = (
            f"Unknown bundled profile '{name_or_path}'. "
            f"Available: {sorted(BUNDLED_PROFILES)}"
        )
        raise KeyError(msg)

    return Path(name_or_path)
