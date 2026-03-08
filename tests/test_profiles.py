"""Tests for profile model and loader."""

from pathlib import Path

import pytest

from decoct.profiles import Profile, load_profile

FIXTURES = Path(__file__).parent / "fixtures" / "profiles"


class TestProfileModel:
    def test_profile_defaults(self) -> None:
        p = Profile()
        assert p.name is None
        assert p.schema_ref is None
        assert p.assertion_refs == []
        assert p.passes == {}

    def test_profile_with_all_fields(self) -> None:
        p = Profile(
            name="test",
            schema_ref="schemas/test.yaml",
            assertion_refs=["assertions/test.yaml"],
            passes={"strip-comments": {}},
        )
        assert p.name == "test"
        assert len(p.assertion_refs) == 1


class TestLoadProfile:
    def test_load_valid_profile(self) -> None:
        profile = load_profile(FIXTURES / "docker.yaml")
        assert profile.name == "docker-compose"
        assert profile.schema_ref == "schemas/docker-compose.yaml"
        assert len(profile.assertion_refs) == 1
        assert "strip-comments" in profile.passes
        assert "strip-defaults" in profile.passes
        assert profile.passes["strip-defaults"]["skip_low_confidence"] is True

    def test_load_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_profile(FIXTURES / "nonexistent.yaml")

    def test_load_non_mapping(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.yaml"
        f.write_text("- item1\n")
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            load_profile(f)

    def test_load_null_pass_config(self, tmp_path: Path) -> None:
        f = tmp_path / "profile.yaml"
        f.write_text("passes:\n  strip-comments:\n")
        profile = load_profile(f)
        assert profile.passes["strip-comments"] == {}

    def test_load_minimal_profile(self, tmp_path: Path) -> None:
        f = tmp_path / "profile.yaml"
        f.write_text("schema: test.yaml\n")
        profile = load_profile(f)
        assert profile.schema_ref == "test.yaml"
        assert profile.assertion_refs == []
        assert profile.passes == {}
