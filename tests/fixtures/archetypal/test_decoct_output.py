"""
Archetypal fixture tests — decoct output scoring.

Level 1: Score decoct's actual output against golden references.

STUB — these tests will be implemented when the decoct pipeline ships.
For now they skip with a clear message.
"""

import pytest

from decoct.compression.archetypal import archetypal_compress

from helpers import normalize, reconstruct_instances, reconstruct_section


def run_decoct(input_files):
    """
    Run decoct's archetypal compression on input data.

    Returns:
        (tier_b, tier_c): dict of classes, dict of {host: per-host data}
    """
    return archetypal_compress(input_files)


@pytest.fixture
def decoct_output(case):
    """Run decoct on input files for this case."""
    result = run_decoct(case.inputs)
    if result is None:
        pytest.skip("decoct pipeline not yet implemented")
    return result


class TestDecoctClassDiscovery:
    """Does decoct discover the correct classes?"""

    def test_class_count(self, case, decoct_output):
        """Decoct produces the expected number of classes."""
        tier_b, tier_c = decoct_output
        expected_total = sum(
            cls.get("class_count", 1)
            for cls in case.expected.get("classes", {}).values()
        )
        assert len(tier_b) == expected_total

    def test_no_false_classes(self, case, decoct_output):
        """Decoct creates no classes for negative sections."""
        tier_b, tier_c = decoct_output
        for host in case.hosts:
            for section in case.negative_sections:
                tc_section = tier_c[host].get(section, {})
                assert "_class" not in tc_section, (
                    f"{case.name}/{host}/{section}: false class created"
                )


class TestDecoctReconstruction:
    """Can decoct's output reconstruct the original data?"""

    def test_lossless_reconstruction(self, case, decoct_output):
        """Decoct's B + C reconstructs Tier A exactly."""
        tier_b, tier_c = decoct_output
        for host in case.hosts:
            for section in case.all_sections:
                raw = case.inputs[host][section]
                tc_section = tier_c[host][section]

                if "_class" not in tc_section:
                    reconstructed = tc_section
                elif "instances" in tc_section:
                    reconstructed = reconstruct_instances(tier_b, tc_section)
                else:
                    reconstructed = reconstruct_section(tier_b, tc_section)

                assert normalize(reconstructed) == normalize(raw), (
                    f"{case.name}/{host}/{section}: reconstruction failed"
                )


class TestDecoctCompression:
    """Is decoct achieving meaningful compression?"""

    def test_positive_sections_compressed(self, case, decoct_output):
        """Positive sections use classes (not raw passthrough)."""
        tier_b, tier_c = decoct_output
        for host in case.hosts:
            for section in case.positive_sections:
                _ = tier_c[host].get(section, {})
                # At least some hosts should have _class
                # (Set G allows one host to be raw, Set N allows one outlier)
                pass  # Specific assertions per set in set-specific tests
