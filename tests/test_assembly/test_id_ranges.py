"""Tests for tier building, ID range compression, and structural invariants."""

from decoct.assembly.tier_builder import compress_id_ranges, expand_id_ranges


class TestIdRangeCompression:
    def test_contiguous_range(self) -> None:
        ids = ["BNG-01", "BNG-02", "BNG-03", "BNG-04"]
        compressed = compress_id_ranges(ids)
        assert compressed == ["BNG-01..BNG-04"]

    def test_round_trip(self) -> None:
        ids = ["BNG-01", "BNG-02", "BNG-03", "BNG-04"]
        compressed = compress_id_ranges(ids)
        expanded = expand_id_ranges(compressed)
        assert expanded == ids

    def test_non_contiguous(self) -> None:
        ids = ["BNG-01", "BNG-02", "BNG-05"]
        compressed = compress_id_ranges(ids)
        assert compressed == ["BNG-01..BNG-02", "BNG-05"]

    def test_singleton(self) -> None:
        ids = ["BNG-01"]
        compressed = compress_id_ranges(ids)
        assert compressed == ["BNG-01"]

    def test_no_numeric_suffix(self) -> None:
        ids = ["RouterA", "RouterB"]
        compressed = compress_id_ranges(ids)
        assert compressed == ["RouterA", "RouterB"]

    def test_empty(self) -> None:
        assert compress_id_ranges([]) == []

    def test_mixed_prefixes(self) -> None:
        ids = ["APE-01", "APE-02", "BNG-01", "BNG-02"]
        compressed = compress_id_ranges(ids)
        assert compressed == ["APE-01..APE-02", "BNG-01..BNG-02"]

    def test_round_trip_complex(self) -> None:
        ids = ["APE-R1-01", "APE-R1-02", "APE-R1-03", "APE-R2-01"]
        compressed = compress_id_ranges(ids)
        expanded = expand_id_ranges(compressed)
        assert expanded == ids

    def test_zero_padding_preserved(self) -> None:
        ids = ["R-001", "R-002", "R-003"]
        compressed = compress_id_ranges(ids)
        assert compressed == ["R-001..R-003"]
        expanded = expand_id_ranges(compressed)
        assert expanded == ids
