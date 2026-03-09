"""Tests for bundled schema resolution — TDD (initially failing until resolver.py is implemented)."""

from __future__ import annotations

from pathlib import Path

import pytest

from decoct.schemas.resolver import BUNDLED_SCHEMAS, resolve_schema


class TestResolveSchema:
    def test_resolve_bundled_by_name(self) -> None:
        path = resolve_schema("docker-compose")
        assert path.exists()
        assert path.name == "docker-compose.yaml"

    def test_resolve_path_passthrough(self) -> None:
        test_path = "tests/fixtures/schemas/docker-compose.yaml"
        path = resolve_schema(test_path)
        assert str(path) == test_path

    def test_resolve_unknown_raises(self) -> None:
        with pytest.raises(KeyError, match="unknown-platform"):
            resolve_schema("unknown-platform")

    def test_bundled_schema_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("docker-compose")
        schema = load_schema(path)
        assert schema.platform == "docker-compose"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 35

    def test_bundled_schemas_registry(self) -> None:
        assert "docker-compose" in BUNDLED_SCHEMAS

    def test_resolve_cloud_init_bundled(self) -> None:
        path = resolve_schema("cloud-init")
        assert path.exists()
        assert path.name == "cloud-init.yaml"

    def test_bundled_cloud_init_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("cloud-init")
        schema = load_schema(path)
        assert schema.platform == "cloud-init"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 40

    def test_resolve_ansible_playbook_bundled(self) -> None:
        path = resolve_schema("ansible-playbook")
        assert path.exists()
        assert path.name == "ansible-playbook.yaml"

    def test_bundled_ansible_playbook_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("ansible-playbook")
        schema = load_schema(path)
        assert schema.platform == "ansible-playbook"
        assert len(schema.defaults) >= 80

    def test_resolve_sshd_config_bundled(self) -> None:
        path = resolve_schema("sshd-config")
        assert path.exists()
        assert path.name == "sshd-config.yaml"

    def test_bundled_sshd_config_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("sshd-config")
        schema = load_schema(path)
        assert schema.platform == "sshd-config"
        assert len(schema.defaults) >= 30

    def test_resolve_kubernetes_bundled(self) -> None:
        path = resolve_schema("kubernetes")
        assert path.exists()
        assert path.name == "kubernetes.yaml"

    def test_bundled_kubernetes_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("kubernetes")
        schema = load_schema(path)
        assert schema.platform == "kubernetes"
        assert len(schema.defaults) >= 40
        assert len(schema.system_managed) >= 5

    def test_resolve_github_actions_bundled(self) -> None:
        path = resolve_schema("github-actions")
        assert path.exists()
        assert path.name == "github-actions.yaml"

    def test_bundled_github_actions_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("github-actions")
        schema = load_schema(path)
        assert schema.platform == "github-actions"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 8

    def test_resolve_traefik_bundled(self) -> None:
        path = resolve_schema("traefik")
        assert path.exists()
        assert path.name == "traefik.yaml"

    def test_bundled_traefik_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("traefik")
        schema = load_schema(path)
        assert schema.platform == "traefik"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 50

    def test_resolve_prometheus_bundled(self) -> None:
        path = resolve_schema("prometheus")
        assert path.exists()
        assert path.name == "prometheus.yaml"

    def test_bundled_prometheus_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("prometheus")
        schema = load_schema(path)
        assert schema.platform == "prometheus"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 50

    # --- MongoDB, OTel Collector, ArgoCD (added in this session) ---

    def test_resolve_mongodb_bundled(self) -> None:
        path = resolve_schema("mongodb")
        assert path.exists()
        assert path.name == "mongodb.yaml"

    def test_bundled_mongodb_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("mongodb")
        schema = load_schema(path)
        assert schema.platform == "mongodb"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 14

    def test_resolve_opentelemetry_collector_bundled(self) -> None:
        path = resolve_schema("opentelemetry-collector")
        assert path.exists()
        assert path.name == "opentelemetry-collector.yaml"

    def test_bundled_opentelemetry_collector_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("opentelemetry-collector")
        schema = load_schema(path)
        assert schema.platform == "opentelemetry-collector"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 19

    def test_resolve_argocd_bundled(self) -> None:
        path = resolve_schema("argocd")
        assert path.exists()
        assert path.name == "argocd.yaml"

    def test_bundled_argocd_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("argocd")
        schema = load_schema(path)
        assert schema.platform == "argocd"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 14
        assert len(schema.system_managed) >= 5

    # --- Database schemas (PostgreSQL, Redis, MariaDB/MySQL, Kafka) ---

    def test_resolve_postgresql_bundled(self) -> None:
        path = resolve_schema("postgresql")
        assert path.exists()
        assert path.name == "postgresql.yaml"

    def test_bundled_postgresql_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("postgresql")
        schema = load_schema(path)
        assert schema.platform == "postgresql"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 40

    def test_resolve_redis_bundled(self) -> None:
        path = resolve_schema("redis")
        assert path.exists()
        assert path.name == "redis.yaml"

    def test_bundled_redis_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("redis")
        schema = load_schema(path)
        assert schema.platform == "redis"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 40

    def test_resolve_mariadb_mysql_bundled(self) -> None:
        path = resolve_schema("mariadb-mysql")
        assert path.exists()
        assert path.name == "mariadb-mysql.yaml"

    def test_bundled_mariadb_mysql_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("mariadb-mysql")
        schema = load_schema(path)
        assert schema.platform == "mariadb-mysql"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 30

    def test_resolve_kafka_bundled(self) -> None:
        path = resolve_schema("kafka")
        assert path.exists()
        assert path.name == "kafka.yaml"

    def test_bundled_kafka_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("kafka")
        schema = load_schema(path)
        assert schema.platform == "kafka"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 40

    # --- Observability & CI (Fluent Bit, GitLab CI, Grafana, Keycloak) ---

    def test_resolve_fluent_bit_bundled(self) -> None:
        path = resolve_schema("fluent-bit")
        assert path.exists()
        assert path.name == "fluent-bit.yaml"

    def test_bundled_fluent_bit_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("fluent-bit")
        schema = load_schema(path)
        assert schema.platform == "fluent-bit"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 25

    def test_resolve_gitlab_ci_bundled(self) -> None:
        path = resolve_schema("gitlab-ci")
        assert path.exists()
        assert path.name == "gitlab-ci.yaml"

    def test_bundled_gitlab_ci_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("gitlab-ci")
        schema = load_schema(path)
        assert schema.platform == "gitlab-ci"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 20

    def test_resolve_grafana_bundled(self) -> None:
        path = resolve_schema("grafana")
        assert path.exists()
        assert path.name == "grafana.yaml"

    def test_bundled_grafana_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("grafana")
        schema = load_schema(path)
        assert schema.platform == "grafana"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 50

    def test_resolve_keycloak_bundled(self) -> None:
        path = resolve_schema("keycloak")
        assert path.exists()
        assert path.name == "keycloak.yaml"

    def test_bundled_keycloak_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("keycloak")
        schema = load_schema(path)
        assert schema.platform == "keycloak"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 40
        assert len(schema.system_managed) >= 5

    # --- Azure cloud (Entra ID, Intune, ARM/Bicep) ---

    def test_resolve_entra_id_bundled(self) -> None:
        path = resolve_schema("entra-id")
        assert path.exists()
        assert path.name == "entra-id.yaml"

    def test_bundled_entra_id_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("entra-id")
        schema = load_schema(path)
        assert schema.platform == "entra-id"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 40
        assert len(schema.system_managed) >= 5

    def test_resolve_intune_bundled(self) -> None:
        path = resolve_schema("intune")
        assert path.exists()
        assert path.name == "intune.yaml"

    def test_bundled_intune_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("intune")
        schema = load_schema(path)
        assert schema.platform == "intune"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 40
        assert len(schema.system_managed) >= 5

    def test_resolve_azure_arm_bundled(self) -> None:
        path = resolve_schema("azure-arm")
        assert path.exists()
        assert path.name == "azure-arm.yaml"

    def test_bundled_azure_arm_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("azure-arm")
        schema = load_schema(path)
        assert schema.platform == "azure-arm"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 40
        assert len(schema.system_managed) >= 5

    # --- AWS + GCP cloud ---

    def test_resolve_aws_cloudformation_bundled(self) -> None:
        path = resolve_schema("aws-cloudformation")
        assert path.exists()
        assert path.name == "aws-cloudformation.yaml"

    def test_bundled_aws_cloudformation_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("aws-cloudformation")
        schema = load_schema(path)
        assert schema.platform == "aws-cloudformation"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 40
        assert len(schema.system_managed) >= 5

    def test_resolve_gcp_resources_bundled(self) -> None:
        path = resolve_schema("gcp-resources")
        assert path.exists()
        assert path.name == "gcp-resources.yaml"

    def test_bundled_gcp_resources_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("gcp-resources")
        schema = load_schema(path)
        assert schema.platform == "gcp-resources"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 30
        assert len(schema.system_managed) >= 5

    # --- Network OS schemas (Cisco IOS XE, IOS XR, NX-OS, Juniper JunOS, Arista EOS) ---

    def test_resolve_cisco_ios_xe_bundled(self) -> None:
        path = resolve_schema("cisco-ios-xe")
        assert path.exists()
        assert path.name == "cisco-ios-xe.yaml"

    def test_bundled_cisco_ios_xe_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("cisco-ios-xe")
        schema = load_schema(path)
        assert schema.platform == "cisco-ios-xe"
        assert schema.confidence == "high"
        assert len(schema.defaults) >= 60
        assert len(schema.system_managed) >= 5

    def test_resolve_cisco_ios_xr_bundled(self) -> None:
        path = resolve_schema("cisco-ios-xr")
        assert path.exists()
        assert path.name == "cisco-ios-xr.yaml"

    def test_bundled_cisco_ios_xr_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("cisco-ios-xr")
        schema = load_schema(path)
        assert schema.platform == "cisco-ios-xr"
        assert schema.confidence == "high"
        assert len(schema.defaults) >= 60
        assert len(schema.system_managed) >= 5

    def test_resolve_cisco_nxos_bundled(self) -> None:
        path = resolve_schema("cisco-nxos")
        assert path.exists()
        assert path.name == "cisco-nxos.yaml"

    def test_bundled_cisco_nxos_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("cisco-nxos")
        schema = load_schema(path)
        assert schema.platform == "cisco-nxos"
        assert schema.confidence == "medium"
        assert len(schema.defaults) >= 50
        assert len(schema.system_managed) >= 5

    def test_resolve_juniper_junos_bundled(self) -> None:
        path = resolve_schema("juniper-junos")
        assert path.exists()
        assert path.name == "juniper-junos.yaml"

    def test_bundled_juniper_junos_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("juniper-junos")
        schema = load_schema(path)
        assert schema.platform == "juniper-junos"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) >= 60
        assert len(schema.system_managed) >= 5

    def test_resolve_arista_eos_bundled(self) -> None:
        path = resolve_schema("arista-eos")
        assert path.exists()
        assert path.name == "arista-eos.yaml"

    def test_bundled_arista_eos_loads(self) -> None:
        from decoct.schemas import load_schema

        path = resolve_schema("arista-eos")
        schema = load_schema(path)
        assert schema.platform == "arista-eos"
        assert schema.confidence == "high"
        assert len(schema.defaults) >= 50
        assert len(schema.system_managed) >= 5

    def test_all_bundled_schemas_exist(self) -> None:
        for name in BUNDLED_SCHEMAS:
            path = resolve_schema(name)
            assert path.exists(), f"Bundled schema {name} not found at {path}"


class TestCliBundledSchema:
    def test_cli_bundled_schema(self) -> None:
        from click.testing import CliRunner

        from decoct.cli import cli

        runner = CliRunner()
        fixtures = Path(__file__).parent / "fixtures"
        result = runner.invoke(cli, [
            "compress",
            str(fixtures / "yaml" / "with-defaults.yaml"),
            "--schema", "docker-compose",
        ])
        assert result.exit_code == 0
        assert "services" in result.output
