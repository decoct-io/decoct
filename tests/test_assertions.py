"""Tests for assertion models and loader."""

from pathlib import Path

import pytest

from decoct.assertions import Assertion, Match, load_assertions

FIXTURES = Path(__file__).parent / "fixtures" / "assertions"


class TestMatchModel:
    def test_match_with_value(self) -> None:
        m = Match(path="services.*.restart", value="always")
        assert m.path == "services.*.restart"
        assert m.value == "always"
        assert m.pattern is None

    def test_match_with_pattern(self) -> None:
        m = Match(path="services.*.image", pattern="^(?!.*:latest$)")
        assert m.pattern == "^(?!.*:latest$)"

    def test_match_with_range(self) -> None:
        m = Match(path="ports.*", range=[1, 65535])
        assert m.range == [1, 65535]


class TestAssertionModel:
    def test_assertion_minimal(self) -> None:
        a = Assertion(id="test-1", assert_="Test assertion", rationale="Testing", severity="must")
        assert a.id == "test-1"
        assert a.match is None
        assert a.exceptions is None

    def test_assertion_with_match(self) -> None:
        m = Match(path="services.*.image", pattern="^(?!.*:latest$)")
        a = Assertion(id="test-1", assert_="No latest", rationale="Reproducibility", severity="must", match=m)
        assert a.match is not None
        assert a.match.path == "services.*.image"


class TestLoadAssertions:
    def test_load_valid_assertions(self) -> None:
        assertions = load_assertions(FIXTURES / "docker-services.yaml")
        assert len(assertions) == 3

        # First: match with pattern
        assert assertions[0].id == "docker-no-latest"
        assert assertions[0].assert_ == "Image tags must be pinned to specific versions"
        assert assertions[0].match is not None
        assert assertions[0].match.pattern is not None
        assert assertions[0].severity == "must"
        assert assertions[0].example == "nginx:1.25.3"

        # Second: no match (LLM-context only)
        assert assertions[1].id == "docker-healthcheck"
        assert assertions[1].match is None
        assert assertions[1].source == "Enable infrastructure standards"

        # Third: match with value
        assert assertions[2].id == "docker-logging"
        assert assertions[2].match is not None
        assert assertions[2].match.value == "json-file"
        assert assertions[2].related == ["docker-healthcheck"]

    def test_load_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_assertions(FIXTURES / "nonexistent.yaml")

    def test_load_missing_assertions_key(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.yaml"
        f.write_text("something: else\n")
        with pytest.raises(ValueError, match="must contain an 'assertions' key"):
            load_assertions(f)

    def test_load_missing_required_field(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.yaml"
        f.write_text("assertions:\n  - assert: test\n    rationale: test\n    severity: must\n")
        with pytest.raises(ValueError, match="missing required field 'id'"):
            load_assertions(f)

    def test_load_invalid_severity(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.yaml"
        f.write_text("assertions:\n  - id: t\n    assert: t\n    rationale: t\n    severity: critical\n")
        with pytest.raises(ValueError, match="severity must be one of"):
            load_assertions(f)

    def test_load_match_missing_path(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.yaml"
        content = (
            "assertions:\n  - id: t\n    assert: t\n    rationale: t\n"
            "    severity: must\n    match:\n      value: test\n"
        )
        f.write_text(content)
        with pytest.raises(ValueError, match="Match missing required field 'path'"):
            load_assertions(f)

    def test_load_invalid_range(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.yaml"
        content = (
            "assertions:\n  - id: t\n    assert: t\n    rationale: t\n"
            "    severity: must\n    match:\n      path: x\n      range: [1]\n"
        )
        f.write_text(content)
        with pytest.raises(ValueError, match="range.*must be a list of"):
            load_assertions(f)
