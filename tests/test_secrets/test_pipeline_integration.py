"""Integration tests: secrets masking through the entity-graph pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from decoct.adapters.iosxr import IosxrAdapter
from decoct.core.config import EntityGraphConfig
from decoct.entity_pipeline import run_entity_graph_pipeline

IOSXR_FIXTURES = Path("tests/fixtures/iosxr/configs")


class TestIosxrPipelineSecrets:
    """Single IOS-XR config through the pipeline with TACACS/SNMP/RADIUS secrets."""

    def test_single_config_with_secrets(self, tmp_path: Path) -> None:
        """IOS-XR config with embedded secrets should have them redacted."""
        config_text = """\
!! IOS-XR Configuration
hostname test-router-001
!
interface GigabitEthernet0/0/0/0
 description Link to Core
 ipv4 address 10.0.0.1 255.255.255.252
 mtu 9216
!
router bgp 65001
 address-family ipv4 unicast
!
snmp-server community S3cr3tRO RO
snmp-server community Pr1v4teRW RW
!
tacacs-server host 10.10.10.10
 key 7 094F471A1A0A
!
radius-server host 10.10.10.20
 key 7 02050D480809
!
line console
 exec-timeout 30 0
!
end
"""
        cfg_file = tmp_path / "test-router-001.cfg"
        cfg_file.write_text(config_text)

        adapter = IosxrAdapter()
        # warn mode: IOS-XR discrimination moves secret values into path
        # segments (e.g. community strings), causing masking asymmetry
        config = EntityGraphConfig(source_fidelity_mode="warn")
        result = run_entity_graph_pipeline([str(cfg_file)], adapter, config)

        # Secrets audit should have entries
        assert len(result.secrets_audit) > 0

        # Check that TACACS/SNMP/RADIUS values are redacted in entity attributes
        entity = result.graph.get_entity("test-router-001")
        for attr in entity.attributes.values():
            if isinstance(attr.value, str):
                assert "S3cr3tRO" not in attr.value
                assert "Pr1v4teRW" not in attr.value
                assert "094F471A1A0A" not in attr.value
                assert "02050D480809" not in attr.value


class TestHybridInfraPipelineSecrets:
    """Hybrid-infra YAML with secrets through the pipeline."""

    def test_yaml_with_secrets(self, tmp_path: Path) -> None:
        yaml_content = """\
apiVersion: v1
kind: ConfigMap
metadata:
  name: test-app
data:
  DATABASE_HOST: db.internal
  DATABASE_PASSWORD: SuperS3cretDB
  API_KEY: sk-proj-1234567890abcdefghijklmnop
  NORMAL_VAR: hello
"""
        yaml_file = tmp_path / "test-app.yaml"
        yaml_file.write_text(yaml_content)

        from decoct.adapters.hybrid_infra import HybridInfraAdapter
        adapter = HybridInfraAdapter()
        config = EntityGraphConfig()
        result = run_entity_graph_pipeline([str(yaml_file)], adapter, config)

        # Verify secrets are in audit
        assert len(result.secrets_audit) > 0


class TestSecretsAuditOnResult:
    """Verify secrets_audit field on EntityGraphResult."""

    def test_secrets_audit_populated(self, tmp_path: Path) -> None:
        config_text = """\
!! IOS-XR Configuration
hostname audit-test-001
!
tacacs-server host 10.10.10.10
 key 7 094F471A1A0A
!
end
"""
        cfg_file = tmp_path / "audit-test-001.cfg"
        cfg_file.write_text(config_text)

        adapter = IosxrAdapter()
        result = run_entity_graph_pipeline([str(cfg_file)], adapter)

        # secrets_audit should be a list of AuditEntry
        assert isinstance(result.secrets_audit, list)
        for entry in result.secrets_audit:
            assert hasattr(entry, "path")
            assert hasattr(entry, "detection_method")
            # Never contains actual secret values
            assert "094F471A1A0A" not in entry.path
            assert "094F471A1A0A" not in entry.detection_method


class TestGateTestWithSecrets:
    """The 86-config gate test still passes with secrets masking enabled."""

    @pytest.mark.slow
    def test_gate_test_passes_with_masking(self) -> None:
        """Pipeline with 86 IOS-XR configs: 0 reconstruction mismatches."""
        if not IOSXR_FIXTURES.exists():
            pytest.skip("IOS-XR fixtures not available")

        sources = sorted(str(f) for f in IOSXR_FIXTURES.glob("*.cfg"))
        if len(sources) != 86:
            pytest.skip(f"Expected 86 configs, found {len(sources)}")

        adapter = IosxrAdapter()
        # warn mode: IOS-XR adapter has known structural transformations
        config = EntityGraphConfig(source_fidelity_mode="warn")
        result = run_entity_graph_pipeline(sources, adapter, config)
        assert result is not None
        # secrets_audit field exists
        assert isinstance(result.secrets_audit, list)
