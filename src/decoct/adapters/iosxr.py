"""IOS-XR adapter: parser and entity extraction.

Parses IOS-XR configuration files into entities with dotted-path attributes
and extracts inter-device relationships from interface/BGP descriptions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from decoct.adapters.base import BaseAdapter
from decoct.core.composite_value import CompositeValue
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import Attribute, Entity

# Section keywords that consume arguments to form path segments.
# Maps keyword -> number of args to consume (or "all" for join-with-dash).
SECTION_KEYWORDS: dict[str, str | int] = {
    "router": 2,            # router isis CORE -> router.isis.CORE
    "interface": 1,         # interface Loopback0
    "neighbor": 1,          # neighbor 10.0.0.11
    "address-family": "all",  # address-family ipv4 unicast -> address-family.ipv4-unicast
    "vrf": 1,
    "evi": 1,
    "bridge-domain": 1,
    "bridge group": 1,      # pseudo-section (two-word keyword)
    "route-policy": 1,
    "policy-map": 1,
    "dynamic-template": "all",
}

# Two-word section keywords
TWO_WORD_SECTIONS = {"bridge group"}

# Route-policy uses end-policy terminator
POLICY_TERMINATORS = {"end-policy", "end-set", "end-class-map", "end-policy-map"}

# Hostname prefix -> type hint
TYPE_HINT_PATTERNS: list[tuple[str, str]] = [
    ("P-CORE-", "iosxr-p-core"),
    ("RR-", "iosxr-rr"),
    ("APE-", "iosxr-access-pe"),
    ("BNG-", "iosxr-bng"),
    ("SVC-PE-", "iosxr-services-pe"),
]

# Pattern for extracting hostnames from descriptions
DESCRIPTION_HOSTNAME_RE = re.compile(r"TO-([A-Za-z0-9_-]+)")
PEER_DESCRIPTION_RE = re.compile(r"^([A-Za-z0-9_-]+)")


@dataclass
class ConfigNode:
    """A node in the IOS-XR config tree."""
    keyword: str
    args: list[str] = field(default_factory=list)
    depth: int = 0
    children: list[ConfigNode] = field(default_factory=list)
    annotation: str | None = None
    raw_line: str = ""
    negated: bool = False


@dataclass
class IosxrMetadata:
    """Metadata extracted from config header comments."""
    hostname: str | None = None
    platform: str | None = None
    generated_date: str | None = None


class IosxrConfigTree:
    """Parsed IOS-XR configuration tree."""

    def __init__(self, root_children: list[ConfigNode], metadata: IosxrMetadata) -> None:
        self.children = root_children
        self.metadata = metadata

    @property
    def hostname(self) -> str | None:
        """Extract hostname from config."""
        if self.metadata.hostname:
            return self.metadata.hostname
        for node in self.children:
            if node.keyword == "hostname" and node.args:
                return node.args[0]
        return None


def parse_iosxr_config(text: str) -> IosxrConfigTree:
    """Parse IOS-XR configuration text into a tree structure.

    IOS-XR uses 1-space indent per level, `!` as block terminator,
    `end` as file terminator.
    """
    lines = text.splitlines()
    metadata = IosxrMetadata()
    root_children: list[ConfigNode] = []
    pending_annotation: str | None = None

    # Stack: list of (depth, node_list) where node_list is the children list
    # to append to at each depth level.
    stack: list[tuple[int, list[ConfigNode]]] = [(-1, root_children)]

    i = 0
    while i < len(lines):
        raw_line = lines[i]
        stripped = raw_line.rstrip()
        i += 1

        # Skip empty lines
        if not stripped:
            continue

        # Handle !! header comments
        if stripped.startswith("!!"):
            content = stripped[2:].strip()
            if content.startswith("IOS XR Configuration - "):
                metadata.hostname = content.split(" - ", 1)[1].strip()
            elif content.startswith("Platform:"):
                metadata.platform = content.split(":", 1)[1].strip()
            elif content.startswith("Generated:"):
                metadata.generated_date = content.split(":", 1)[1].strip()
            continue

        # Handle ! (block terminator or comment)
        if stripped == "!":
            continue

        # Handle ! CUSTOM: annotations
        if stripped.startswith("! CUSTOM:"):
            pending_annotation = stripped[9:].strip()
            continue

        # Skip other comments
        if stripped.startswith("!"):
            continue

        # Handle end (file terminator)
        if stripped == "end":
            break

        # Calculate indentation depth (1 space = 1 level in IOS-XR)
        depth = len(raw_line) - len(raw_line.lstrip(" "))

        # Check for route-policy (special multi-line block with end-policy)
        tokens = stripped.split()
        keyword = tokens[0] if tokens else ""

        # Handle route-policy special block
        if keyword == "route-policy" and len(tokens) > 1:
            policy_name = tokens[1]
            policy_lines: list[str] = []
            while i < len(lines):
                pline = lines[i].rstrip()
                i += 1
                if pline.strip() in POLICY_TERMINATORS:
                    break
                policy_lines.append(pline.strip())

            node = ConfigNode(
                keyword="route-policy",
                args=[policy_name],
                depth=depth,
                raw_line=stripped,
                annotation=pending_annotation,
            )
            # Store policy body as child nodes
            for pl in policy_lines:
                if pl:
                    child_tokens = pl.split(None, 1)
                    child = ConfigNode(
                        keyword=child_tokens[0] if child_tokens else pl,
                        args=child_tokens[1].split() if len(child_tokens) > 1 else [],
                        depth=depth + 1,
                        raw_line=pl,
                    )
                    node.children.append(child)

            pending_annotation = None
            _place_node(stack, root_children, node, depth)
            continue

        # Parse normal line
        negated = False
        if keyword == "no" and len(tokens) > 1:
            negated = True
            tokens = tokens[1:]
            keyword = tokens[0]

        args = tokens[1:] if len(tokens) > 1 else []

        node = ConfigNode(
            keyword=keyword,
            args=args,
            depth=depth,
            raw_line=stripped,
            negated=negated,
            annotation=pending_annotation,
        )
        pending_annotation = None

        _place_node(stack, root_children, node, depth)

    return IosxrConfigTree(root_children, metadata)


def _place_node(
    stack: list[tuple[int, list[ConfigNode]]],
    root_children: list[ConfigNode],
    node: ConfigNode,
    depth: int,
) -> None:
    """Place a node in the tree based on its depth."""
    # Pop stack until we find a parent at a lower depth
    while len(stack) > 1 and stack[-1][0] >= depth:
        stack.pop()

    # Add to current parent's children
    stack[-1][1].append(node)

    # Push this node as potential parent
    stack.append((depth, node.children))


def _get_section_key(keyword: str, args: list[str]) -> tuple[str, list[str]]:
    """Determine if a keyword is a section and compute its path segment.

    Returns (path_segment, remaining_args) or ("", args) if not a section.
    """
    # Check two-word sections first
    for tw in TWO_WORD_SECTIONS:
        parts = tw.split()
        if keyword == parts[0] and args and args[0] == parts[1]:
            spec = SECTION_KEYWORDS[tw]
            remaining = args[1:]
            if spec == "all":
                segment = tw.replace(" ", "-") + "." + "-".join(remaining)
                return segment, []
            n = int(spec)
            consumed = remaining[:n]
            rest = remaining[n:]
            segment = tw.replace(" ", "-") + "." + ".".join(consumed) if consumed else tw.replace(" ", "-")
            return segment, rest

    if keyword in SECTION_KEYWORDS:
        spec = SECTION_KEYWORDS[keyword]
        if spec == "all":
            segment = keyword + "." + "-".join(args) if args else keyword
            return segment, []
        n = int(spec)
        consumed = args[:n]
        rest = args[n:]
        segment = keyword + "." + ".".join(consumed) if consumed else keyword
        return segment, rest

    return "", args


def flatten_config_tree(
    nodes: list[ConfigNode],
    prefix: str = "",
) -> dict[str, Any]:
    """Flatten a config tree into dotted-path attributes.

    Returns a dict of {dotted_path: value_string}.
    """
    attrs: dict[str, Any] = {}

    for node in nodes:
        # Try section keyword detection
        section_seg, remaining_args = _get_section_key(node.keyword, node.args)

        if section_seg and node.children:
            # This is a section node — recurse with extended prefix
            new_prefix = f"{prefix}{section_seg}." if prefix else f"{section_seg}."
            # If there are remaining args, they're a value on this section line itself
            if remaining_args:
                path = f"{prefix}{section_seg}" if prefix else section_seg
                attrs[path] = " ".join(remaining_args)
            child_attrs = flatten_config_tree(node.children, new_prefix)
            attrs.update(child_attrs)
        elif node.children:
            # Non-section node with children — use keyword as path segment
            new_prefix = f"{prefix}{node.keyword}." if prefix else f"{node.keyword}."
            if node.args:
                path = f"{prefix}{node.keyword}" if prefix else node.keyword
                attrs[path] = " ".join(node.args)
            child_attrs = flatten_config_tree(node.children, new_prefix)
            attrs.update(child_attrs)
        else:
            # Leaf node
            path = f"{prefix}{node.keyword}" if prefix else node.keyword
            if node.negated:
                attrs[path] = "false"
            elif node.args:
                attrs[path] = " ".join(node.args)
            else:
                attrs[path] = "true"

    return attrs


def _classify_attribute_type(value: Any) -> str:
    """Classify a flat attribute value into a type."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, CompositeValue):
        return value.kind
    return "string"


def _type_hint_from_hostname(hostname: str) -> str | None:
    """Derive entity type hint from hostname prefix."""
    for prefix, hint in TYPE_HINT_PATTERNS:
        if hostname.startswith(prefix):
            return hint
    return None


def _extract_p2p_refs(attrs: dict[str, Any]) -> list[tuple[str, str]]:
    """Extract p2p_link relationships from interface descriptions.

    Looks for 'TO-{hostname}' patterns in interface descriptions.
    """
    refs: list[tuple[str, str]] = []
    for path, value in attrs.items():
        if path.endswith(".description") and isinstance(value, str):
            match = DESCRIPTION_HOSTNAME_RE.search(value)
            if match:
                target = match.group(1)
                refs.append(("p2p_link", target))
    return refs


def _extract_bgp_peer_refs(attrs: dict[str, Any]) -> list[tuple[str, str]]:
    """Extract bgp_peer relationships from BGP neighbor descriptions."""
    refs: list[tuple[str, str]] = []
    for path, value in attrs.items():
        if ".neighbor." in path and path.endswith(".description") and isinstance(value, str):
            # BGP neighbor description often contains peer hostname like "RR-1", "TRANSIT-A"
            # Only extract if it looks like a device hostname
            match = PEER_DESCRIPTION_RE.match(value)
            if match:
                target = match.group(1)
                # Only add if it looks like a valid hostname
                if re.match(r"^[A-Z][A-Za-z0-9_-]+$", target):
                    refs.append(("bgp_peer", target))
    return refs


def _extract_bgp_confederation_peers(attrs: dict[str, Any]) -> list[str]:
    """Extract BGP confederation peer ASNs."""
    peers: list[str] = []
    for path, value in sorted(attrs.items()):
        # bgp confederation peers section: values are just ASN numbers
        parts = path.split(".")
        if "bgp" in parts and "confederation" in parts and "peers" in parts:
            # The peer ASNs appear as children of bgp.confederation.peers
            if value and value != "true":
                peers.append(value)
    return peers


def _collect_composite_values(
    nodes: list[ConfigNode],
    prefix: str = "",
) -> dict[str, CompositeValue]:
    """Collect composite value structures from config tree.

    Identifies BGP neighbor blocks, EVPN EVI blocks, bridge-domain blocks,
    and route-policy bodies as CompositeValue.
    """
    composites: dict[str, CompositeValue] = {}

    for node in nodes:
        if not node.children:
            continue

        section_seg, _ = _get_section_key(node.keyword, node.args)

        # BGP neighbor blocks -> CompositeValue(map)
        if node.keyword == "neighbor" and node.args:
            parent_prefix = prefix.rstrip(".")
            if "bgp" in parent_prefix or "router.bgp" in parent_prefix:
                neighbor_attrs = flatten_config_tree(node.children, "")
                neighbor_id = node.args[0]
                cv_path = f"{prefix}neighbors"
                if cv_path not in composites:
                    composites[cv_path] = CompositeValue(data={}, kind="map")
                composites[cv_path].data[neighbor_id] = neighbor_attrs

        # EVPN EVI blocks -> CompositeValue(map)
        if node.keyword == "evi" and node.args:
            parent_prefix = prefix.rstrip(".")
            if parent_prefix.endswith("evpn") or parent_prefix == "evpn":
                evi_attrs = flatten_config_tree(node.children, "")
                evi_id = node.args[0]
                cv_path = f"{prefix}evis"
                if cv_path not in composites:
                    composites[cv_path] = CompositeValue(data={}, kind="map")
                composites[cv_path].data[evi_id] = evi_attrs

        # Bridge-group blocks -> CompositeValue(map) — group-level
        # Collect entire bridge-group as composite to avoid per-device path names
        if node.keyword == "bridge" and node.args and node.args[0] == "group":
            bg_name = node.args[1] if len(node.args) > 1 else "default"
            bg_attrs = flatten_config_tree(node.children, "")
            cv_path = f"{prefix}bridge-groups"
            if cv_path not in composites:
                composites[cv_path] = CompositeValue(data={}, kind="map")
            composites[cv_path].data[bg_name] = bg_attrs

        # Bridge-domain blocks -> CompositeValue(map)
        if node.keyword == "bridge-domain" and node.args:
            bd_attrs = flatten_config_tree(node.children, "")
            bd_name = node.args[0]
            cv_path = f"{prefix}bridge-domains"
            if cv_path not in composites:
                composites[cv_path] = CompositeValue(data={}, kind="map")
            composites[cv_path].data[bd_name] = bd_attrs

        # Route-policy bodies -> CompositeValue(list)
        if node.keyword == "route-policy" and node.args:
            policy_lines = [child.raw_line for child in node.children]
            composites[f"{section_seg}.body"] = CompositeValue.from_list(policy_lines)

        # Recurse into children — for both section and non-section nodes
        if section_seg:
            new_prefix = f"{prefix}{section_seg}." if prefix else f"{section_seg}."
        else:
            new_prefix = f"{prefix}{node.keyword}." if prefix else f"{node.keyword}."
        nested = _collect_composite_values(node.children, new_prefix)
        composites.update(nested)

    return composites


class IosxrAdapter(BaseAdapter):
    """IOS-XR configuration adapter.

    Parses IOS-XR .cfg files into entities with dotted-path attributes.
    v1: each .cfg file = one entity. Canonical ID = hostname.
    """

    def source_type(self) -> str:
        return "iosxr"

    def parse(self, source: str) -> IosxrConfigTree:
        """Parse IOS-XR config from file path or text."""
        path = Path(source)
        if path.exists():
            text = path.read_text(encoding="utf-8")
        else:
            text = source
        return parse_iosxr_config(text)

    def extract_entities(self, parsed: Any, graph: EntityGraph) -> None:
        """Extract a single entity per config file into the graph."""
        tree: IosxrConfigTree = parsed
        hostname = tree.hostname
        if not hostname:
            return

        entity = Entity(id=hostname)
        entity.schema_type_hint = _type_hint_from_hostname(hostname)

        # Flatten config tree into dotted-path attributes
        flat_attrs = flatten_config_tree(tree.children)

        # Collect composite values
        composites = _collect_composite_values(tree.children)

        # Build set of path prefixes subsumed by composites
        # e.g., composite at "evpn.evis" subsumes "evpn.evi.10000.*"
        subsumed_prefixes: set[str] = set()
        for cv_path in composites:
            # Composite "evpn.evis" subsumes flat paths "evpn.evi.*"
            # Composite "X.neighbors" subsumes "X.neighbor.*"
            # Composite "X.bridge-domains" subsumes "X.bridge-domain.*"
            # Composite "X.bridge-groups" subsumes "X.bridge-group.*" (two-word section)
            if cv_path.endswith(".evis"):
                subsumed_prefixes.add(cv_path[:-1])  # evpn.evi
            elif cv_path.endswith(".neighbors"):
                subsumed_prefixes.add(cv_path[:-1])  # *.neighbor
            elif cv_path.endswith(".bridge-groups"):
                subsumed_prefixes.add(cv_path.replace("-groups", "-group."))  # *.bridge-group.
            elif cv_path.endswith(".bridge-domains"):
                subsumed_prefixes.add(cv_path.replace("-domains", "-domain."))  # *.bridge-domain.
            elif cv_path.endswith(".body"):
                # route-policy body: subsume "route-policy.NAME.*" paths
                subsumed_prefixes.add(cv_path.rsplit(".", 1)[0] + ".")

        # Add flat attributes, excluding those subsumed by composites
        for path, value in sorted(flat_attrs.items()):
            subsumed = False
            for prefix in subsumed_prefixes:
                if path.startswith(prefix):
                    subsumed = True
                    break
            if subsumed:
                continue
            attr_type = _classify_attribute_type(value)
            entity.attributes[path] = Attribute(
                path=path,
                value=value,
                type=attr_type,
                source=hostname,
            )

        # Add composite value attributes, excluding those subsumed by higher composites
        for path, cv in sorted(composites.items()):
            subsumed = False
            for prefix in subsumed_prefixes:
                if path.startswith(prefix):
                    subsumed = True
                    break
            if subsumed:
                continue
            entity.attributes[path] = Attribute(
                path=path,
                value=cv,
                type=cv.kind,
                source=hostname,
            )

        # Extract BGP confederation peers as composite
        confed_peers = _extract_bgp_confederation_peers(flat_attrs)
        if confed_peers:
            # Find the BGP confederation peers path
            for path in sorted(flat_attrs.keys()):
                if "confederation" in path and "peers" in path:
                    # Remove individual peer entries, add as composite list
                    bgp_prefix = path.rsplit(".peers", 1)[0]
                    cv_path = f"{bgp_prefix}.confederation-peers"
                    entity.attributes[cv_path] = Attribute(
                        path=cv_path,
                        value=CompositeValue.from_list(confed_peers),
                        type="list",
                        source=hostname,
                    )
                    break

        graph.add_entity(entity)

        # Extract relationships
        refs = _extract_p2p_refs(flat_attrs)
        refs.extend(_extract_bgp_peer_refs(flat_attrs))

        for label, target in refs:
            graph.add_relationship(hostname, label, target)

    def parse_and_extract(self, source: str, graph: EntityGraph) -> None:
        """Convenience: parse and extract in one call."""
        parsed = self.parse(source)
        self.extract_entities(parsed, graph)
