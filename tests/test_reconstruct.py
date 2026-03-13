"""Tests for decoct.reconstruct module."""

from __future__ import annotations

from typing import Any

from decoct.reconstruct import (
    deep_delete,
    deep_get,
    deep_set,
    normalize,
    reconstruct_host,
    reconstruct_instances,
    reconstruct_section,
    validate_round_trip,
)

# ---------------------------------------------------------------------------
# deep_set / deep_delete / deep_get
# ---------------------------------------------------------------------------


def test_deep_set_flat() -> None:
    d: dict[str, Any] = {"a": 1}
    deep_set(d, "b", 2)
    assert d == {"a": 1, "b": 2}


def test_deep_set_nested() -> None:
    d: dict[str, Any] = {}
    deep_set(d, "a.b.c", 42)
    assert d == {"a": {"b": {"c": 42}}}


def test_deep_delete_flat() -> None:
    d: dict[str, Any] = {"a": 1, "b": 2}
    assert deep_delete(d, "a") is True
    assert d == {"b": 2}


def test_deep_delete_nested() -> None:
    d: dict[str, Any] = {"a": {"b": 1, "c": 2}}
    assert deep_delete(d, "a.b") is True
    assert d == {"a": {"c": 2}}


def test_deep_delete_missing_returns_false() -> None:
    d: dict[str, Any] = {"a": 1}
    assert deep_delete(d, "b") is False
    assert deep_delete(d, "x.y") is False


def test_deep_get_flat() -> None:
    d: dict[str, Any] = {"a": 1}
    assert deep_get(d, "a") == 1


def test_deep_get_nested() -> None:
    d: dict[str, Any] = {"a": {"b": {"c": 42}}}
    assert deep_get(d, "a.b.c") == 42


def test_deep_get_default() -> None:
    d: dict[str, Any] = {"a": 1}
    assert deep_get(d, "b", "missing") == "missing"


def test_deep_get_raises_on_missing() -> None:
    d: dict[str, Any] = {"a": 1}
    try:
        deep_get(d, "b")
        assert False, "Expected KeyError"
    except KeyError:
        pass


# ---------------------------------------------------------------------------
# normalize
# ---------------------------------------------------------------------------


def test_normalize_sorts_keys_recursively() -> None:
    data = {"z": {"b": 1, "a": 2}, "a": 3}
    result = normalize(data)
    assert list(result.keys()) == ["a", "z"]
    assert list(result["z"].keys()) == ["a", "b"]


def test_normalize_handles_lists() -> None:
    data = [{"b": 1, "a": 2}]
    result = normalize(data)
    assert list(result[0].keys()) == ["a", "b"]


def test_normalize_scalars_pass_through() -> None:
    assert normalize(42) == 42
    assert normalize("hello") == "hello"
    assert normalize(True) is True


# ---------------------------------------------------------------------------
# reconstruct_section
# ---------------------------------------------------------------------------


def test_reconstruct_section_applies_overrides() -> None:
    tier_b: dict[str, Any] = {
        "MyClass": {"ip": "10.0.0.1", "mask": "255.255.255.0", "mtu": 1500, "_identity": ["ip"]},
    }
    tier_c_section: dict[str, Any] = {
        "_class": "MyClass",
        "ip": "10.0.0.2",
        "mtu": 9000,
    }
    result = reconstruct_section(tier_b, tier_c_section)
    assert result["ip"] == "10.0.0.2"
    assert result["mask"] == "255.255.255.0"
    assert result["mtu"] == 9000
    assert "_identity" not in result


def test_reconstruct_section_handles_removals() -> None:
    tier_b: dict[str, Any] = {
        "MyClass": {"a": 1, "b": 2, "c": 3},
    }
    tier_c_section: dict[str, Any] = {
        "_class": "MyClass",
        "_remove": ["b"],
    }
    result = reconstruct_section(tier_b, tier_c_section)
    assert result == {"a": 1, "c": 3}


def test_reconstruct_section_dot_notation_override() -> None:
    tier_b: dict[str, Any] = {
        "MyClass": {"nested": {"a": 1, "b": 2}},
    }
    tier_c_section: dict[str, Any] = {
        "_class": "MyClass",
        "nested.a": 99,
    }
    result = reconstruct_section(tier_b, tier_c_section)
    assert result["nested"]["a"] == 99
    assert result["nested"]["b"] == 2


def test_reconstruct_section_raw_passthrough() -> None:
    section: dict[str, Any] = {"key": "val", "num": 42}
    result = reconstruct_section({}, section)
    assert result == {"key": "val", "num": 42}


# ---------------------------------------------------------------------------
# reconstruct_instances
# ---------------------------------------------------------------------------


def test_reconstruct_instances_rebuilds_list() -> None:
    tier_b: dict[str, Any] = {
        "IfClass": {"speed": "1G", "enabled": True, "_identity": ["name"]},
    }
    tier_c_section: dict[str, Any] = {
        "_class": "IfClass",
        "instances": [
            {"name": "eth0"},
            {"name": "eth1", "speed": "10G"},
            {"name": "eth2", "_remove": ["enabled"]},
        ],
    }
    result = reconstruct_instances(tier_b, tier_c_section)
    assert len(result) == 3
    assert result[0] == {"name": "eth0", "speed": "1G", "enabled": True}
    assert result[1] == {"name": "eth1", "speed": "10G", "enabled": True}
    assert result[2] == {"name": "eth2", "speed": "1G"}


# ---------------------------------------------------------------------------
# reconstruct_host
# ---------------------------------------------------------------------------


def test_reconstruct_host_handles_mixed_sections() -> None:
    tier_b: dict[str, Any] = {
        "NetClass": {"mask": "255.255.255.0", "gw": "10.0.0.254", "_identity": ["ip"]},
        "IfClass": {"speed": "1G", "enabled": True, "_identity": ["name"]},
    }
    tier_c_host: dict[str, Any] = {
        "network": {"_class": "NetClass", "ip": "10.0.0.1"},
        "interfaces": {
            "_class": "IfClass",
            "instances": [{"name": "eth0"}, {"name": "eth1"}],
        },
        "raw_section": {"key": "val"},
    }
    result = reconstruct_host(tier_b, tier_c_host)
    assert result["network"] == {"mask": "255.255.255.0", "gw": "10.0.0.254", "ip": "10.0.0.1"}
    assert len(result["interfaces"]) == 2
    assert result["raw_section"] == {"key": "val"}


# ---------------------------------------------------------------------------
# validate_round_trip
# ---------------------------------------------------------------------------


def test_validate_round_trip_returns_empty_on_success() -> None:
    corpus: dict[str, dict[str, Any]] = {
        "host-a": {"section": {"a": 1, "b": 2}},
    }
    tier_b: dict[str, Any] = {}
    tier_c: dict[str, dict[str, Any]] = {
        "host-a": {"section": {"a": 1, "b": 2}},
    }
    assert validate_round_trip(corpus, tier_b, tier_c) == []


def test_validate_round_trip_detects_mismatch() -> None:
    corpus: dict[str, dict[str, Any]] = {
        "host-a": {"section": {"a": 1, "b": 2}},
    }
    tier_b: dict[str, Any] = {}
    tier_c: dict[str, dict[str, Any]] = {
        "host-a": {"section": {"a": 1, "b": 999}},
    }
    assert validate_round_trip(corpus, tier_b, tier_c) == ["host-a"]
