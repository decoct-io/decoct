"""Tests for canonical key, equality, and IS_SCALAR_LIKE."""

from decoct.core.canonical import (
    CANONICAL_EQUAL,
    CANONICAL_KEY,
    IS_SCALAR_LIKE,
    ITEM_KEY,
    VALUE_KEY,
    encode_canonical,
)
from decoct.core.composite_value import CompositeValue


class TestCanonicalKey:
    def test_deterministic_across_calls(self) -> None:
        value = {"b": 2, "a": 1}
        assert CANONICAL_KEY(value) == CANONICAL_KEY(value)

    def test_sort_keys(self) -> None:
        v1 = {"b": 2, "a": 1}
        v2 = {"a": 1, "b": 2}
        assert CANONICAL_KEY(v1) == CANONICAL_KEY(v2)

    def test_string(self) -> None:
        assert CANONICAL_KEY("hello") == '"hello"'

    def test_number(self) -> None:
        assert CANONICAL_KEY(42) == "42"

    def test_none(self) -> None:
        assert CANONICAL_KEY(None) == "null"

    def test_bool(self) -> None:
        assert CANONICAL_KEY(True) == "true"
        assert CANONICAL_KEY(False) == "false"

    def test_list(self) -> None:
        assert CANONICAL_KEY([1, 2, 3]) == "[1,2,3]"

    def test_composite_value(self) -> None:
        cv = CompositeValue(data={"a": 1}, kind="map")
        key = CANONICAL_KEY(cv)
        assert key == '{"a":1}'

    def test_float_int_normalization(self) -> None:
        # 1.0 and 1 should be the same
        assert CANONICAL_KEY(1.0) == CANONICAL_KEY(1)


class TestCanonicalEqual:
    def test_same_values(self) -> None:
        assert CANONICAL_EQUAL("hello", "hello") is True

    def test_different_values(self) -> None:
        assert CANONICAL_EQUAL("hello", "world") is False

    def test_dict_key_order(self) -> None:
        assert CANONICAL_EQUAL({"b": 2, "a": 1}, {"a": 1, "b": 2}) is True

    def test_composite_value(self) -> None:
        cv1 = CompositeValue(data=[1, 2], kind="list")
        cv2 = CompositeValue(data=[1, 2], kind="list")
        assert CANONICAL_EQUAL(cv1, cv2) is True


class TestIsScalarLike:
    def test_string_is_scalar(self) -> None:
        assert IS_SCALAR_LIKE("string") is True

    def test_number_is_scalar(self) -> None:
        assert IS_SCALAR_LIKE("number") is True

    def test_boolean_is_scalar(self) -> None:
        assert IS_SCALAR_LIKE("boolean") is True

    def test_null_is_scalar(self) -> None:
        assert IS_SCALAR_LIKE("null") is True

    def test_composite_template_ref_never_scalar(self) -> None:
        assert IS_SCALAR_LIKE("composite_template_ref") is False

    def test_list_not_scalar(self) -> None:
        assert IS_SCALAR_LIKE("list") is False

    def test_map_not_scalar(self) -> None:
        assert IS_SCALAR_LIKE("map") is False


class TestItemKey:
    def test_basic(self) -> None:
        key = ITEM_KEY("router.bgp.as", "65002")
        assert key == ("router.bgp.as", '"65002"')

    def test_value_key_alias(self) -> None:
        assert VALUE_KEY("hello") == CANONICAL_KEY("hello")
