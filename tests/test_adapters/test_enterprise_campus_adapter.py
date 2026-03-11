"""Integration tests for HybridInfraAdapter with enterprise-campus ingestion spec."""

from __future__ import annotations

from pathlib import Path

import pytest

from decoct.adapters.hybrid_infra import HybridInfraAdapter
from decoct.adapters.ingestion_spec import load_ingestion_spec
from decoct.core.entity_graph import EntityGraph

FIXTURES = Path("tests/fixtures/enterprise-campus/configs")
SPEC_PATH = Path("specs/ingestion/enterprise-campus/ingestion_spec.yaml")


def _parse_one(
    filename: str,
    adapter: HybridInfraAdapter,
) -> tuple[EntityGraph, str]:
    graph = EntityGraph()
    parsed = adapter.parse(str(FIXTURES / filename))
    adapter.extract_entities(parsed, graph)
    entity_id = graph.entity_ids[0]
    return graph, entity_id


class TestEnterpriseCampusAdapterWithSpec:
    """Spec overrides schema_type_hint for enterprise-campus files."""

    @pytest.fixture()
    def spec_adapter(self) -> HybridInfraAdapter:
        spec = load_ingestion_spec(SPEC_PATH)
        return HybridInfraAdapter(ingestion_spec=spec)

    # ── SD-WAN domain ─────────────────────────────────────────────────────────

    def test_sdwan_cedge_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("sdwan-cedge-hq-1.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "sdwan-cedge"

    def test_sdwan_vsmart_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("sdwan-vsmart-1.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "sdwan-vsmart"

    def test_sdwan_vbond_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("sdwan-vbond-1.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "sdwan-vbond"

    def test_sdwan_policy_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("sdwan-policy-app-route.json", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "sdwan-policy"

    def test_sdwan_template_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("sdwan-template-vpn0.json", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "sdwan-template"

    # ── SD-Access domain ──────────────────────────────────────────────────────

    def test_catalyst_switch_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("catalyst-border-hq-1.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "catalyst-switch"

    def test_wlc_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("wlc-hq.json", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "wlc-config"

    def test_ap_group_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("ap-group-hq-lobby.json", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "ap-group"

    def test_ise_policy_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("ise-policy-dot1x-corp.json", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "ise-policy"

    def test_sgt_matrix_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("sgt-matrix-campus.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "sgt-matrix"

    def test_dnac_template_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("dnac-template-day0.json", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "dnac-template"

    # ── Firewall domain ───────────────────────────────────────────────────────

    def test_paloalto_fw_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("pa-fw-hq-1.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "paloalto-fw"

    def test_paloalto_profile_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("pa-profile-url-filter.json", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "paloalto-profile"

    def test_fortinet_fw_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("forti-bra.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "fortinet-fw"

    def test_fw_address_group_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("fw-addrgrp-rfc1918.json", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "fw-address-group"

    def test_fw_nat_rule_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("fw-nat-dc-ingress.json", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "fw-nat-rule"

    # ── Datacentre domain ─────────────────────────────────────────────────────

    def test_arista_leaf_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("arista-leaf-r01-1.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "arista-leaf"

    def test_arista_spine_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("arista-spine-1.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "arista-spine"

    def test_server_bmc_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("bmc-db-primary.json", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "server-bmc"

    def test_server_netplan_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("netplan-db-primary.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "server-netplan"

    def test_server_sysctl_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("sysctl-db-primary.conf", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "server-sysctl"

    def test_server_systemd_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("systemd-app-api.conf", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "server-systemd"

    def test_storage_array_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("storage-netapp-01.json", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "storage-array"

    def test_db_config_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("db-pg-primary.conf", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "db-config"

    def test_redis_config_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("redis-primary.conf", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "redis-config"

    def test_lb_config_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("lb-f5-web.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "lb-config"

    # ── IoT Factory Floor domain ──────────────────────────────────────────────

    def test_mqtt_broker_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("mqtt-plant-primary.json", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "mqtt-broker"

    def test_opcua_server_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("opcua-weld-cell-1.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "opcua-server"

    def test_plc_gateway_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("plc-gw-weld-1.json", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "plc-gateway"

    def test_edge_compute_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("edge-node-defect-1.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "edge-compute"

    def test_sensor_network_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("sensor-vibration-weld.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "sensor-network"

    def test_industrial_fw_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("ind-fw-l01.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "industrial-fw"

    def test_historian_config_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("historian-influx-plant.json", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "historian-config"


class TestEnterpriseCampusFullCorpus:
    """All 185 fixtures get a non-None schema_type_hint with spec loaded."""

    def test_full_corpus_no_unknowns(self) -> None:
        spec = load_ingestion_spec(SPEC_PATH)
        adapter = HybridInfraAdapter(ingestion_spec=spec)

        all_files = sorted(FIXTURES.iterdir())
        assert len(all_files) == 185

        missing_hints: list[str] = []
        for f in all_files:
            graph = EntityGraph()
            parsed = adapter.parse(str(f))
            adapter.extract_entities(parsed, graph)
            entity = graph.get_entity(f.stem)
            if entity.schema_type_hint is None:
                missing_hints.append(f.name)

        assert missing_hints == [], f"Files without schema_type_hint: {missing_hints}"
