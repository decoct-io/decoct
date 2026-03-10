"""Tests for Entra ID / Intune adapter: per-type and relationship validation."""

from pathlib import Path

import pytest

from decoct.adapters.entra_intune import (
    ODATA_TYPE_MAP,
    EntraIntuneAdapter,
    flatten_json,
)
from decoct.core.composite_value import CompositeValue
from decoct.core.entity_graph import EntityGraph

FIXTURES = Path("tests/fixtures/entra-intune/resources")


class TestParseByType:
    """One test per entity type prefix."""

    def _parse_one(self, filename: str) -> tuple[EntityGraph, str]:
        adapter = EntraIntuneAdapter()
        graph = EntityGraph()
        adapter.parse_and_extract(str(FIXTURES / filename), graph)
        entity_id = graph.entity_ids[0]
        return graph, entity_id

    def test_parse_ca_policy(self) -> None:
        graph, eid = self._parse_one("ca-ca-mfa-global-admins.json")
        e = graph.get_entity(eid)
        assert eid == "CA-MFA-Global-Admins"
        assert e.schema_type_hint == "entra-conditional-access"
        assert e.attributes["state"].value == "enabled"
        assert "conditions.users.includeGroups" in e.attributes
        assert "grantControls.operator" in e.attributes

    def test_parse_group(self) -> None:
        graph, eid = self._parse_one("grp-sg-finance-users.json")
        e = graph.get_entity(eid)
        assert eid == "SG-Finance-Users"
        assert e.schema_type_hint == "entra-group"
        assert e.attributes["securityEnabled"].value == "true"
        assert e.attributes["mailEnabled"].value == "false"
        # Null fields should be filtered
        assert "membershipRule" not in e.attributes
        assert "mail" not in e.attributes
        assert "visibility" not in e.attributes

    def test_parse_compliance(self) -> None:
        graph, eid = self._parse_one("compliance-cp-win-basic-security.json")
        e = graph.get_entity(eid)
        assert eid == "CP-Win-Basic-Security"
        assert e.schema_type_hint == "intune-compliance"
        assert e.attributes["passwordRequired"].value == "false"
        # Assignments as CompositeValue
        assert "assignments" in e.attributes
        cv = e.attributes["assignments"].value
        assert isinstance(cv, CompositeValue)
        assert cv.kind == "list"

    def test_parse_application(self) -> None:
        graph, eid = self._parse_one("app-app-api-backend.json")
        e = graph.get_entity(eid)
        assert eid == "App-API-Backend"
        assert e.schema_type_hint == "entra-application"
        assert "api.requestedAccessTokenVersion" in e.attributes
        # OAuth2 scopes as composite map
        assert "api.oauth2PermissionScopes" in e.attributes
        cv = e.attributes["api.oauth2PermissionScopes"].value
        assert isinstance(cv, CompositeValue)
        assert cv.kind == "map"
        assert "access_as_user" in cv.data
        assert "read_all" in cv.data

    def test_parse_named_location_ip(self) -> None:
        graph, eid = self._parse_one("namedloc-nl-corporate-hq.json")
        e = graph.get_entity(eid)
        assert eid == "NL-Corporate-HQ"
        assert e.schema_type_hint == "entra-named-location"
        assert e.attributes["isTrusted"].value == "true"
        assert "ipRanges" in e.attributes
        cv = e.attributes["ipRanges"].value
        assert isinstance(cv, CompositeValue)

    def test_parse_named_location_country(self) -> None:
        graph, eid = self._parse_one("namedloc-nl-blocked-countries.json")
        e = graph.get_entity(eid)
        assert eid == "NL-Blocked-Countries"
        assert e.schema_type_hint == "entra-named-location"
        assert "countriesAndRegions" in e.attributes
        assert "KP" in e.attributes["countriesAndRegions"].value

    def test_parse_cta(self) -> None:
        graph, eid = self._parse_one("cta-cta-partner-contoso.json")
        e = graph.get_entity(eid)
        assert eid == "CTA-Partner-Contoso"
        assert e.schema_type_hint == "entra-cross-tenant"
        assert "tenantId" in e.attributes
        assert "b2bCollaborationInbound.applications.accessType" in e.attributes
        assert "inboundTrust.isMfaAccepted" in e.attributes

    def test_parse_app_protection(self) -> None:
        graph, eid = self._parse_one("appprotect-ap-android-standard.json")
        e = graph.get_entity(eid)
        assert eid == "AP-Android-Standard"
        assert e.schema_type_hint == "intune-app-protection"
        assert e.attributes["pinRequired"].value == "true"
        assert "apps" in e.attributes
        cv = e.attributes["apps"].value
        assert isinstance(cv, CompositeValue)

    def test_parse_device_config(self) -> None:
        graph, eid = self._parse_one("devconfig-dc-android-standard.json")
        e = graph.get_entity(eid)
        assert eid == "DC-Android-Standard"
        assert e.schema_type_hint == "intune-device-config"
        assert e.attributes["cameraBlocked"].value == "false"
        assert "assignments" in e.attributes


class TestNullAndEmptyFiltering:
    """Verify null, empty array, and empty object filtering."""

    def test_null_filtered(self) -> None:
        flat, _ = flatten_json({"displayName": "test", "foo": None})
        assert "foo" not in flat

    def test_empty_list_filtered(self) -> None:
        flat, _ = flatten_json({"displayName": "test", "foo": []})
        assert "foo" not in flat

    def test_empty_dict_filtered(self) -> None:
        flat, _ = flatten_json({"displayName": "test", "foo": {}})
        assert "foo" not in flat

    def test_nested_all_null_filtered(self) -> None:
        flat, _ = flatten_json({
            "displayName": "test",
            "nested": {"a": None, "b": [], "c": {}},
        })
        assert not any(k.startswith("nested") for k in flat)

    def test_scalars_preserved(self) -> None:
        flat, _ = flatten_json({
            "displayName": "test",
            "name": "value",
            "count": 42,
            "enabled": True,
        })
        assert flat["name"] == "value"
        assert flat["count"] == "42"
        assert flat["enabled"] == "true"


class TestTypeHintMapping:
    """Verify all 13 @odata.type values map correctly."""

    @pytest.mark.parametrize("odata_type,expected_type", [
        ("#microsoft.graph.conditionalAccessPolicy", "entra-conditional-access"),
        ("#microsoft.graph.group", "entra-group"),
        ("#microsoft.graph.application", "entra-application"),
        ("#microsoft.graph.windows10CompliancePolicy", "intune-compliance"),
        ("#microsoft.graph.iosCompliancePolicy", "intune-compliance"),
        ("#microsoft.graph.androidCompliancePolicy", "intune-compliance"),
        ("#microsoft.graph.macOSCompliancePolicy", "intune-compliance"),
        ("#microsoft.graph.androidGeneralDeviceConfiguration", "intune-device-config"),
        ("#microsoft.graph.androidManagedAppProtection", "intune-app-protection"),
        ("#microsoft.graph.iosManagedAppProtection", "intune-app-protection"),
        ("#microsoft.graph.ipNamedLocation", "entra-named-location"),
        ("#microsoft.graph.countryNamedLocation", "entra-named-location"),
        ("#microsoft.graph.crossTenantAccessPolicyConfigurationPartner", "entra-cross-tenant"),
    ])
    def test_type_mapping(self, odata_type: str, expected_type: str) -> None:
        assert ODATA_TYPE_MAP[odata_type] == expected_type


class TestRelationshipExtraction:
    """Verify relationships are correctly extracted."""

    def _parse_all(self) -> tuple[EntraIntuneAdapter, EntityGraph]:
        adapter = EntraIntuneAdapter()
        graph = EntityGraph()
        for f in sorted(FIXTURES.glob("*.json")):
            adapter.parse_and_extract(str(f), graph)
        adapter.extract_relationships(graph)
        return adapter, graph

    def test_ca_group_ref_relationships(self) -> None:
        _, graph = self._parse_all()
        rels = graph.relationships_from("CA-Compliant-Device-Internal")
        group_refs = [(lbl, t) for lbl, t in rels if lbl == "group_ref"]
        targets = {t for _, t in group_refs}
        assert "SG-Engineering" in targets
        assert "SG-Finance-Users" in targets

    def test_assignment_relationship(self) -> None:
        _, graph = self._parse_all()
        rels = graph.relationships_from("CP-Win-Basic-Security")
        assignment_targets = [(lbl, t) for lbl, t in rels if lbl == "assignment_target"]
        targets = {t for _, t in assignment_targets}
        assert "DG-All-Corp-Windows" in targets

    def test_cta_tenant_ref(self) -> None:
        _, graph = self._parse_all()
        rels = graph.relationships_from("CTA-Partner-Contoso")
        tenant_refs = [(lbl, t) for lbl, t in rels if lbl == "tenant_ref"]
        assert len(tenant_refs) == 1
        assert tenant_refs[0][1] == "72f988bf-86f1-41af-91ab-2d7cd011db47"

    def test_cta_default_no_tenant_ref(self) -> None:
        _, graph = self._parse_all()
        rels = graph.relationships_from("CTA-Default-Settings")
        tenant_refs = [(lbl, t) for lbl, t in rels if lbl == "tenant_ref"]
        assert len(tenant_refs) == 0
