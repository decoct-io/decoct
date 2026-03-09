"""Input format detection and conversion."""

from __future__ import annotations

import configparser
import json
import re
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

_INI_EXTENSIONS = {".ini", ".conf", ".cfg", ".cnf", ".properties"}


def detect_format(path: Path) -> str:
    """Detect input format from file extension.

    Returns 'json' for .json files, 'ini' for INI/config files, 'yaml' for everything else.
    """
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in _INI_EXTENSIONS:
        return "ini"
    return "yaml"


def json_to_commented_map(data: Any) -> Any:
    """Recursively convert JSON-parsed data to ruamel.yaml round-trip types.

    dicts → CommentedMap, lists → CommentedSeq, scalars pass through.
    """
    if isinstance(data, dict):
        cm = CommentedMap()
        for key, value in data.items():
            cm[key] = json_to_commented_map(value)
        return cm
    if isinstance(data, list):
        cs = CommentedSeq()
        for item in data:
            cs.append(json_to_commented_map(item))
        return cs
    return data


def _coerce_ini_value(value: str) -> Any:
    """Coerce an INI string value to a native Python type.

    Detects booleans (true/false/yes/no/on/off), integers, and floats.
    Leaves everything else as a string.
    """
    lower = value.lower()
    if lower in ("true", "yes", "on"):
        return True
    if lower in ("false", "no", "off"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _has_sections(text: str) -> bool:
    """Return True if the text contains INI-style [section] headers."""
    return bool(re.search(r"^\[.+\]\s*$", text, re.MULTILINE))


def ini_to_commented_map(text: str) -> CommentedMap:
    """Convert INI or flat key=value text to a CommentedMap.

    Sectioned INI files produce a nested CommentedMap (section → keys).
    Flat key=value files (no sections) produce a flat CommentedMap.
    """
    if _has_sections(text):
        return _parse_sectioned_ini(text)
    return _parse_flat_keyvalue(text)


def _parse_sectioned_ini(text: str) -> CommentedMap:
    """Parse standard INI with [section] headers using configparser."""
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(text)

    cm = CommentedMap()
    for section in parser.sections():
        section_map = CommentedMap()
        for key, value in parser.items(section):
            section_map[key] = _coerce_ini_value(value)
        cm[section] = section_map
    return cm


def _parse_flat_keyvalue(text: str) -> CommentedMap:
    """Parse flat key=value format (no sections). Skips comments and blank lines."""
    cm = CommentedMap()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()
        if key:
            cm[key] = _coerce_ini_value(value)
    return cm


def detect_platform(doc: Any) -> str | None:
    """Detect the platform from document content.

    Returns a bundled schema name or None if unrecognised.
    """
    # Ansible playbook: list of plays with hosts + tasks/roles
    if isinstance(doc, list) and len(doc) > 0:
        first = doc[0]
        if isinstance(first, dict) and "hosts" in first and ("tasks" in first or "roles" in first):
            return "ansible-playbook"

    if not isinstance(doc, dict):
        return None

    # Docker Compose: has "services" key with nested mappings
    if "services" in doc and isinstance(doc.get("services"), dict):
        return "docker-compose"

    # Terraform state: has "version", "resources", "terraform_version"
    if "terraform_version" in doc and "resources" in doc:
        return "terraform-state"

    # cloud-init: common cloud-init keys
    cloud_init_keys = {"packages", "runcmd", "write_files", "users", "ssh_authorized_keys", "growpart", "ntp"}
    if len(cloud_init_keys & set(doc.keys())) >= 2:
        return "cloud-init"

    # Kubernetes: has apiVersion + kind
    if "apiVersion" in doc and "kind" in doc:
        return "kubernetes"

    # GitHub Actions: has "on" (trigger) and "jobs" keys
    if "on" in doc and "jobs" in doc:
        return "github-actions"

    # Traefik: has "entryPoints" or ("providers" and ("api" or "log"))
    if "entryPoints" in doc or ("providers" in doc and ("api" in doc or "log" in doc)):
        return "traefik"

    # Prometheus: has "scrape_configs" key
    if "scrape_configs" in doc:
        return "prometheus"

    return None


def load_input(path: Path) -> tuple[Any, str]:
    """Load an input file, auto-detecting format.

    Returns (document, raw_text) tuple. JSON files are converted to
    CommentedMap/CommentedSeq for pipeline compatibility.
    """
    raw = path.read_text()
    fmt = detect_format(path)

    if fmt == "json":
        data = json.loads(raw)
        doc = json_to_commented_map(data)
    elif fmt == "ini":
        doc = ini_to_commented_map(raw)
    else:
        yaml = YAML(typ="rt")
        doc = yaml.load(raw)

    return doc, raw
