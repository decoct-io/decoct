"""Tests for pipeline framework."""

from __future__ import annotations

from typing import Any

import pytest
from ruamel.yaml import YAML

from decoct.passes.base import (
    BasePass,
    PassResult,
    clear_registry,
    get_pass,
    list_passes,
    register_pass,
)
from decoct.pipeline import Pipeline, _topological_sort

# ── Test passes ──


class FakePassA(BasePass):
    name = "fake-a"
    run_after: list[str] = []
    run_before: list[str] = []

    def run(self, doc: Any, **kwargs: Any) -> PassResult:
        doc["a_ran"] = True
        return PassResult(name=self.name, items_removed=1)


class FakePassB(BasePass):
    name = "fake-b"
    run_after = ["fake-a"]
    run_before: list[str] = []

    def run(self, doc: Any, **kwargs: Any) -> PassResult:
        doc["b_ran"] = True
        return PassResult(name=self.name, items_removed=2)


class FakePassC(BasePass):
    name = "fake-c"
    run_after: list[str] = []
    run_before = ["fake-b"]

    def run(self, doc: Any, **kwargs: Any) -> PassResult:
        doc["c_ran"] = True
        return PassResult(name=self.name, items_removed=0)


# ── Registry tests ──


class TestPassRegistry:
    def setup_method(self) -> None:
        clear_registry()

    def test_register_and_lookup(self) -> None:
        register_pass(FakePassA)
        assert get_pass("fake-a") is FakePassA

    def test_list_passes(self) -> None:
        register_pass(FakePassA)
        register_pass(FakePassB)
        assert list_passes() == ["fake-a", "fake-b"]

    def test_unknown_pass_raises(self) -> None:
        with pytest.raises(KeyError, match="Unknown pass 'nope'"):
            get_pass("nope")

    def test_register_without_name_raises(self) -> None:
        class BadPass(BasePass):
            name = ""

        with pytest.raises(ValueError, match="must define a 'name'"):
            register_pass(BadPass)

    def test_clear_registry(self) -> None:
        register_pass(FakePassA)
        assert list_passes() == ["fake-a"]
        clear_registry()
        assert list_passes() == []


# ── Topological sort tests ──


class TestTopologicalSort:
    def test_respects_run_after(self) -> None:
        a, b = FakePassA(), FakePassB()
        result = _topological_sort([b, a])
        names = [p.name for p in result]
        assert names.index("fake-a") < names.index("fake-b")

    def test_respects_run_before(self) -> None:
        b, c = FakePassB(), FakePassC()
        result = _topological_sort([b, c])
        names = [p.name for p in result]
        assert names.index("fake-c") < names.index("fake-b")

    def test_combined_ordering(self) -> None:
        a, b, c = FakePassA(), FakePassB(), FakePassC()
        result = _topological_sort([c, b, a])
        names = [p.name for p in result]
        # a before b (run_after), c before b (run_before)
        assert names.index("fake-a") < names.index("fake-b")
        assert names.index("fake-c") < names.index("fake-b")

    def test_cycle_detection(self) -> None:
        class CycleX(BasePass):
            name = "cycle-x"
            run_after = ["cycle-y"]
            run_before: list[str] = []

            def run(self, doc: Any, **kwargs: Any) -> PassResult:
                return PassResult(name=self.name)

        class CycleY(BasePass):
            name = "cycle-y"
            run_after = ["cycle-x"]
            run_before: list[str] = []

            def run(self, doc: Any, **kwargs: Any) -> PassResult:
                return PassResult(name=self.name)

        with pytest.raises(ValueError, match="Cycle detected"):
            _topological_sort([CycleX(), CycleY()])

    def test_no_constraints(self) -> None:
        class P1(BasePass):
            name = "p1"
            run_after: list[str] = []
            run_before: list[str] = []

            def run(self, doc: Any, **kwargs: Any) -> PassResult:
                return PassResult(name=self.name)

        class P2(BasePass):
            name = "p2"
            run_after: list[str] = []
            run_before: list[str] = []

            def run(self, doc: Any, **kwargs: Any) -> PassResult:
                return PassResult(name=self.name)

        result = _topological_sort([P2(), P1()])
        assert len(result) == 2

    def test_ignores_missing_dependencies(self) -> None:
        # run_after referencing a pass not in the list is silently ignored
        result = _topological_sort([FakePassB()])
        assert len(result) == 1
        assert result[0].name == "fake-b"


# ── Pipeline tests ──


class TestPipeline:
    def test_pipeline_runs_in_order(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("{}\n")

        pipeline = Pipeline([FakePassB(), FakePassA()])
        stats = pipeline.run(doc)

        assert doc["a_ran"] is True
        assert doc["b_ran"] is True
        assert stats.pass_results[0].name == "fake-a"
        assert stats.pass_results[1].name == "fake-b"

    def test_pipeline_pass_names(self) -> None:
        pipeline = Pipeline([FakePassB(), FakePassC(), FakePassA()])
        names = pipeline.pass_names
        assert names.index("fake-a") < names.index("fake-b")
        assert names.index("fake-c") < names.index("fake-b")

    def test_pipeline_collects_stats(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("{}\n")

        pipeline = Pipeline([FakePassA(), FakePassB()])
        stats = pipeline.run(doc)

        assert len(stats.pass_results) == 2
        assert stats.pass_results[0].items_removed == 1
        assert stats.pass_results[1].items_removed == 2
        assert "fake-a" in stats.pass_timings
        assert "fake-b" in stats.pass_timings
        assert stats.total_time >= 0

    def test_pipeline_passes_kwargs(self) -> None:
        class KwargsPass(BasePass):
            name = "kwargs-pass"
            run_after: list[str] = []
            run_before: list[str] = []

            def run(self, doc: Any, **kwargs: Any) -> PassResult:
                doc["received"] = kwargs.get("test_key")
                return PassResult(name=self.name)

        yaml = YAML(typ="rt")
        doc = yaml.load("{}\n")
        pipeline = Pipeline([KwargsPass()])
        pipeline.run(doc, test_key="test_value")
        assert doc["received"] == "test_value"

    def test_empty_pipeline(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("key: value\n")
        pipeline = Pipeline([])
        stats = pipeline.run(doc)
        assert doc["key"] == "value"
        assert len(stats.pass_results) == 0
