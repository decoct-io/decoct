"""decoct CLI."""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path
from typing import Any

import click
from ruamel.yaml import YAML

from decoct import __version__
from decoct.passes import annotate_deviations as _ad  # noqa: F401
from decoct.passes import deviation_summary as _ds  # noqa: F401
from decoct.passes import drop_fields as _df  # noqa: F401
from decoct.passes import keep_fields as _kf  # noqa: F401

# Import all pass modules so they register with the registry
from decoct.passes import strip_comments as _sc  # noqa: F401
from decoct.passes import strip_conformant as _sco  # noqa: F401
from decoct.passes import strip_defaults as _sd  # noqa: F401
from decoct.passes import strip_secrets as _ss  # noqa: F401


def _load_yaml_input(source: str | None) -> tuple[Any, str]:
    """Load YAML from a file path or stdin.

    Returns (document, raw_text) tuple.
    """
    yaml = YAML(typ="rt")
    if source is None or source == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(source).read_text()
    doc = yaml.load(raw)
    return doc, raw


def _dump_yaml(doc: Any) -> str:
    """Dump a YAML document to string."""
    yaml = YAML(typ="rt")
    stream = StringIO()
    yaml.dump(doc, stream)
    return stream.getvalue()


def _build_passes(
    schema_path: str | None,
    assertions_path: str | None,
    profile_path: str | None,
) -> tuple[list[Any], Any, list[Any]]:
    """Build pass instances from CLI options.

    Returns (passes, schema, assertions) tuple.
    """
    from decoct.assertions.loader import load_assertions
    from decoct.passes.annotate_deviations import AnnotateDeviationsPass
    from decoct.passes.base import get_pass
    from decoct.passes.deviation_summary import DeviationSummaryPass
    from decoct.passes.strip_comments import StripCommentsPass
    from decoct.passes.strip_conformant import StripConformantPass
    from decoct.passes.strip_defaults import StripDefaultsPass
    from decoct.passes.strip_secrets import StripSecretsPass
    from decoct.profiles.loader import load_profile
    from decoct.schemas.loader import load_schema

    schema = None
    assertions: list[Any] = []
    passes: list[Any] = []

    if profile_path:
        profile = load_profile(profile_path)
        profile_dir = Path(profile_path).parent

        # Load schema from profile ref
        if profile.schema_ref:
            schema_file = profile_dir / profile.schema_ref
            if schema_file.exists():
                schema = load_schema(schema_file)

        # Load assertions from profile refs
        for ref in profile.assertion_refs:
            assertion_file = profile_dir / ref
            if assertion_file.exists():
                assertions.extend(load_assertions(assertion_file))

        # Build passes from profile configuration
        for pass_name, config in profile.passes.items():
            pass_cls = get_pass(pass_name)
            if pass_cls == StripDefaultsPass and schema:
                passes.append(StripDefaultsPass(schema=schema, **config))
            elif pass_cls in (StripConformantPass, AnnotateDeviationsPass, DeviationSummaryPass):
                passes.append(pass_cls(assertions=assertions, **config))
            else:
                passes.append(pass_cls(**config))
    else:
        # Default pipeline: all passes in order
        passes.append(StripSecretsPass())
        passes.append(StripCommentsPass())

        if schema_path:
            schema = load_schema(schema_path)
            passes.append(StripDefaultsPass(schema=schema))

        if assertions_path:
            assertions = load_assertions(assertions_path)

        if assertions:
            passes.append(StripConformantPass(assertions=assertions))
            passes.append(AnnotateDeviationsPass(assertions=assertions))
            passes.append(DeviationSummaryPass(assertions=assertions))

    return passes, schema, assertions


@click.group()
@click.version_option(version=__version__, prog_name="decoct")
def cli() -> None:
    """decoct — infrastructure context compression for LLMs."""


@cli.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--schema", "schema_path", type=click.Path(exists=True), help="Schema file.")
@click.option("--assertions", "assertions_path", type=click.Path(exists=True), help="Assertions file.")
@click.option("--profile", "profile_path", type=click.Path(exists=True), help="Profile file.")
@click.option("--stats", is_flag=True, help="Show token statistics.")
@click.option("--stats-only", is_flag=True, help="Show only token statistics.")
@click.option("--show-removed", is_flag=True, help="Show what was stripped.")
@click.option("--output", "-o", type=click.Path(), help="Output file.")
@click.option("--encoding", default="cl100k_base", show_default=True, help="Tiktoken encoding for token counting.")
def compress(
    files: tuple[str, ...],
    schema_path: str | None,
    assertions_path: str | None,
    profile_path: str | None,
    stats: bool,
    stats_only: bool,
    show_removed: bool,
    output: str | None,
    encoding: str,
) -> None:
    """Compress infrastructure data for LLM context windows."""
    from decoct.pipeline import Pipeline
    from decoct.tokens import create_report, format_report

    # Determine input sources
    sources: list[str | None] = list(files) if files else [None]

    try:
        pass_instances, _schema, _assertions = _build_passes(schema_path, assertions_path, profile_path)
    except (ValueError, KeyError, FileNotFoundError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if not pass_instances:
        click.echo("No passes configured.", err=True)
        sys.exit(1)

    pipeline = Pipeline(pass_instances)

    for source in sources:
        try:
            doc, input_text = _load_yaml_input(source)
        except Exception as e:  # noqa: BLE001
            click.echo(f"Error reading input: {e}", err=True)
            sys.exit(1)

        pipeline_stats = pipeline.run(doc)
        output_text = _dump_yaml(doc)

        # Output compressed YAML
        if not stats_only:
            if output:
                Path(output).write_text(output_text)
            else:
                click.echo(output_text, nl=False)

        # Show what was removed
        if show_removed:
            for result in pipeline_stats.pass_results:
                if result.items_removed > 0 or result.details:
                    click.echo(f"--- {result.name} ---", err=True)
                    if result.items_removed > 0:
                        click.echo(f"  Removed: {result.items_removed} items", err=True)
                    for detail in result.details:
                        click.echo(f"  {detail}", err=True)

        # Show token stats
        if stats or stats_only:
            report = create_report(input_text, output_text, encoding)
            click.echo(format_report(report), err=True)
