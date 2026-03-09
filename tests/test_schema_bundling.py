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
