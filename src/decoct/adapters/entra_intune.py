"""Entra ID / Intune adapter: parser and entity extraction.

Parses Microsoft Entra ID and Intune JSON exports (Graph API format)
into entities with dotted-path attributes and extracts inter-entity
relationships from group references and policy assignments.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from decoct.adapters.base import BaseAdapter
from decoct.core.composite_value import CompositeValue
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import Attribute, Entity

# @odata.type → entity type ID
ODATA_TYPE_MAP: dict[str, str] = {
    "#microsoft.graph.conditionalAccessPolicy": "entra-conditional-access",
    "#microsoft.graph.group": "entra-group",
    "#microsoft.graph.application": "entra-application",
    "#microsoft.graph.windows10CompliancePolicy": "intune-compliance",
    "#microsoft.graph.iosCompliancePolicy": "intune-compliance",
    "#microsoft.graph.androidCompliancePolicy": "intune-compliance",
    "#microsoft.graph.macOSCompliancePolicy": "intune-compliance",
    "#microsoft.graph.androidGeneralDeviceConfiguration": "intune-device-config",
    "#microsoft.graph.androidManagedAppProtection": "intune-app-protection",
    "#microsoft.graph.iosManagedAppProtection": "intune-app-protection",
    "#microsoft.graph.ipNamedLocation": "entra-named-location",
    "#microsoft.graph.countryNamedLocation": "entra-named-location",
    "#microsoft.graph.crossTenantAccessPolicyConfigurationPartner": "entra-cross-tenant",
}

# Metadata fields stripped before flattening — not useful for compression
SKIP_FIELDS: set[str] = {
    "@odata.type",
    "id",
    "createdDateTime",
    "modifiedDateTime",
    "deletedDateTime",
    "renewedDateTime",
}

# Top-level array fields that contain objects → CompositeValue
COMPOSITE_ARRAY_FIELDS: set[str] = {
    "assignments",
    "apps",
    "oauth2PermissionScopes",
    "ipRanges",
    "scheduledActionsForRule",
    "requiredResourceAccess",
    "passwordCredentials",
    "keyCredentials",
    "appRoles",
}


def _is_empty(value: Any) -> bool:
    """Check if a value should be filtered out (null, empty array, empty object)."""
    if value is None:
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    if isinstance(value, dict) and len(value) == 0:
        return True
    return False


def _value_to_str(value: Any) -> str:
    """Convert a scalar value to string, matching IOS-XR adapter convention."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def flatten_json(
    obj: dict[str, Any],
    prefix: str = "",
    skip_fields: set[str] | None = None,
) -> tuple[dict[str, str], dict[str, CompositeValue]]:
    """Flatten a JSON object into dotted-path attributes.

    Returns:
        (flat_attrs, composites) — flat scalar attributes and composite values.
    """
    if skip_fields is None:
        skip_fields = SKIP_FIELDS

    flat: dict[str, str] = {}
    composites: dict[str, CompositeValue] = {}

    for key, value in obj.items():
        if key in skip_fields:
            continue

        path = f"{prefix}{key}" if prefix else key

        if _is_empty(value):
            continue

        if isinstance(value, dict):
            child_flat, child_composites = flatten_json(value, f"{path}.", skip_fields=set())
            if child_flat or child_composites:
                flat.update(child_flat)
                composites.update(child_composites)

        elif isinstance(value, list):
            if _is_scalar_list(value):
                # Simple array of scalars → comma-separated string
                flat[path] = ", ".join(_value_to_str(v) for v in value)
            elif key in COMPOSITE_ARRAY_FIELDS or prefix == "":
                # Array of objects at known fields or top level → CompositeValue
                composites[path] = _build_composite(key, value)
            else:
                # Nested array of objects → also CompositeValue
                composites[path] = _build_composite(key, value)

        else:
            flat[path] = _value_to_str(value)

    return flat, composites


def _is_scalar_list(items: list[Any]) -> bool:
    """Check if a list contains only scalars (str, int, float, bool)."""
    return all(isinstance(v, (str, int, float, bool)) for v in items)


def _build_composite(key: str, items: list[Any]) -> CompositeValue:
    """Build a CompositeValue from a list of objects.

    oauth2PermissionScopes → map keyed by 'value' field.
    Everything else → list (positional).
    """
    if key == "oauth2PermissionScopes":
        data: dict[str, Any] = {}
        for item in items:
            if isinstance(item, dict):
                scope_key = item.get("value", str(len(data)))
                scope_attrs = _flatten_composite_item(item, skip={"value", "id", "@odata.type"})
                data[scope_key] = scope_attrs
        return CompositeValue(data=data, kind="map")

    # Default: positional list
    entries: list[Any] = []
    for item in items:
        if isinstance(item, dict):
            entries.append(_flatten_composite_item(item, skip={"@odata.type", "id"}))
        else:
            entries.append(_value_to_str(item))
    return CompositeValue(data=entries, kind="list")


def _flatten_composite_item(item: dict[str, Any], skip: set[str] | None = None) -> dict[str, str]:
    """Flatten a single composite item into string-valued dict."""
    if skip is None:
        skip = set()
    result: dict[str, str] = {}
    for k, v in item.items():
        if k in skip:
            continue
        if _is_empty(v):
            continue
        if isinstance(v, dict):
            for ck, cv in v.items():
                if ck in {"@odata.type", "id"}:
                    continue
                if not _is_empty(cv):
                    result[f"{k}.{ck}"] = _value_to_str(cv)
        elif isinstance(v, list):
            if _is_scalar_list(v) and v:
                result[k] = ", ".join(_value_to_str(x) for x in v)
            elif v:
                for i, entry in enumerate(v):
                    if isinstance(entry, dict):
                        for ek, ev in entry.items():
                            if ek in {"@odata.type", "id"}:
                                continue
                            if not _is_empty(ev):
                                result[f"{k}.{i}.{ek}"] = _value_to_str(ev)
                    elif not _is_empty(entry):
                        result[f"{k}.{i}"] = _value_to_str(entry)
        else:
            result[k] = _value_to_str(v)
    return result


def _extract_group_refs_from_ca(
    flat_attrs: dict[str, str],
    graph: EntityGraph,
) -> list[tuple[str, str]]:
    """Extract group_ref relationships from CA policy group references.

    CA policies reference groups by displayName in includeGroups/excludeGroups.
    """
    refs: list[tuple[str, str]] = []
    group_ref_paths = {
        "conditions.users.includeGroups",
        "conditions.users.excludeGroups",
        "conditions.users.excludeUsers",
    }
    for path, value in flat_attrs.items():
        if path in group_ref_paths:
            for name in value.split(", "):
                name = name.strip()
                if name and graph.has_entity(name):
                    refs.append(("group_ref", name))
    return refs


def _extract_assignment_refs(
    composites: dict[str, CompositeValue],
    uuid_to_display: dict[str, str],
) -> list[tuple[str, str]]:
    """Extract assignment_target relationships from assignment composites.

    Intune policies reference groups by UUID groupId in assignments.
    """
    refs: list[tuple[str, str]] = []
    cv = composites.get("assignments")
    if cv is None or not isinstance(cv.data, list):
        return refs

    for item in cv.data:
        if not isinstance(item, dict):
            continue
        group_id = item.get("target.groupId")
        if group_id and group_id in uuid_to_display:
            refs.append(("assignment_target", uuid_to_display[group_id]))
    return refs


def _extract_cta_refs(flat_attrs: dict[str, str]) -> list[tuple[str, str]]:
    """Extract tenant_ref relationships from CTA tenantId."""
    tenant_id = flat_attrs.get("tenantId")
    if tenant_id and tenant_id != "00000000-0000-0000-0000-000000000000":
        return [("tenant_ref", tenant_id)]
    return []


class EntraIntuneAdapter(BaseAdapter):
    """Entra ID / Intune JSON adapter.

    Parses Microsoft Graph API JSON exports into entities with dotted-path
    attributes. Each JSON file = one entity. Canonical ID = displayName.
    """

    def source_type(self) -> str:
        return "entra-intune"

    def parse(self, source: str) -> dict[str, Any]:
        """Parse JSON from file path or raw string."""
        path = Path(source)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
        return json.loads(source)  # type: ignore[no-any-return]

    def extract_entities(self, parsed: Any, graph: EntityGraph) -> None:
        """Extract a single entity from a parsed JSON object into the graph."""
        if not isinstance(parsed, dict):
            return

        display_name = parsed.get("displayName")
        if not display_name:
            return

        odata_type = parsed.get("@odata.type", "")
        type_hint = ODATA_TYPE_MAP.get(odata_type)

        entity = Entity(id=display_name)
        entity.schema_type_hint = type_hint

        # Flatten JSON to dotted paths
        flat_attrs, composites = flatten_json(parsed)

        # Store UUID for relationship resolution
        uuid = parsed.get("id", "")
        if uuid:
            entity.attributes["_uuid"] = Attribute(
                path="_uuid", value=uuid, type="string", source=display_name,
            )

        # Add flat attributes
        for path, value in sorted(flat_attrs.items()):
            entity.attributes[path] = Attribute(
                path=path, value=value, type="string", source=display_name,
            )

        # Add composite value attributes
        for path, cv in sorted(composites.items()):
            entity.attributes[path] = Attribute(
                path=path, value=cv, type=cv.kind, source=display_name,
            )

        graph.add_entity(entity)

    def extract_relationships(self, graph: EntityGraph) -> None:
        """Extract relationships after all entities have been parsed.

        Two-pass approach: entities must all be in the graph first so we can
        build the UUID→displayName lookup for assignment resolution.
        """
        # Build UUID → displayName lookup from all entities
        uuid_to_display: dict[str, str] = {}
        for entity in graph.entities:
            uuid_attr = entity.attributes.get("_uuid")
            if uuid_attr:
                uuid_to_display[uuid_attr.value] = entity.id

        for entity in graph.entities:
            flat_attrs: dict[str, str] = {}
            composites: dict[str, CompositeValue] = {}
            for path, attr in entity.attributes.items():
                if path == "_uuid":
                    continue
                if isinstance(attr.value, CompositeValue):
                    composites[path] = attr.value
                else:
                    flat_attrs[path] = attr.value

            refs: list[tuple[str, str]] = []

            if entity.schema_type_hint == "entra-conditional-access":
                refs.extend(_extract_group_refs_from_ca(flat_attrs, graph))
            elif entity.schema_type_hint in {
                "intune-compliance",
                "intune-device-config",
                "intune-app-protection",
            }:
                refs.extend(_extract_assignment_refs(composites, uuid_to_display))
            elif entity.schema_type_hint == "entra-cross-tenant":
                refs.extend(_extract_cta_refs(flat_attrs))

            for label, target in refs:
                graph.add_relationship(entity.id, label, target)

    def parse_and_extract(self, source: str, graph: EntityGraph) -> None:
        """Convenience: parse and extract in one call."""
        parsed = self.parse(source)
        self.extract_entities(parsed, graph)
