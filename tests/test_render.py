"""Tests for decoct.render — YAML rendering rules."""

import pytest
import yaml

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from decoct.render import (
    assert_no_subclass_refs,
    collapse_single_child_dicts,
    render_yaml,
    to_styled_yaml,
)
from decoct.reconstruct import unflatten_collapsed


# ---------------------------------------------------------------------------
# Rule 1 — Dot-notation collapse
# ---------------------------------------------------------------------------

class TestCollapseDottedKeys:
    def test_single_child_chain(self) -> None:
        data = {"a": {"b": {"c": 1}}}
        assert collapse_single_child_dicts(data) == {"a.b.c": 1}

    def test_multi_child_stops(self) -> None:
        data = {"a": {"b": 1, "c": 2}}
        assert collapse_single_child_dicts(data) == {"a": {"b": 1, "c": 2}}

    def test_control_key_stops(self) -> None:
        """Parent key starting with _ should not collapse."""
        data = {"_body": {"x": {"y": 1}}}
        result = collapse_single_child_dicts(data)
        # _body is a control key — does NOT collapse with its child
        # but its value IS recursed into, collapsing x.y
        assert result == {"_body": {"x.y": 1}}

    def test_control_child_key_stops(self) -> None:
        """Collapse stops when child key starts with _."""
        data = {"x": {"_class": "Foo"}}
        assert collapse_single_child_dicts(data) == {"x": {"_class": "Foo"}}

    def test_recurse_into_control_value(self) -> None:
        data = {"_identity": ["a"], "nested": {"a": {"b": 1}}}
        result = collapse_single_child_dicts(data)
        assert result == {"_identity": ["a"], "nested.a.b": 1}

    def test_list_stops(self) -> None:
        data = {"a": {"b": [1, 2]}}
        assert collapse_single_child_dicts(data) == {"a.b": [1, 2]}

    def test_empty_dict_leaf(self) -> None:
        data = {"a": {}}
        assert collapse_single_child_dicts(data) == {"a": {}}

    def test_scalar_passthrough(self) -> None:
        assert collapse_single_child_dicts(42) == 42

    def test_list_of_dicts(self) -> None:
        data = [{"a": {"b": 1}}, {"c": 2}]
        assert collapse_single_child_dicts(data) == [{"a.b": 1}, {"c": 2}]

    def test_deep_chain(self) -> None:
        data = {"a": {"b": {"c": {"d": {"e": "leaf"}}}}}
        assert collapse_single_child_dicts(data) == {"a.b.c.d.e": "leaf"}


# ---------------------------------------------------------------------------
# Rule 2 — Flow maps at leaf dicts
# ---------------------------------------------------------------------------

class TestFlowMaps:
    def test_small_leaf_dict_flow(self) -> None:
        data = {"a": 1, "b": 2, "c": 3}
        styled = to_styled_yaml(data)
        assert styled.fa.flow_style() is True

    def test_six_keys_flow(self) -> None:
        data = {f"k{i}": i for i in range(6)}
        styled = to_styled_yaml(data)
        assert styled.fa.flow_style() is True

    def test_seven_keys_block(self) -> None:
        data = {f"k{i}": i for i in range(7)}
        styled = to_styled_yaml(data)
        assert styled.fa.flow_style() is not True

    def test_nested_value_block(self) -> None:
        data = {"a": 1, "b": {"nested": 2}}
        styled = to_styled_yaml(data)
        assert styled.fa.flow_style() is not True


# ---------------------------------------------------------------------------
# Rule 3 — Flow maps for list items
# ---------------------------------------------------------------------------

class TestFlowListItems:
    def test_all_leaf_items_flow(self) -> None:
        data = {"items": [{"a": 1, "b": 2}, {"a": 3, "b": 4}]}
        styled = to_styled_yaml(data)
        for item in styled["items"]:
            assert item.fa.flow_style() is True

    def test_mixed_items_no_rule3_flow(self) -> None:
        """Rule 3 doesn't apply when items aren't all flow-eligible.

        The deeply nested item won't be set to flow by Rule 3.
        (Simple items may still be flow via Rule 2 independently.)
        """
        data = {"items": [{"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6, "g": 7},
                          {"a": {"deep": {"nested": 1}}}]}
        styled = to_styled_yaml(data)
        # 7-key item is NOT flow-eligible by Rule 2, and Rule 3 doesn't apply
        assert styled["items"][0].fa.flow_style() is not True
        # Deep-nested item also not flow
        assert styled["items"][1].fa.flow_style() is not True

    def test_items_with_flow_eligible_nested_dict(self) -> None:
        """Items with small nested dicts should still be flow."""
        data = {"items": [{"a": 1, "sub": {"x": 1}}, {"a": 2, "sub": {"x": 2}}]}
        styled = to_styled_yaml(data)
        for item in styled["items"]:
            assert item.fa.flow_style() is True


# ---------------------------------------------------------------------------
# Rule 4 — No subclass refs in Tier B
# ---------------------------------------------------------------------------

class TestNoSubclassRefs:
    def test_clean_passes(self) -> None:
        tier_b = {"MyClass": {"a": 1, "b": 2, "_identity": ["a"]}}
        assert_no_subclass_refs(tier_b)  # should not raise

    def test_list_class_in_body_raises(self) -> None:
        tier_b = {"MyClass": {"a": 1, "_list_class": "SomeList"}}
        with pytest.raises(ValueError, match="subclass ref"):
            assert_no_subclass_refs(tier_b)

    def test_instances_in_body_raises(self) -> None:
        tier_b = {"MyClass": {"a": 1, "_instances": [1, 2]}}
        with pytest.raises(ValueError, match="subclass ref"):
            assert_no_subclass_refs(tier_b)

    def test_also_in_body_raises(self) -> None:
        tier_b = {"MyClass": {"a": 1, "_also": [{"x": 1}]}}
        with pytest.raises(ValueError, match="subclass ref"):
            assert_no_subclass_refs(tier_b)

    def test_list_classes_key_allowed(self) -> None:
        """The _list_classes top-level key is excluded from the check."""
        tier_b = {
            "MyClass": {"a": 1},
            "_list_classes": {"ListA": {"_body": {"x": 1}, "_discriminators": ["id"]}},
        }
        assert_no_subclass_refs(tier_b)  # should not raise


# ---------------------------------------------------------------------------
# Rule 5 — Flow sequences for _identity / _discriminators
# ---------------------------------------------------------------------------

class TestFlowSequences:
    def test_identity_flow(self) -> None:
        data = {"MyClass": {"_identity": ["a", "b"], "x": 1}}
        styled = to_styled_yaml(data)
        assert styled["MyClass"]["_identity"].fa.flow_style() is True

    def test_discriminators_flow(self) -> None:
        data = {"_discriminators": ["id", "name"]}
        styled = to_styled_yaml(data)
        assert styled["_discriminators"].fa.flow_style() is True


# ---------------------------------------------------------------------------
# Integration: render + unflatten roundtrip
# ---------------------------------------------------------------------------

class TestRenderUnflattenRoundtrip:
    def test_roundtrip(self) -> None:
        """Collapse → render → load → unflatten == original (structurally)."""
        original = {
            "bgp": {
                "neighbors": {
                    "config": {
                        "peer_as": 65001,
                        "description": "upstream",
                    }
                }
            },
            "interfaces": {"loopback0": {"ip": "10.0.0.1"}},
            "simple": "value",
        }

        rendered = render_yaml(original)

        # Load back with safe YAML
        loaded = yaml.safe_load(rendered)

        # Unflatten
        restored = unflatten_collapsed(loaded)

        assert restored == original

    def test_roundtrip_with_control_keys(self) -> None:
        """Control keys should survive the roundtrip."""
        original = {
            "_identity": ["name"],
            "config": {"settings": {"timeout": 30}},
        }
        rendered = render_yaml(original)
        loaded = yaml.safe_load(rendered)
        restored = unflatten_collapsed(loaded)
        assert restored == original

    def test_render_produces_valid_yaml(self) -> None:
        data = {
            "ClassA": {
                "_identity": ["name"],
                "nested": {"deep": {"value": 42}},
                "flat": {"a": 1, "b": 2},
            }
        }
        rendered = render_yaml(data)
        loaded = yaml.safe_load(rendered)
        assert isinstance(loaded, dict)
        assert "ClassA" in loaded
