"""Input format detection and conversion."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq


def detect_format(path: Path) -> str:
    """Detect input format from file extension.

    Returns 'json' for .json files, 'yaml' for everything else.
    """
    if path.suffix.lower() == ".json":
        return "json"
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
    else:
        yaml = YAML(typ="rt")
        doc = yaml.load(raw)

    return doc, raw
