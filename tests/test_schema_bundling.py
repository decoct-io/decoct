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
