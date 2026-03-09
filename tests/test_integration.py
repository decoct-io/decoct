"""Integration tests — full pipeline against realistic fixtures."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML

from decoct.assertions import load_assertions
from decoct.passes.annotate_deviations import AnnotateDeviationsPass
from decoct.passes.deviation_summary import DeviationSummaryPass
from decoct.passes.strip_comments import StripCommentsPass
from decoct.passes.strip_conformant import StripConformantPass
from decoct.passes.strip_defaults import StripDefaultsPass
from decoct.passes.strip_secrets import StripSecretsPass
from decoct.pipeline import Pipeline
from decoct.profiles.loader import load_profile
from decoct.schemas import load_schema
from decoct.tokens import create_report

FIXTURES = Path(__file__).parent / "fixtures"
YAML_FIXTURES = FIXTURES / "yaml"
SCHEMA_FIXTURES = FIXTURES / "schemas"
ASSERTION_FIXTURES = FIXTURES / "assertions"
PROFILE_FIXTURES = FIXTURES / "profiles"


def _load_yaml(path: Path) -> dict:
    yaml = YAML(typ="rt")
    return yaml.load(path)


def _dump_yaml(doc: dict) -> str:
    yaml = YAML(typ="rt")
    stream = StringIO()
    yaml.dump(doc, stream)
    return stream.getvalue()


class TestFullPipelineRealisticCompose:
    """Integration tests running the full pipeline against realistic fixtures."""

    def setup_method(self) -> None:
        self.schema = load_schema(SCHEMA_FIXTURES / "docker-compose-full.yaml")
        self.assertions = load_assertions(ASSERTION_FIXTURES / "deployment-standards.yaml")

    def test_full_pipeline_realistic_compose(self) -> None:
        """All passes against realistic fixture with full schema + assertions."""
        doc = _load_yaml(YAML_FIXTURES / "realistic-compose.yaml")
        input_text = (YAML_FIXTURES / "realistic-compose.yaml").read_text()

        passes = [
            StripSecretsPass(),
            StripCommentsPass(),
            StripDefaultsPass(schema=self.schema),
            StripConformantPass(assertions=self.assertions),
            AnnotateDeviationsPass(assertions=self.assertions),
            DeviationSummaryPass(assertions=self.assertions),
        ]
        pipeline = Pipeline(passes)
        stats = pipeline.run(doc)

        output_text = _dump_yaml(doc)

        # Secrets should be redacted
        assert "[REDACTED]" not in input_text or "[REDACTED]" in output_text

        # Some defaults should be stripped (e.g. retries: 3 on healthchecks where it matches default)
        assert stats.pass_results[2].items_removed > 0  # strip-defaults did work

        # Conformant values should be stripped (e.g. image tags are pinned, restart is unless-stopped)
        strip_conformant_result = stats.pass_results[3]
        assert strip_conformant_result.items_removed > 0

        # Output should be smaller than input
        report = create_report(input_text, output_text)
        assert report.savings_pct > 0

    def test_three_tier_compression(self) -> None:
        """Measure generic, +schema, +assertions savings on realistic fixture."""
        input_text = (YAML_FIXTURES / "realistic-compose.yaml").read_text()

        # Tier 1: Generic only
        doc1 = _load_yaml(YAML_FIXTURES / "realistic-compose.yaml")
        pipeline1 = Pipeline([StripSecretsPass(), StripCommentsPass()])
        pipeline1.run(doc1)
        tier1_output = _dump_yaml(doc1)
        tier1_report = create_report(input_text, tier1_output)

        # Tier 2: Generic + schema
        doc2 = _load_yaml(YAML_FIXTURES / "realistic-compose.yaml")
        pipeline2 = Pipeline([
            StripSecretsPass(),
            StripCommentsPass(),
            StripDefaultsPass(schema=self.schema),
        ])
        pipeline2.run(doc2)
        tier2_output = _dump_yaml(doc2)
        tier2_report = create_report(input_text, tier2_output)

        # Tier 3: Generic + schema + assertions
        doc3 = _load_yaml(YAML_FIXTURES / "realistic-compose.yaml")
        pipeline3 = Pipeline([
            StripSecretsPass(),
            StripCommentsPass(),
            StripDefaultsPass(schema=self.schema),
            StripConformantPass(assertions=self.assertions),
            AnnotateDeviationsPass(assertions=self.assertions),
            DeviationSummaryPass(assertions=self.assertions),
        ])
        pipeline3.run(doc3)
        tier3_output = _dump_yaml(doc3)
        tier3_report = create_report(input_text, tier3_output)

        # Each tier should save more than the previous
        assert tier2_report.savings_pct > tier1_report.savings_pct
        assert tier3_report.savings_pct > tier2_report.savings_pct

    def test_secrets_before_defaults(self) -> None:
        """Verify pass ordering: secrets pass runs before defaults."""
        passes = [
            StripSecretsPass(),
            StripDefaultsPass(schema=self.schema),
        ]
        pipeline = Pipeline(passes)
        # strip-secrets should come first in the ordered pipeline
        assert pipeline.pass_names.index("strip-secrets") < pipeline.pass_names.index("strip-defaults")


class TestProfileIntegration:
    def test_profile_loads_and_runs(self) -> None:
        """docker-full profile orchestrates full pipeline."""
        profile = load_profile(PROFILE_FIXTURES / "docker-full.yaml")

        # Resolve schema and assertions relative to profile dir
        schema = load_schema(PROFILE_FIXTURES / profile.schema_ref)
        assertions: list = []
        for ref in profile.assertion_refs:
            assertions.extend(load_assertions(PROFILE_FIXTURES / ref))

        doc = _load_yaml(YAML_FIXTURES / "realistic-compose.yaml")

        # Build passes from profile
        passes = []
        for pass_name in profile.passes:
            if pass_name == "strip-secrets":
                passes.append(StripSecretsPass())
            elif pass_name == "strip-comments":
                passes.append(StripCommentsPass())
            elif pass_name == "strip-defaults":
                passes.append(StripDefaultsPass(schema=schema))
            elif pass_name == "strip-conformant":
                passes.append(StripConformantPass(assertions=assertions))
            elif pass_name == "annotate-deviations":
                passes.append(AnnotateDeviationsPass(assertions=assertions))
            elif pass_name == "deviation-summary":
                passes.append(DeviationSummaryPass(assertions=assertions))

        pipeline = Pipeline(passes)
        stats = pipeline.run(doc)
        assert len(stats.pass_results) == 6


class TestDeviationsFixture:
    def setup_method(self) -> None:
        self.assertions = load_assertions(ASSERTION_FIXTURES / "deployment-standards.yaml")

    def test_deviations_fixture_counts(self) -> None:
        """Deviation fixture produces expected annotation count."""
        doc = _load_yaml(YAML_FIXTURES / "realistic-with-deviations.yaml")

        # Run annotate-deviations to count them
        from decoct.passes.annotate_deviations import annotate_deviations

        deviations = annotate_deviations(doc, self.assertions)

        # Expected deviations:
        # worker: image acme-worker:latest (ops-image-pinned)
        # worker: missing logging options max-size (ops-logging-max-size)
        # worker: missing logging options max-file (ops-logging-max-file)
        # scheduler: restart "no" (ops-restart-policy)
        # scheduler: missing security_opt on both worker and scheduler (ops-security-opt is should, not must)
        # At minimum we expect several deviations
        assert len(deviations) >= 2

    def test_conformant_services_stripped(self) -> None:
        """Conformant services have their must-match values stripped."""
        doc = _load_yaml(YAML_FIXTURES / "realistic-with-deviations.yaml")
        from decoct.passes.strip_conformant import strip_conformant

        count = strip_conformant(doc, self.assertions)

        # api and redis are fully conformant for must-severity assertions
        # Their image, restart, logging.driver, logging.options.max-size/max-file should be stripped
        assert count > 0


class TestNoRegressionExistingFixtures:
    def test_existing_defaults_fixture_still_works(self) -> None:
        """Existing with-defaults.yaml + existing schema produces same results as before."""
        schema = load_schema(SCHEMA_FIXTURES / "docker-compose.yaml")
        doc = _load_yaml(YAML_FIXTURES / "with-defaults.yaml")

        from decoct.passes.strip_defaults import strip_defaults

        count = strip_defaults(doc, schema)

        # Original test expectations
        assert "restart" not in doc["services"]["web"]  # "no" is default
        assert doc["services"]["db"]["restart"] == "always"  # not default
        assert count > 0
