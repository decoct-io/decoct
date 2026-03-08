"""Tests for schema models and loader."""

from pathlib import Path

import pytest

from decoct.schemas import Schema, load_schema

FIXTURES = Path(__file__).parent / "fixtures" / "schemas"


class TestSchemaModel:
    def test_schema_defaults(self) -> None:
        schema = Schema(platform="test", source="test", confidence="high")
        assert schema.defaults == {}
        assert schema.drop_patterns == []
        assert schema.system_managed == []

    def test_schema_with_all_fields(self) -> None:
        schema = Schema(
            platform="docker-compose",
            source="Docker Compose spec",
            confidence="authoritative",
            defaults={"services.*.restart": "no"},
            drop_patterns=["**.uuid"],
            system_managed=["**.creationTimestamp"],
        )
        assert schema.platform == "docker-compose"
        assert schema.confidence == "authoritative"
        assert len(schema.defaults) == 1


class TestLoadSchema:
    def test_load_valid_schema(self) -> None:
        schema = load_schema(FIXTURES / "docker-compose.yaml")
        assert schema.platform == "docker-compose"
        assert schema.source == "Docker Compose specification v3.8"
        assert schema.confidence == "authoritative"
        assert "services.*.restart" in schema.defaults
        assert schema.defaults["services.*.restart"] == "no"
        assert "**.uuid" in schema.drop_patterns
        assert "**.creationTimestamp" in schema.system_managed

    def test_load_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_schema(FIXTURES / "nonexistent.yaml")

    def test_load_missing_platform(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.yaml"
        f.write_text("source: test\nconfidence: high\n")
        with pytest.raises(ValueError, match="missing required field 'platform'"):
            load_schema(f)

    def test_load_invalid_confidence(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.yaml"
        f.write_text("platform: test\nsource: test\nconfidence: invalid\n")
        with pytest.raises(ValueError, match="confidence must be one of"):
            load_schema(f)

    def test_load_non_mapping(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.yaml"
        f.write_text("- item1\n- item2\n")
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            load_schema(f)
