"""Tests for decoct.pipeline — pipeline orchestrator."""

from pathlib import Path

import yaml

from decoct.pipeline import PipelineConfig, PipelineResult, run_pipeline, write_output


class TestRunPipeline:
    def test_empty_directory(self, tmp_path: Path) -> None:
        result = run_pipeline(tmp_path)
        assert result.tier_b == {}
        assert result.tier_c == {}

    def test_yaml_files(self, tmp_path: Path) -> None:
        for i in range(3):
            data = {"base": {"ntp": "10.1.1.1", "log": "10.2.2.2", "snmp": "pub", "hostname": f"rtr-{i:02d}"}}
            with open(tmp_path / f"rtr-{i:02d}.yaml", "w") as f:
                yaml.dump(data, f)

        result = run_pipeline(tmp_path)
        assert len(result.tier_b) > 0
        assert len(result.tier_c) == 3
        assert result.validation_ok is True

    def test_json_files(self, tmp_path: Path) -> None:
        import json

        for i in range(3):
            data = {"config": {"version": "1.0", "region": "us-east", "env": "prod", "name": f"host-{i:02d}"}}
            with open(tmp_path / f"host-{i:02d}.json", "w") as f:
                json.dump(data, f)

        result = run_pipeline(tmp_path)
        assert len(result.tier_c) == 3
        assert result.validation_ok is True
        assert result.format == "json"

    def test_xml_files(self) -> None:
        fixture_dir = Path("tests/fixtures/ios-xr-program/xml")
        if not fixture_dir.exists():
            return

        result = run_pipeline(fixture_dir, PipelineConfig(secrets=False))
        assert len(result.tier_c) > 0
        assert result.validation_ok is True
        assert result.format == "xml"

    def test_no_secrets_masking(self, tmp_path: Path) -> None:
        data = {"base": {"password": "secret123", "ntp": "10.1.1.1", "log": "10.2.2.2", "host": "rtr-00"}}
        with open(tmp_path / "rtr-00.yaml", "w") as f:
            yaml.dump(data, f)

        result = run_pipeline(tmp_path, PipelineConfig(secrets=False))
        assert result.secrets_audit == []

    def test_no_validation(self, tmp_path: Path) -> None:
        for i in range(3):
            data = {"section": {"a": 1, "b": 2, "c": 3, "name": f"h-{i}"}}
            with open(tmp_path / f"h-{i}.yaml", "w") as f:
                yaml.dump(data, f)

        result = run_pipeline(tmp_path, PipelineConfig(validate=False))
        assert result.validation_ok is True  # not checked, defaults to True
        assert result.validation_errors == []


class TestWriteOutput:
    def test_writes_files(self, tmp_path: Path) -> None:
        result = PipelineResult(
            tier_b={"MyClass": {"a": 1, "b": 2}},
            tier_c={"rtr-00": {"section": {"_class": "MyClass"}}, "rtr-01": {"section": {"_class": "MyClass"}}},
        )
        write_output(result, tmp_path / "out")
        assert (tmp_path / "out" / "tier_b.yaml").exists()
        assert (tmp_path / "out" / "rtr-00.yaml").exists()
        assert (tmp_path / "out" / "rtr-01.yaml").exists()

    def test_output_is_valid_yaml(self, tmp_path: Path) -> None:
        result = PipelineResult(
            tier_b={"Cls": {"x": [1, 2, 3], "y": 42}},
            tier_c={"host": {"s": {"_class": "Cls"}}},
        )
        write_output(result, tmp_path / "out")
        loaded = yaml.safe_load((tmp_path / "out" / "tier_b.yaml").read_text())
        assert loaded["Cls"]["x"] == [1, 2, 3]
        assert loaded["Cls"]["y"] == 42


class TestPipelineE2E:
    """End-to-end pipeline tests with fixture data."""

    def test_xml_fixture_roundtrip(self) -> None:
        """Full pipeline on XML fixtures: all hosts must reconstruct."""
        fixture_dir = Path("tests/fixtures/ios-xr-program/xml")
        if not fixture_dir.exists():
            return

        result = run_pipeline(fixture_dir, PipelineConfig(secrets=False))
        assert result.validation_ok is True, f"Reconstruction errors: {result.validation_errors}"
        assert len(result.tier_c) > 0
        assert len(result.tier_b) > 0

    def test_json_fixture_roundtrip(self) -> None:
        """Full pipeline on JSON fixtures: all hosts must reconstruct."""
        fixture_dir = Path("tests/fixtures/ios-xr-program/json")
        if not fixture_dir.exists():
            return

        result = run_pipeline(fixture_dir, PipelineConfig(secrets=False))
        assert result.validation_ok is True, f"Reconstruction errors: {result.validation_errors}"
        assert len(result.tier_c) > 0
