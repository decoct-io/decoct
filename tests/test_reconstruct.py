"""Tests for decoct.reconstruct — reconstruction and validation."""

import pytest

from decoct.reconstruct import (
    deep_delete,
    deep_get,
    deep_set,
    normalize,
    reconstruct_host,
    reconstruct_instances,
    reconstruct_section,
    unflatten_collapsed,
    validate_reconstruction,
)


class TestDeepSet:
    def test_simple_key(self) -> None:
        d: dict = {}
        deep_set(d, "a", 1)
        assert d == {"a": 1}

    def test_nested_key(self) -> None:
        d: dict = {}
        deep_set(d, "a.b.c", 42)
        assert d == {"a": {"b": {"c": 42}}}

    def test_overwrite(self) -> None:
        d = {"a": {"b": 1}}
        deep_set(d, "a.b", 2)
        assert d == {"a": {"b": 2}}


class TestDeepDelete:
    def test_simple_delete(self) -> None:
        d = {"a": 1, "b": 2}
        assert deep_delete(d, "a") is True
        assert d == {"b": 2}

    def test_nested_delete(self) -> None:
        d = {"a": {"b": {"c": 1, "d": 2}}}
        assert deep_delete(d, "a.b.c") is True
        assert d == {"a": {"b": {"d": 2}}}

    def test_missing_key(self) -> None:
        d = {"a": 1}
        assert deep_delete(d, "b") is False

    def test_missing_nested(self) -> None:
        d = {"a": 1}
        assert deep_delete(d, "a.b.c") is False


class TestDeepGet:
    def test_simple_get(self) -> None:
        assert deep_get({"a": 1}, "a") == 1

    def test_nested_get(self) -> None:
        assert deep_get({"a": {"b": {"c": 42}}}, "a.b.c") == 42

    def test_missing_raises(self) -> None:
        with pytest.raises(KeyError):
            deep_get({"a": 1}, "b")

    def test_default(self) -> None:
        assert deep_get({"a": 1}, "b", default=99) == 99


class TestNormalize:
    def test_sort_dict_keys(self) -> None:
        assert normalize({"b": 1, "a": 2}) == {"a": 2, "b": 1}

    def test_nested(self) -> None:
        result = normalize({"z": {"b": 1, "a": 2}, "a": 3})
        assert list(result.keys()) == ["a", "z"]

    def test_list_preserved(self) -> None:
        assert normalize([3, 1, 2]) == [3, 1, 2]

    def test_scalar_passthrough(self) -> None:
        assert normalize(42) == 42


class TestReconstructSection:
    def test_no_class_passthrough(self) -> None:
        result = reconstruct_section({}, {"key": "value"})
        assert result == {"key": "value"}

    def test_class_with_override(self) -> None:
        tier_b = {"MyClass": {"a": 1, "b": 2, "c": 3, "_identity": ["name"]}}
        tc = {"_class": "MyClass", "name": "host1", "b": 99}
        result = reconstruct_section(tier_b, tc)
        assert result == {"a": 1, "b": 99, "c": 3, "name": "host1"}

    def test_class_additive_only(self) -> None:
        """Reconstruction is purely additive: class body + delta additions."""
        tier_b = {"MyClass": {"a": 1, "c": 3}}
        tc = {"_class": "MyClass", "b": 99}
        result = reconstruct_section(tier_b, tc)
        assert result == {"a": 1, "b": 99, "c": 3}

    def test_class_with_dot_override(self) -> None:
        tier_b = {"MyClass": {"nested": {"x": 1, "y": 2}}}
        tc = {"_class": "MyClass", "nested.x": 99}
        result = reconstruct_section(tier_b, tc)
        assert result == {"nested": {"x": 99, "y": 2}}

    def test_missing_class_raises(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            reconstruct_section({}, {"_class": "Missing"})


class TestReconstructInstances:
    def test_basic_instances(self) -> None:
        tier_b = {"Iface": {"mtu": 1500, "speed": "1G", "_identity": ["name"]}}
        tc = {
            "_class": "Iface",
            "instances": [
                {"name": "eth0"},
                {"name": "eth1", "mtu": 9000},
            ],
        }
        result = reconstruct_instances(tier_b, tc)
        assert len(result) == 2
        assert result[0] == {"name": "eth0", "mtu": 1500, "speed": "1G"}
        assert result[1] == {"name": "eth1", "mtu": 9000, "speed": "1G"}

    def test_instance_additive_only(self) -> None:
        """Instance reconstruction is purely additive."""
        tier_b = {"Cls": {"a": 1, "c": 3}}
        tc = {
            "_class": "Cls",
            "instances": [{"b": 99}],
        }
        result = reconstruct_instances(tier_b, tc)
        assert result == [{"a": 1, "b": 99, "c": 3}]


class TestReconstructHost:
    def test_mixed_sections(self) -> None:
        tier_b = {"Base": {"ntp": "10.1.1.1", "log": "10.2.2.2", "snmp": "pub", "_identity": ["hostname"]}}
        tier_c_host = {
            "base": {"_class": "Base", "hostname": "rtr-00"},
            "version": "1.0",
        }
        result = reconstruct_host(tier_b, tier_c_host)
        assert result["base"]["hostname"] == "rtr-00"
        assert result["base"]["ntp"] == "10.1.1.1"
        assert result["version"] == "1.0"


class TestValidateReconstruction:
    def test_valid_reconstruction(self) -> None:
        from decoct.compress import compress

        inputs = {
            f"rtr-{i:02d}": {"section": {"a": 1, "b": 2, "c": 3, "name": f"rtr-{i:02d}"}}
            for i in range(3)
        }
        tier_b, tier_c = compress(inputs)
        ok, errors = validate_reconstruction(inputs, tier_b, tier_c)
        assert ok is True
        assert errors == []

    def test_invalid_reconstruction_detected(self) -> None:
        inputs = {"rtr-00": {"section": {"a": 1}}}
        tier_b: dict = {}
        tier_c = {"rtr-00": {"section": {"a": 999}}}  # wrong value
        ok, errors = validate_reconstruction(inputs, tier_b, tier_c)
        assert ok is False
        assert len(errors) > 0

    def test_missing_host_detected(self) -> None:
        inputs = {"rtr-00": {"section": {"a": 1}}}
        ok, errors = validate_reconstruction(inputs, {}, {})
        assert ok is False
        assert any("missing" in e for e in errors)


class TestUnflattenCollapsed:
    def test_no_dots_passthrough(self) -> None:
        data = {"a": 1, "b": {"c": 2}}
        assert unflatten_collapsed(data) == data

    def test_simple_dotted_key(self) -> None:
        data = {"a.b.c": 1}
        assert unflatten_collapsed(data) == {"a": {"b": {"c": 1}}}

    def test_shared_prefix(self) -> None:
        data = {"a.b": 1, "a.c": 2}
        assert unflatten_collapsed(data) == {"a": {"b": 1, "c": 2}}

    def test_mixed_dotted_and_plain(self) -> None:
        data = {"a.b": 1, "c": 2}
        assert unflatten_collapsed(data) == {"a": {"b": 1}, "c": 2}

    def test_nested_dict_with_dots(self) -> None:
        """Dots inside nested dicts are also unflattened."""
        data = {"outer": {"x.y": 1}}
        assert unflatten_collapsed(data) == {"outer": {"x": {"y": 1}}}

    def test_list_of_dicts(self) -> None:
        data = [{"a.b": 1}, {"c.d": 2}]
        assert unflatten_collapsed(data) == [{"a": {"b": 1}}, {"c": {"d": 2}}]

    def test_scalar_passthrough(self) -> None:
        assert unflatten_collapsed(42) == 42
        assert unflatten_collapsed("hello") == "hello"

    def test_deep_merge(self) -> None:
        """Two dotted keys that share a deep prefix merge correctly."""
        data = {"a.b.c": 1, "a.b.d": 2}
        assert unflatten_collapsed(data) == {"a": {"b": {"c": 1, "d": 2}}}

    def test_plain_key_merges_with_dotted(self) -> None:
        """A plain key 'a' with dict value merges with 'a.x' expansions."""
        data = {"a": {"z": 3}, "a.x": 1}
        result = unflatten_collapsed(data)
        assert result == {"a": {"z": 3, "x": 1}}
