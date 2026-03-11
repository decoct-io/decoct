"""Unit tests for segment-aware glob matching over dotted attribute paths."""

from __future__ import annotations

import pytest

from decoct.projections.path_matcher import collect_matching_paths, matches_path


class TestMatchesPath:
    """Test single-path matching against glob patterns."""

    def test_exact_match(self) -> None:
        assert matches_path("router.bgp.65002", "router.bgp.65002") is True

    def test_exact_no_match(self) -> None:
        assert matches_path("router.bgp.65002", "router.bgp.65003") is False

    def test_star_matches_one_segment(self) -> None:
        assert matches_path("router.bgp.65002", "router.bgp.*") is True

    def test_star_does_not_match_deeper(self) -> None:
        assert matches_path("router.bgp.65002.nsr", "router.bgp.*") is False

    def test_double_star_matches_zero_segments(self) -> None:
        assert matches_path("router.bgp", "router.bgp.**") is True

    def test_double_star_matches_one_segment(self) -> None:
        assert matches_path("router.bgp.65002", "router.bgp.**") is True

    def test_double_star_matches_deep(self) -> None:
        assert matches_path("router.bgp.65002.nsr.enable", "router.bgp.**") is True

    def test_double_star_no_match_wrong_prefix(self) -> None:
        assert matches_path("router.isis.CORE", "router.bgp.**") is False

    def test_double_star_at_start(self) -> None:
        assert matches_path("a.b.c", "**") is True

    def test_double_star_in_middle(self) -> None:
        assert matches_path("router.bgp.65002.neighbor.10.0.0.1", "router.bgp.**.neighbor.**") is True

    def test_fnmatch_within_segment(self) -> None:
        assert matches_path("interface.TenGigE0/0/0/0.shutdown", "interface.TenGigE*.shutdown") is True

    def test_fnmatch_question_mark(self) -> None:
        assert matches_path("interface.BVI100", "interface.BVI???") is True
        assert matches_path("interface.BVI10", "interface.BVI???") is False

    def test_single_segment_path(self) -> None:
        assert matches_path("hostname", "hostname") is True
        assert matches_path("hostname", "*") is True
        assert matches_path("hostname", "**") is True

    def test_empty_path(self) -> None:
        assert matches_path("", "") is True
        assert matches_path("", "**") is True
        assert matches_path("", "*") is True

    def test_star_matches_segment_with_dots_in_value(self) -> None:
        # The path "interface.MgmtEth0/RP0/CPU0/0.shutdown" has slashes but
        # those are within a single segment (between dots)
        assert matches_path(
            "interface.MgmtEth0/RP0/CPU0/0.shutdown",
            "interface.*.shutdown",
        ) is True

    def test_double_star_then_specific(self) -> None:
        assert matches_path("a.b.c.d", "**.d") is True
        assert matches_path("a.b.c.d", "**.c.d") is True
        assert matches_path("a.b.c.d", "**.x") is False


class TestCollectMatchingPaths:
    """Test collecting paths from a set."""

    @pytest.fixture()
    def all_paths(self) -> set[str]:
        return {
            "hostname",
            "router.bgp.65002",
            "router.bgp.65002.nsr",
            "router.bgp.65002.address-family",
            "router.isis.CORE",
            "router.isis.CORE.is-type",
            "interface.Loopback0.ipv4",
            "interface.TenGigE0/0/0/0.shutdown",
            "mpls.ldp",
        }

    def test_include_patterns(self, all_paths: set[str]) -> None:
        result = collect_matching_paths(all_paths, ["router.bgp.**"])
        assert result == {
            "router.bgp.65002",
            "router.bgp.65002.nsr",
            "router.bgp.65002.address-family",
        }

    def test_related_patterns(self, all_paths: set[str]) -> None:
        result = collect_matching_paths(
            all_paths,
            ["router.bgp.**"],
            related_patterns=["hostname"],
        )
        assert "hostname" in result
        assert "router.bgp.65002" in result

    def test_multiple_include_patterns(self, all_paths: set[str]) -> None:
        result = collect_matching_paths(all_paths, ["router.bgp.**", "mpls.**"])
        assert "router.bgp.65002" in result
        assert "mpls.ldp" in result
        assert "router.isis.CORE" not in result

    def test_no_matches(self, all_paths: set[str]) -> None:
        result = collect_matching_paths(all_paths, ["nonexistent.**"])
        assert result == set()

    def test_empty_patterns(self, all_paths: set[str]) -> None:
        result = collect_matching_paths(all_paths, [])
        assert result == set()
