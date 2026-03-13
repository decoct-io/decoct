"""Tests for the swappable compression engine ABC + registry."""

from __future__ import annotations

import pytest

from decoct.compression import ArchetypalEngine, CompressionEngine, GreedyBundleEngine, get_engine, registry
from decoct.core.config import EntityGraphConfig
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import AttributeProfile, ClassHierarchy, Entity

# ── Registry tests ───────────────────────────────────────────────────


def test_archetypal_is_registered_by_default() -> None:
    assert "archetypal" in registry.available()


def test_greedy_bundle_is_registered_by_default() -> None:
    assert "greedy-bundle" in registry.available()


def test_get_engine_returns_archetypal() -> None:
    engine = get_engine("archetypal")
    assert isinstance(engine, ArchetypalEngine)


def test_get_engine_returns_greedy_bundle() -> None:
    engine = get_engine("greedy-bundle")
    assert isinstance(engine, GreedyBundleEngine)


def test_unknown_engine_raises_key_error() -> None:
    with pytest.raises(KeyError, match="Unknown compression engine 'nonexistent'"):
        get_engine("nonexistent")


def test_duplicate_registration_raises_value_error() -> None:
    from decoct.compression.engine import _EngineRegistry

    reg = _EngineRegistry()

    class DummyEngine(CompressionEngine):
        def compress(
            self,
            type_map: dict[str, list[Entity]],
            graph: EntityGraph,
            profiles: dict[str, dict[str, AttributeProfile]],
            config: EntityGraphConfig,
        ) -> dict[str, ClassHierarchy]:
            return {}

        def name(self) -> str:
            return "dummy"

    reg.register(DummyEngine)
    with pytest.raises(ValueError, match="already registered"):
        reg.register(DummyEngine)


def test_custom_engine_registration() -> None:
    from decoct.compression.engine import _EngineRegistry

    reg = _EngineRegistry()

    class CustomEngine(CompressionEngine):
        def compress(
            self,
            type_map: dict[str, list[Entity]],
            graph: EntityGraph,
            profiles: dict[str, dict[str, AttributeProfile]],
            config: EntityGraphConfig,
        ) -> dict[str, ClassHierarchy]:
            return {}

        def name(self) -> str:
            return "custom"

    reg.register(CustomEngine)
    assert "custom" in reg.available()
    engine = reg.get("custom")
    assert isinstance(engine, CustomEngine)
    assert engine.name() == "custom"


def test_available_returns_sorted_names() -> None:
    from decoct.compression.engine import _EngineRegistry

    reg = _EngineRegistry()

    class ZEngine(CompressionEngine):
        def compress(self, type_map: dict[str, list[Entity]], graph: EntityGraph,
                     profiles: dict[str, dict[str, AttributeProfile]],
                     config: EntityGraphConfig) -> dict[str, ClassHierarchy]:
            return {}

        def name(self) -> str:
            return "z-engine"

    class AEngine(CompressionEngine):
        def compress(self, type_map: dict[str, list[Entity]], graph: EntityGraph,
                     profiles: dict[str, dict[str, AttributeProfile]],
                     config: EntityGraphConfig) -> dict[str, ClassHierarchy]:
            return {}

        def name(self) -> str:
            return "a-engine"

    reg.register(ZEngine)
    reg.register(AEngine)
    assert reg.available() == ["a-engine", "z-engine"]


# ── ArchetypalEngine tests ──────────────────────────────────────────


def test_archetypal_engine_name() -> None:
    engine = ArchetypalEngine()
    assert engine.name() == "archetypal"


def test_archetypal_engine_is_compression_engine() -> None:
    engine = ArchetypalEngine()
    assert isinstance(engine, CompressionEngine)


# ── GreedyBundleEngine tests ────────────────────────────────────────


def test_greedy_bundle_engine_name() -> None:
    engine = GreedyBundleEngine()
    assert engine.name() == "greedy-bundle"


def test_greedy_bundle_engine_is_compression_engine() -> None:
    engine = GreedyBundleEngine()
    assert isinstance(engine, CompressionEngine)


# ── Config default test ──────────────────────────────────────────────


def test_config_default_compression_engine() -> None:
    config = EntityGraphConfig()
    assert config.compression_engine == "archetypal"
