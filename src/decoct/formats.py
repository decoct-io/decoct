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
_XML_EXTENSIONS = {".xml", ".xsl", ".xslt", ".plist", ".xhtml"}


def detect_format(path: Path) -> str:
    """Detect input format from file extension.

    Returns 'json', 'ini', 'xml', or 'yaml' (default).
    """
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in _INI_EXTENSIONS:
        return "ini"
    if suffix in _XML_EXTENSIONS:
        return "xml"
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


def _strip_ns(tag: str) -> str:
    """Strip XML namespace prefix: ``{http://...}tag`` -> ``tag``."""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def xml_to_commented_map(text: str) -> CommentedMap:
    """Convert XML text to a CommentedMap.

    Rules:
    - Namespace prefixes stripped: ``{http://ns}tag`` -> ``tag``
    - Attributes -> ``@attr_name`` keys (sorted, before child keys)
    - Repeated same-name children -> CommentedSeq
    - Text-only elements (no children, no attributes) -> scalar value
    - Mixed content (text + children) -> ``_text`` key alongside child keys
    """
    import defusedxml.ElementTree as DefusedET

    root = DefusedET.fromstring(text)
    cm = CommentedMap()
    root_tag = _strip_ns(root.tag)
    cm[root_tag] = _xml_element_to_value(root)
    return cm


def _xml_element_to_value(elem: Any) -> Any:
    """Convert a single XML element to CommentedMap, CommentedSeq, or scalar."""
    children = list(elem)
    has_attrs = len(elem.attrib) > 0
    has_children = len(children) > 0
    text = (elem.text or "").strip()

    # Text-only leaf element (no children, no attributes)
    if not has_children and not has_attrs:
        return text if text else ""

    cm = CommentedMap()

    # Attributes -> @name keys (sorted)
    if has_attrs:
        for attr_name in sorted(elem.attrib):
            cm[f"@{_strip_ns(attr_name)}"] = elem.attrib[attr_name]

    # Mixed content: text alongside children
    if text and has_children:
        cm["_text"] = text

    # Children — detect repeated names for CommentedSeq
    if has_children:
        child_order: list[str] = []
        child_groups: dict[str, list[Any]] = {}
        for child in children:
            tag = _strip_ns(child.tag)
            if tag not in child_groups:
                child_order.append(tag)
                child_groups[tag] = []
            child_groups[tag].append(child)

        for tag in child_order:
            group = child_groups[tag]
            if len(group) == 1:
                cm[tag] = _xml_element_to_value(group[0])
            else:
                cs = CommentedSeq()
                for child in group:
                    cs.append(_xml_element_to_value(child))
                cm[tag] = cs

    return cm


def detect_platform(doc: Any) -> str | None:
    """Detect the platform from document content.

    Returns a platform type name or None if unrecognised.
    """
    # Ansible playbook: list of plays with hosts + tasks/roles
    if isinstance(doc, list) and len(doc) > 0:
        first = doc[0]
        if isinstance(first, dict) and "hosts" in first and ("tasks" in first or "roles" in first):
            return "ansible-playbook"

    if not isinstance(doc, dict):
        return None

    # Docker Compose: has "services" key with at least one service containing "image"
    if "services" in doc and isinstance(doc.get("services"), dict):
        svc = doc["services"]
        if any(isinstance(v, dict) and "image" in v for v in svc.values()):
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
    elif fmt == "xml":
        doc = xml_to_commented_map(raw)
    else:
        yaml = YAML(typ="rt")
        doc = yaml.load(raw)

    return doc, raw
