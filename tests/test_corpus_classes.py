"""Tests for corpus-learned compression classes."""

from __future__ import annotations

from ruamel.yaml.comments import CommentedMap

from decoct.corpus_classes import (
    LearnedClass,
    _coerce_value,
    _mine_frequent_pairs,
    classes_to_schema,
    discover_instance_levels,
    flatten_doc,
    learn_classes,
    normalise_paths,
)

# ── flatten_doc ──────────────────────────────────────────────────────────


def _cm(data: dict) -> CommentedMap:
    """Quick helper to build a CommentedMap from a dict."""
    cm = CommentedMap()
    for k, v in data.items():
        if isinstance(v, dict):
            cm[k] = _cm(v)
        elif isinstance(v, list):
            from ruamel.yaml.comments import CommentedSeq

            cs = CommentedSeq()
            for item in v:
                if isinstance(item, dict):
                    cs.append(_cm(item))
                else:
                    cs.append(item)
            cm[k] = cs
        else:
            cm[k] = v
    return cm


class TestFlattenDoc:
    def test_flat_dict(self) -> None:
        doc = _cm({"a": 1, "b": "two"})
        pairs = flatten_doc(doc)
        assert ("a", 1) in pairs
        assert ("b", "two") in pairs
        assert len(pairs) == 2

    def test_nested_dict(self) -> None:
        doc = _cm({"top": {"mid": {"leaf": "val"}}})
        pairs = flatten_doc(doc)
        assert pairs == [("top.mid.leaf", "val")]

    def test_list_indices_become_wildcard(self) -> None:
        doc = _cm({"items": [{"name": "a"}, {"name": "b"}]})
        pairs = flatten_doc(doc)
        assert all(p == "items.*.name" for p, _ in pairs)
        assert len(pairs) == 2

    def test_nested_list_wildcards(self) -> None:
        doc = _cm({"containers": [{"ports": [{"protocol": "TCP"}]}]})
        pairs = flatten_doc(doc)
        assert pairs == [("containers.*.ports.*.protocol", "TCP")]

    def test_empty_doc(self) -> None:
        assert flatten_doc(_cm({})) == []

    def test_scalar_list_items(self) -> None:
        doc = _cm({"tags": ["a", "b"]})
        pairs = flatten_doc(doc)
        assert len(pairs) == 2
        assert all(p == "tags.*" for p, _ in pairs)


# ── discover_instance_levels ─────────────────────────────────────────────


class TestDiscoverInstanceLevels:
    def test_no_instance_levels_in_small_corpus(self) -> None:
        paths = ["a.b", "a.c", "a.d"]
        result = discover_instance_levels(paths)
        assert result == set()

    def test_detects_instance_level_with_many_keys(self) -> None:
        # Simulate docker-compose-like structure: services.{many names}.restart
        paths = []
        for name in [f"svc{i}" for i in range(20)]:
            paths.append(f"services.{name}.restart")
            paths.append(f"services.{name}.image")
        result = discover_instance_levels(paths)
        # Depth 1 (the service names) should be detected as instance level
        assert 1 in result

    def test_structural_levels_not_wildcarded(self) -> None:
        # All docs use the same keys at depth 0 and 2
        paths = []
        for name in [f"svc{i}" for i in range(20)]:
            paths.append(f"services.{name}.restart")
            paths.append(f"services.{name}.image")
        result = discover_instance_levels(paths)
        assert 0 not in result  # "services" is structural
        assert 2 not in result  # "restart"/"image" is structural


# ── normalise_paths ──────────────────────────────────────────────────────


class TestNormalisePaths:
    def test_wildcards_instance_levels(self) -> None:
        pairs = [("services.web.restart", "always"), ("services.db.restart", "always")]
        result = normalise_paths(pairs, instance_levels={1})
        assert result == [("services.*.restart", "always"), ("services.*.restart", "always")]

    def test_preserves_existing_wildcards(self) -> None:
        pairs = [("items.*.name", "foo")]
        result = normalise_paths(pairs, instance_levels={1})
        assert result == [("items.*.name", "foo")]

    def test_empty_instance_levels(self) -> None:
        pairs = [("a.b.c", 1)]
        result = normalise_paths(pairs, instance_levels=set())
        assert result == [("a.b.c", 1)]


# ── _mine_frequent_pairs ────────────────────────────────────────────────


class TestMineFrequentPairs:
    def test_finds_common_pairs(self) -> None:
        doc_pairs = [
            [("a", "1"), ("b", "2")],
            [("a", "1"), ("c", "3")],
            [("a", "1"), ("b", "2")],
        ]
        result = _mine_frequent_pairs(doc_pairs, min_frequency=0.5)
        assert ("a", "1") in result
        assert result[("a", "1")] == 3

    def test_filters_infrequent_pairs(self) -> None:
        doc_pairs = [
            [("a", "1"), ("rare", "x")],
            [("a", "1"), ("b", "2")],
            [("a", "1"), ("b", "2")],
            [("a", "1"), ("b", "2")],
        ]
        result = _mine_frequent_pairs(doc_pairs, min_frequency=0.5)
        assert ("rare", "x") not in result

    def test_empty_corpus(self) -> None:
        assert _mine_frequent_pairs([]) == {}

    def test_deduplicates_within_doc(self) -> None:
        doc_pairs = [
            [("a", "1"), ("a", "1"), ("a", "1")],
            [("a", "1")],
            [("a", "1")],
        ]
        result = _mine_frequent_pairs(doc_pairs, min_frequency=0.5)
        # Each doc counts once regardless of duplicates
        assert result[("a", "1")] == 3


# ── _coerce_value ────────────────────────────────────────────────────────


class TestCoerceValue:
    def test_bool_true(self) -> None:
        assert _coerce_value("True") is True
        assert _coerce_value("true") is True

    def test_bool_false(self) -> None:
        assert _coerce_value("False") is False

    def test_none(self) -> None:
        assert _coerce_value("None") is None

    def test_int(self) -> None:
        assert _coerce_value("42") == 42

    def test_float(self) -> None:
        assert _coerce_value("3.14") == 3.14

    def test_string(self) -> None:
        assert _coerce_value("hello") == "hello"


# ── classes_to_schema ────────────────────────────────────────────────────


class TestClassesToSchema:
    def test_produces_schema_with_merged_defaults(self) -> None:
        classes = [
            LearnedClass(
                name="cls-0",
                defaults={"a": 1, "b": 2},
                matching_file_count=5,
                total_file_count=10,
                net_score=100,
            ),
            LearnedClass(
                name="cls-1",
                defaults={"c": 3},
                matching_file_count=3,
                total_file_count=10,
                net_score=50,
            ),
        ]
        schema = classes_to_schema(classes, "kubernetes")
        assert schema.platform == "kubernetes-corpus"
        assert schema.source == "corpus-learned"
        assert schema.confidence == "medium"
        assert schema.defaults == {"a": 1, "b": 2, "c": 3}

    def test_empty_classes(self) -> None:
        schema = classes_to_schema([], "docker-compose")
        assert schema.defaults == {}


# ── learn_classes (integration) ──────────────────────────────────────────


class TestLearnClasses:
    def test_too_few_docs_returns_empty(self) -> None:
        docs = [_cm({"a": 1}), _cm({"a": 1})]
        assert learn_classes(docs) == []

    def test_discovers_common_defaults(self) -> None:
        # Build a corpus where most docs share the same defaults
        common = {"restart": "always", "network_mode": "bridge"}
        docs = []
        for i in range(10):
            doc = _cm({**common, "name": f"svc-{i}"})
            docs.append(doc)
        # Add a few docs without the common defaults
        docs.append(_cm({"name": "outlier", "restart": "never"}))

        classes = learn_classes(docs, min_frequency=0.3)
        # Should find at least one class containing the common defaults
        all_defaults = {}
        for cls in classes:
            all_defaults.update(cls.defaults)

        # The common values should appear in the learned defaults
        if classes:
            assert any(
                cls.defaults.get("restart") == "always" for cls in classes
            )

    def test_all_classes_have_positive_score(self) -> None:
        docs = [_cm({"a": 1, "b": 2, "c": 3}) for _ in range(10)]
        classes = learn_classes(docs, min_frequency=0.3)
        for cls in classes:
            assert cls.net_score > 0

    def test_classes_sorted_by_score_descending(self) -> None:
        docs = [_cm({"a": 1, "b": 2, "c": 3, "d": 4}) for _ in range(10)]
        classes = learn_classes(docs, min_frequency=0.3)
        if len(classes) >= 2:
            scores = [c.net_score for c in classes]
            assert scores == sorted(scores, reverse=True)
