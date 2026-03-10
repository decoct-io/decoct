"""Tests for entropy, profiling, and tier classification."""

from collections import Counter

from decoct.analysis.entropy import normalized_entropy, shannon_entropy
from decoct.analysis.tier_classifier import (
    classify_bootstrap_role,
    classify_final_role,
    select_tier_c_storage,
)
from decoct.core.types import (
    AttributeProfile,
    BootstrapSignal,
    FinalRole,
    TierCStorage,
)


class TestShannon:
    def test_single_value_zero_entropy(self) -> None:
        freq: Counter[str] = Counter({"a": 10})
        assert shannon_entropy(freq) == 0.0

    def test_uniform_distribution(self) -> None:
        freq: Counter[str] = Counter({"a": 5, "b": 5})
        assert abs(shannon_entropy(freq) - 1.0) < 0.01

    def test_normalized_single_value(self) -> None:
        freq: Counter[str] = Counter({"a": 10})
        assert normalized_entropy(freq) == 0.0


class TestFinalRole:
    def test_a_base_for_universal_constant(self) -> None:
        role, conf = classify_final_role(
            H_norm=0.0, cardinality=1, n_entities=60, coverage=1.0,
            len_mean=10, attribute_type="string",
        )
        assert role == FinalRole.A_BASE

    def test_c_for_high_entropy_above_floor(self) -> None:
        role, _ = classify_final_role(
            H_norm=0.9, cardinality=50, n_entities=60, coverage=1.0,
            len_mean=10, attribute_type="string",
        )
        assert role == FinalRole.C

    def test_b_for_moderate_cardinality(self) -> None:
        role, _ = classify_final_role(
            H_norm=0.3, cardinality=3, n_entities=60, coverage=1.0,
            len_mean=10, attribute_type="string",
        )
        assert role == FinalRole.B

    def test_small_group_below_floor(self) -> None:
        # Below small_group_floor=8, stricter C threshold
        role, _ = classify_final_role(
            H_norm=0.7, cardinality=3, n_entities=4, coverage=1.0,
            len_mean=10, attribute_type="string", small_group_floor=8,
        )
        assert role == FinalRole.B  # Not C despite H_norm=0.7


class TestBootstrapRole:
    def test_a_base_is_value_signal(self) -> None:
        profile = AttributeProfile(
            path="test", cardinality=1, entropy=0, entropy_norm=0,
            coverage=1.0, value_length_mean=5, value_length_var=0,
            attribute_type="string", final_role=FinalRole.A_BASE,
            bootstrap_role=BootstrapSignal.NONE, entity_type="test",
        )
        assert classify_bootstrap_role(profile) == BootstrapSignal.VALUE_SIGNAL

    def test_sparse_is_presence_signal(self) -> None:
        profile = AttributeProfile(
            path="test", cardinality=1, entropy=0, entropy_norm=0,
            coverage=0.1, value_length_mean=5, value_length_var=0,
            attribute_type="string", final_role=FinalRole.B,
            bootstrap_role=BootstrapSignal.NONE, entity_type="test",
        )
        assert classify_bootstrap_role(profile) == BootstrapSignal.PRESENCE_SIGNAL


class TestTierCStorage:
    def test_c_scalar_full_coverage_is_phone_book(self) -> None:
        profile = AttributeProfile(
            path="test", cardinality=60, entropy=5.0, entropy_norm=0.95,
            coverage=1.0, value_length_mean=10, value_length_var=0,
            attribute_type="string", final_role=FinalRole.C,
            bootstrap_role=BootstrapSignal.NONE, entity_type="test",
        )
        assert select_tier_c_storage(profile) == TierCStorage.PHONE_BOOK

    def test_composite_template_ref_never_phone_book(self) -> None:
        profile = AttributeProfile(
            path="test", cardinality=1, entropy=0, entropy_norm=0,
            coverage=1.0, value_length_mean=10, value_length_var=0,
            attribute_type="composite_template_ref", final_role=FinalRole.C,
            bootstrap_role=BootstrapSignal.NONE, entity_type="test",
        )
        assert select_tier_c_storage(profile) == TierCStorage.INSTANCE_ATTRS

    def test_b_role_returns_none(self) -> None:
        profile = AttributeProfile(
            path="test", cardinality=3, entropy=1.0, entropy_norm=0.5,
            coverage=1.0, value_length_mean=10, value_length_var=0,
            attribute_type="string", final_role=FinalRole.B,
            bootstrap_role=BootstrapSignal.NONE, entity_type="test",
        )
        assert select_tier_c_storage(profile) == TierCStorage.NONE
