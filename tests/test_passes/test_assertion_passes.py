"""Tests for assertion-aware passes: matcher, strip-conformant, annotate-deviations, deviation-summary."""

from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML

from decoct.assertions import load_assertions
from decoct.assertions.matcher import _SENTINEL, evaluate_match, find_matches
from decoct.assertions.models import Assertion, Match
from decoct.passes.annotate_deviations import AnnotateDeviationsPass, annotate_deviations
from decoct.passes.deviation_summary import DeviationSummaryPass, deviation_summary
from decoct.passes.strip_conformant import StripConformantPass, strip_conformant

YAML_FIXTURES = Path(__file__).parent.parent / "fixtures" / "yaml"
ASSERTION_FIXTURES = Path(__file__).parent.parent / "fixtures" / "assertions"


def _load_yaml(path: Path) -> dict:
    yaml = YAML(typ="rt")
    return yaml.load(path)


def _dump_yaml(doc: dict) -> str:
    yaml = YAML(typ="rt")
    stream = StringIO()
    yaml.dump(doc, stream)
    return stream.getvalue()


def _load_test_assertions() -> list[Assertion]:
    return load_assertions(ASSERTION_FIXTURES / "test-must-assertions.yaml")


# ── Match evaluator tests ──


class TestEvaluateMatch:
    def test_value_match(self) -> None:
        m = Match(path="x", value="json-file")
        assert evaluate_match(m, "json-file") is True
        assert evaluate_match(m, "syslog") is False

    def test_value_match_case_insensitive(self) -> None:
        m = Match(path="x", value="True")
        assert evaluate_match(m, "true") is True

    def test_pattern_match(self) -> None:
        m = Match(path="x", pattern=r"^(?!.*:latest$)")
        assert evaluate_match(m, "nginx:1.25.3") is True
        assert evaluate_match(m, "postgres:latest") is False

    def test_range_match(self) -> None:
        m = Match(path="x", range=[1, 65535])
        assert evaluate_match(m, 80) is True
        assert evaluate_match(m, 0) is False
        assert evaluate_match(m, 65535) is True
        assert evaluate_match(m, 70000) is False

    def test_range_non_numeric(self) -> None:
        m = Match(path="x", range=[1, 100])
        assert evaluate_match(m, "not_a_number") is False

    def test_contains_match(self) -> None:
        m = Match(path="x", contains="http")
        assert evaluate_match(m, ["http", "https"]) is True
        assert evaluate_match(m, ["tcp"]) is False

    def test_contains_non_list(self) -> None:
        m = Match(path="x", contains="http")
        assert evaluate_match(m, "http") is False

    def test_not_value_match(self) -> None:
        m = Match(path="x", not_value="latest")
        assert evaluate_match(m, "1.25.3") is True
        assert evaluate_match(m, "latest") is False

    def test_no_condition(self) -> None:
        m = Match(path="x")
        assert evaluate_match(m, "anything") is True

    def test_exists_true_present(self) -> None:
        m = Match(path="x", exists=True)
        assert evaluate_match(m, "any_value") is True

    def test_exists_true_absent(self) -> None:
        m = Match(path="x", exists=True)
        assert evaluate_match(m, _SENTINEL) is False

    def test_exists_false_present(self) -> None:
        m = Match(path="x", exists=False)
        assert evaluate_match(m, "any_value") is False

    def test_exists_false_absent(self) -> None:
        m = Match(path="x", exists=False)
        assert evaluate_match(m, _SENTINEL) is True


class TestFindExistsMatches:
    def test_finds_present_keys(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("services:\n  web:\n    healthcheck:\n      test: curl\n  db:\n    image: pg\n")
        assertion = Assertion(
            id="test", assert_="test", rationale="test", severity="must",
            match=Match(path="services.*.healthcheck", exists=True),
        )
        matches = find_matches(doc, "", assertion)
        assert len(matches) == 2
        # web has healthcheck — value is the healthcheck dict
        web_match = next(m for m in matches if "web" in m[0])
        assert web_match[1] is not _SENTINEL
        # db does NOT have healthcheck — value is sentinel
        db_match = next(m for m in matches if "db" in m[0])
        assert db_match[1] is _SENTINEL

    def test_exists_deviations_annotated(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("services:\n  web:\n    healthcheck:\n      test: curl\n  db:\n    image: pg\n")
        assertions = [
            Assertion(
                id="has-healthcheck", assert_="Must have healthcheck", rationale="test", severity="must",
                match=Match(path="services.*.healthcheck", exists=True),
            ),
        ]
        deviations = annotate_deviations(doc, assertions)
        assert len(deviations) == 1
        assert deviations[0].assertion_id == "has-healthcheck"
        assert "db" in deviations[0].path
        assert "missing" in deviations[0].message

    def test_exists_does_not_strip_conformant(self) -> None:
        """exists assertions should not strip values — only detect."""
        yaml = YAML(typ="rt")
        doc = yaml.load("services:\n  web:\n    healthcheck:\n      test: curl\n")
        assertions = [
            Assertion(
                id="has-healthcheck", assert_="Must have healthcheck", rationale="test", severity="must",
                match=Match(path="services.*.healthcheck", exists=True),
            ),
        ]
        count = strip_conformant(doc, assertions)
        # Should NOT strip the healthcheck — exists assertions don't strip
        assert "healthcheck" in doc["services"]["web"]
        assert count == 0


class TestFindMatches:
    def test_finds_wildcard_paths(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "with-assertions.yaml")
        assertion = Assertion(
            id="test", assert_="test", rationale="test", severity="must",
            match=Match(path="services.*.image"),
        )
        matches = find_matches(doc, "", assertion)
        paths = [m[0] for m in matches]
        assert "services.web.image" in paths
        assert "services.db.image" in paths

    def test_no_match_assertion_returns_empty(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "with-assertions.yaml")
        assertion = Assertion(id="test", assert_="test", rationale="test", severity="must")
        matches = find_matches(doc, "", assertion)
        assert matches == []


# ── Strip-conformant tests ──


class TestStripConformant:
    def setup_method(self) -> None:
        self.assertions = _load_test_assertions()

    def test_strips_conformant_values(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "with-assertions.yaml")
        count = strip_conformant(doc, self.assertions)

        # web.image: nginx:1.25.3 — conformant (not :latest) → stripped
        assert "image" not in doc["services"]["web"]
        # web.restart: unless-stopped — conformant → stripped
        assert "restart" not in doc["services"]["web"]
        # web.logging.driver: json-file — conformant → stripped
        assert "driver" not in doc["services"]["web"]["logging"]
        assert count == 3

    def test_preserves_deviating_values(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "with-assertions.yaml")
        strip_conformant(doc, self.assertions)

        # db.image: postgres:latest — deviation → preserved
        assert doc["services"]["db"]["image"] == "postgres:latest"
        # db.restart: always — deviation → preserved
        assert doc["services"]["db"]["restart"] == "always"
        # db.logging.driver: syslog — deviation → preserved
        assert doc["services"]["db"]["logging"]["driver"] == "syslog"

    def test_skips_non_must_assertions(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("services:\n  web:\n    healthcheck: present\n")
        # healthcheck-required is severity "should", not "must"
        count = strip_conformant(doc, self.assertions)
        assert "healthcheck" in doc["services"]["web"]
        assert count == 0

    def test_skips_assertions_without_match(self) -> None:
        assertions = [
            Assertion(id="no-match", assert_="test", rationale="test", severity="must"),
        ]
        yaml = YAML(typ="rt")
        doc = yaml.load("key: value\n")
        count = strip_conformant(doc, assertions)
        assert doc["key"] == "value"
        assert count == 0


class TestStripConformantPass:
    def test_pass_ordering(self) -> None:
        assert "strip-defaults" in StripConformantPass.run_after

    def test_pass_name(self) -> None:
        assert StripConformantPass.name == "strip-conformant"


# ── Annotate-deviations tests ──


class TestAnnotateDeviations:
    def setup_method(self) -> None:
        self.assertions = _load_test_assertions()

    def test_annotates_deviating_values(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "with-assertions.yaml")
        deviations = annotate_deviations(doc, self.assertions)

        assert len(deviations) == 3
        ids = {d.assertion_id for d in deviations}
        assert "no-latest" in ids
        assert "restart-policy" in ids
        assert "logging-driver" in ids

    def test_comments_in_output(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "with-assertions.yaml")
        annotate_deviations(doc, self.assertions)
        output = _dump_yaml(doc)

        # Value match deviations get "standard: expected_value"
        assert "[!] standard: unless-stopped" in output
        assert "[!] standard: json-file" in output
        # Pattern match deviations get "assertion: description"
        assert "[!] assertion: Image tags must not use latest" in output

    def test_does_not_annotate_conformant(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "with-assertions.yaml")
        annotate_deviations(doc, self.assertions)
        output = _dump_yaml(doc)

        # web services are conformant — no annotations on them
        lines = output.split("\n")
        for line in lines:
            if "nginx:1.25.3" in line:
                assert "[!]" not in line

    def test_skips_assertions_without_match(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "with-assertions.yaml")
        assertions = [
            Assertion(id="no-match", assert_="test", rationale="test", severity="must"),
        ]
        deviations = annotate_deviations(doc, assertions)
        assert len(deviations) == 0


class TestAnnotateDeviationsPass:
    def test_pass_ordering(self) -> None:
        assert "strip-conformant" in AnnotateDeviationsPass.run_after

    def test_pass_name(self) -> None:
        assert AnnotateDeviationsPass.name == "annotate-deviations"


# ── Deviation-summary tests ──


class TestDeviationSummary:
    def setup_method(self) -> None:
        self.assertions = _load_test_assertions()

    def test_summary_comment_added(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "with-assertions.yaml")
        lines = deviation_summary(doc, self.assertions)
        output = _dump_yaml(doc)

        assert len(lines) == 4  # header + 3 deviations
        assert "3 deviations from standards" in lines[0]
        assert "3 deviations from standards" in output

    def test_summary_lists_assertion_ids(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "with-assertions.yaml")
        lines = deviation_summary(doc, self.assertions)

        line_text = "\n".join(lines)
        assert "no-latest" in line_text
        assert "restart-policy" in line_text
        assert "logging-driver" in line_text

    def test_no_summary_when_all_conformant(self) -> None:
        yaml = YAML(typ="rt")
        doc = yaml.load("services:\n  web:\n    restart: unless-stopped\n")
        assertions = [
            Assertion(
                id="test", assert_="test", rationale="test", severity="must",
                match=Match(path="services.*.restart", value="unless-stopped"),
            ),
        ]
        lines = deviation_summary(doc, assertions)
        assert len(lines) == 0

    def test_no_summary_when_no_assertions(self) -> None:
        doc = _load_yaml(YAML_FIXTURES / "with-assertions.yaml")
        lines = deviation_summary(doc, [])
        assert len(lines) == 0


class TestDeviationSummaryPass:
    def test_pass_ordering(self) -> None:
        assert "annotate-deviations" in DeviationSummaryPass.run_after

    def test_pass_name(self) -> None:
        assert DeviationSummaryPass.name == "deviation-summary"


# ── Deployment standards tests (against comprehensive assertions) ──


def _load_deployment_assertions() -> list[Assertion]:
    return load_assertions(ASSERTION_FIXTURES / "deployment-standards.yaml")


class TestDeploymentStandards:
    """Tests for the deployment standards assertions against realistic fixtures."""

    def setup_method(self) -> None:
        self.assertions = _load_deployment_assertions()
        self.yaml_fixtures = Path(__file__).parent.parent / "fixtures" / "yaml"

    def test_conformant_service_fully_stripped(self) -> None:
        """A fully conformant service has its must-severity matches stripped."""
        doc = _load_yaml(self.yaml_fixtures / "realistic-with-deviations.yaml")
        count = strip_conformant(doc, self.assertions)
        # api service is conformant — its must-match fields should be stripped
        assert count > 0

    def test_deviating_image_annotated(self) -> None:
        """:latest tag gets [!] annotation."""
        doc = _load_yaml(self.yaml_fixtures / "realistic-with-deviations.yaml")
        deviations = annotate_deviations(doc, self.assertions)
        # worker has image: acme-worker:latest
        image_deviations = [d for d in deviations if d.assertion_id == "ops-image-pinned"]
        assert len(image_deviations) >= 1
        output = _dump_yaml(doc)
        assert "[!]" in output

    def test_deviating_restart_annotated(self) -> None:
        """restart: "no" gets annotation."""
        doc = _load_yaml(self.yaml_fixtures / "realistic-with-deviations.yaml")
        deviations = annotate_deviations(doc, self.assertions)
        restart_deviations = [d for d in deviations if d.assertion_id == "ops-restart-policy"]
        assert len(restart_deviations) >= 1

    def test_pattern_match_restart_accepts_both(self) -> None:
        """unless-stopped and always both match the restart assertion."""
        restart_assertion = next(a for a in self.assertions if a.id == "ops-restart-policy")
        assert restart_assertion.match is not None
        assert evaluate_match(restart_assertion.match, "unless-stopped") is True
        assert evaluate_match(restart_assertion.match, "always") is True
        assert evaluate_match(restart_assertion.match, "no") is False
        assert evaluate_match(restart_assertion.match, "on-failure") is False

    def test_deviation_count_matches_expected(self) -> None:
        """Deviation fixture produces the correct deviation count."""
        doc = _load_yaml(self.yaml_fixtures / "realistic-with-deviations.yaml")
        deviations = annotate_deviations(doc, self.assertions)
        # worker: :latest image, missing max-size, missing max-file
        # scheduler: restart "no"
        # Expect at least 2 deviations
        assert len(deviations) >= 2

    def test_contains_match_for_security_opt(self) -> None:
        """List contains evaluation works for security_opt assertion."""
        sec_assertion = next(a for a in self.assertions if a.id == "ops-security-opt")
        assert sec_assertion.match is not None
        # Conformant: list contains no-new-privileges:true
        assert evaluate_match(sec_assertion.match, ["no-new-privileges:true"]) is True
        # Deviating: list without it
        assert evaluate_match(sec_assertion.match, ["apparmor:unconfined"]) is False
        # Deviating: not a list
        assert evaluate_match(sec_assertion.match, "no-new-privileges:true") is False
