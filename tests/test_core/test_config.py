"""Tests for EntityGraphConfig defaults matching spec §11.3."""

from decoct.core.config import EntityGraphConfig


class TestConfigDefaults:
    def test_composite_decompose_threshold(self) -> None:
        c = EntityGraphConfig()
        assert c.composite_decompose_threshold == 5

    def test_min_class_support(self) -> None:
        c = EntityGraphConfig()
        assert c.min_class_support == 3

    def test_max_class_bundle_size(self) -> None:
        c = EntityGraphConfig()
        assert c.max_class_bundle_size == 3

    def test_min_subclass_size(self) -> None:
        c = EntityGraphConfig()
        assert c.min_subclass_size == 3

    def test_small_group_floor(self) -> None:
        c = EntityGraphConfig()
        assert c.small_group_floor == 8

    def test_max_anti_unify_variables(self) -> None:
        c = EntityGraphConfig()
        assert c.max_anti_unify_variables == 3

    def test_subclass_overhead_tokens(self) -> None:
        c = EntityGraphConfig()
        assert c.subclass_overhead_tokens == 12

    def test_max_bootstrap_iterations(self) -> None:
        c = EntityGraphConfig()
        assert c.max_bootstrap_iterations == 5
