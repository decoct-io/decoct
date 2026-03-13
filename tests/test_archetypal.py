"""Tests for the simplified decoct pipeline."""

from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from ruamel.yaml import YAML

from decoct.adapter import BaseAdapter
from decoct.archetypal import archetypal_compress
from decoct.cli import cli
from decoct.pipeline import run_pipeline
from decoct.reconstruct import validate_round_trip

# ---------------------------------------------------------------------------
# archetypal_compress() unit tests
# ---------------------------------------------------------------------------


def _make_corpus() -> dict[str, dict[str, Any]]:
    """Three hosts with overlapping network config."""
    return {
        "host-a": {
            "network": {"ip": "10.0.0.1", "mask": "255.255.255.0", "gateway": "10.0.0.254", "mtu": 1500},
            "dns": {"primary": "8.8.8.8", "secondary": "8.8.4.4"},
        },
        "host-b": {
            "network": {"ip": "10.0.0.2", "mask": "255.255.255.0", "gateway": "10.0.0.254", "mtu": 1500},
            "dns": {"primary": "8.8.8.8", "secondary": "8.8.4.4"},
        },
        "host-c": {
            "network": {"ip": "10.0.0.3", "mask": "255.255.255.0", "gateway": "10.0.0.254", "mtu": 9000},
            "dns": {"primary": "8.8.8.8", "secondary": "8.8.4.4"},
        },
    }


def test_compress_produces_tier_b_and_tier_c() -> None:
    corpus = _make_corpus()
    tier_b, tier_c = archetypal_compress(corpus)
    assert isinstance(tier_b, dict)
    assert isinstance(tier_c, dict)
    assert set(tier_c.keys()) == {"host-a", "host-b", "host-c"}


def test_compress_extracts_shared_class() -> None:
    corpus = _make_corpus()
    tier_b, tier_c = archetypal_compress(corpus)
    # With 3 hosts sharing most fields, at least one class should be extracted
    assert len(tier_b) >= 1


def test_compress_deltas_reference_class() -> None:
    corpus = _make_corpus()
    tier_b, tier_c = archetypal_compress(corpus)
    # At least one host's section should reference a class
    has_class_ref = False
    for host_data in tier_c.values():
        for section_data in host_data.values():
            if isinstance(section_data, dict) and "_class" in section_data:
                has_class_ref = True
                break
    assert has_class_ref


def test_compress_empty_input() -> None:
    tier_b, tier_c = archetypal_compress({})
    assert tier_b == {}
    assert tier_c == {}


def test_compress_single_host() -> None:
    corpus = {"only-host": {"config": {"key": "value", "num": 42}}}
    tier_b, tier_c = archetypal_compress(corpus)
    # Single host can't form classes
    assert len(tier_b) == 0
    assert "only-host" in tier_c


def test_compress_list_of_dicts_section() -> None:
    corpus = {
        "host-a": {"interfaces": [
            {"name": "eth0", "speed": "1G", "enabled": True, "vlan": 10},
            {"name": "eth1", "speed": "1G", "enabled": True, "vlan": 20},
        ]},
        "host-b": {"interfaces": [
            {"name": "eth0", "speed": "1G", "enabled": True, "vlan": 30},
            {"name": "eth2", "speed": "1G", "enabled": True, "vlan": 40},
        ]},
        "host-c": {"interfaces": [
            {"name": "eth0", "speed": "1G", "enabled": True, "vlan": 50},
            {"name": "eth3", "speed": "1G", "enabled": False, "vlan": 60},
        ]},
    }
    tier_b, tier_c = archetypal_compress(corpus)
    assert isinstance(tier_b, dict)
    assert isinstance(tier_c, dict)


# ---------------------------------------------------------------------------
# BaseAdapter tests
# ---------------------------------------------------------------------------


def test_adapter_load_json() -> None:
    adapter = BaseAdapter()
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        json.dump({"network": {"ip": "10.0.0.1"}}, f)
        f.flush()
        entity_id, data = adapter.load(f.name)
    assert isinstance(data, dict)
    assert "network" in data


def test_adapter_load_yaml() -> None:
    adapter = BaseAdapter()
    yaml = YAML()
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump({"network": {"ip": "10.0.0.1"}}, f)
        f.flush()
        entity_id, data = adapter.load(f.name)
    assert isinstance(data, dict)
    assert "network" in data


def test_adapter_load_ini() -> None:
    adapter = BaseAdapter()
    with tempfile.NamedTemporaryFile(suffix=".ini", mode="w", delete=False) as f:
        f.write("[network]\nip = 10.0.0.1\nmask = 255.255.255.0\n")
        f.flush()
        entity_id, data = adapter.load(f.name)
    assert isinstance(data, dict)
    assert "network" in data


def test_adapter_load_xml() -> None:
    adapter = BaseAdapter()
    with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
        f.write("<config><network><ip>10.0.0.1</ip></network></config>")
        f.flush()
        entity_id, data = adapter.load(f.name)
    assert isinstance(data, dict)
    assert "config" in data


def test_adapter_load_corpus() -> None:
    adapter = BaseAdapter()
    with tempfile.TemporaryDirectory() as d:
        for name in ["a", "b", "c"]:
            p = Path(d) / f"{name}.json"
            p.write_text(json.dumps({"section": {"key": "val", "num": 1, "flag": True}}))
        sources = sorted(str(f) for f in Path(d).iterdir())
        corpus = adapter.load_corpus(sources)
    assert len(corpus) == 3
    assert all(isinstance(v, dict) for v in corpus.values())


# ---------------------------------------------------------------------------
# Pipeline end-to-end test
# ---------------------------------------------------------------------------


def test_run_pipeline_writes_output() -> None:
    with tempfile.TemporaryDirectory() as inp, tempfile.TemporaryDirectory() as out:
        for name in ["host-a", "host-b", "host-c"]:
            p = Path(inp) / f"{name}.json"
            p.write_text(json.dumps({
                "network": {"ip": f"10.0.0.{ord(name[-1]) - 96}", "mask": "255.255.255.0", "gw": "10.0.0.254"},
                "dns": {"primary": "8.8.8.8", "secondary": "8.8.4.4"},
            }))
        sources = sorted(str(f) for f in Path(inp).iterdir())
        result = run_pipeline(sources, out)

        assert result["entities"] == 3
        assert (Path(out) / "tier_b.yaml").exists()
        assert (Path(out) / "tier_c").is_dir()
        tier_c_files = list((Path(out) / "tier_c").iterdir())
        assert len(tier_c_files) == 3
        assert "stats" in result
        assert result["stats"].entity_count == 3


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------


def test_cli_compress() -> None:
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as inp, tempfile.TemporaryDirectory() as out:
        for name in ["host-a", "host-b", "host-c"]:
            p = Path(inp) / f"{name}.json"
            p.write_text(json.dumps({
                "network": {"ip": f"10.0.0.{ord(name[-1]) - 96}", "mask": "255.255.255.0", "gw": "10.0.0.254"},
                "dns": {"primary": "8.8.8.8", "secondary": "8.8.4.4"},
            }))
        result = runner.invoke(cli, ["compress", "-i", inp, "-o", str(Path(out) / "result")])
        assert result.exit_code == 0
        assert "Compressed 3 entities" in result.output
        assert "Compression:" in result.output
        assert "Token counts" in result.output
        assert "Round-trip: PASS" in result.output


def test_cli_version() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.2.0" in result.output


# ---------------------------------------------------------------------------
# Integration test with real fixtures (if available)
# ---------------------------------------------------------------------------


FIXTURE_JSON = Path(__file__).parent / "fixtures" / "ios-xr-program" / "json"
FIXTURE_XML = Path(__file__).parent / "fixtures" / "ios-xr-program" / "xml"


@pytest.mark.skipif(not FIXTURE_JSON.exists(), reason="JSON fixtures not available")
def test_pipeline_on_json_fixtures() -> None:
    sources = sorted(str(f) for f in FIXTURE_JSON.iterdir() if f.suffix == ".json")
    assert len(sources) >= 2
    with tempfile.TemporaryDirectory() as out:
        result = run_pipeline(sources, out)
        assert result["entities"] == len(sources)
        assert (Path(out) / "tier_b.yaml").exists()


@pytest.mark.skipif(not FIXTURE_XML.exists(), reason="XML fixtures not available")
def test_pipeline_on_xml_fixtures() -> None:
    sources = sorted(str(f) for f in FIXTURE_XML.iterdir() if f.suffix == ".xml")
    assert len(sources) >= 2
    with tempfile.TemporaryDirectory() as out:
        result = run_pipeline(sources, out)
        assert result["entities"] == len(sources)
        assert (Path(out) / "tier_b.yaml").exists()


# ---------------------------------------------------------------------------
# Round-trip validation tests
# ---------------------------------------------------------------------------


def test_validate_round_trip_detects_mismatch() -> None:
    corpus = _make_corpus()
    tier_b, tier_c = archetypal_compress(corpus)
    # Corrupt one host's tier_c data
    corrupted_tc = copy.deepcopy(tier_c)
    host = list(corrupted_tc.keys())[0]
    for section in corrupted_tc[host]:
        if isinstance(corrupted_tc[host][section], dict):
            corrupted_tc[host][section]["__bogus__"] = "corrupt"
            break
    mismatched = validate_round_trip(corpus, tier_b, corrupted_tc)
    assert host in mismatched
