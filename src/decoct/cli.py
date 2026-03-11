"""decoct CLI."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import click
from ruamel.yaml import YAML

from decoct import __version__
from decoct.passes import annotate_deviations as _ad  # noqa: F401
from decoct.passes import deviation_summary as _ds  # noqa: F401
from decoct.passes import drop_fields as _df  # noqa: F401
from decoct.passes import emit_classes as _ec  # noqa: F401
from decoct.passes import keep_fields as _kf  # noqa: F401
from decoct.passes import prune_empty as _pe  # noqa: F401

# Import all pass modules so they register with the registry
from decoct.passes import strip_comments as _sc  # noqa: F401
from decoct.passes import strip_conformant as _sco  # noqa: F401
from decoct.passes import strip_defaults as _sd  # noqa: F401
from decoct.passes import strip_secrets as _ss  # noqa: F401


def _load_yaml_input(source: str | None) -> tuple[Any, str]:
    """Load YAML or JSON from a file path or stdin.

    Returns (document, raw_text) tuple. JSON files are auto-detected
    by extension and converted to CommentedMap for pipeline compatibility.
    """
    if source is None or source == "-":
        yaml = YAML(typ="rt")
        raw = sys.stdin.read()
        doc = yaml.load(raw)
        return doc, raw

    from decoct.formats import load_input

    return load_input(Path(source))


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
    from decoct.passes.emit_classes import EmitClassesPass
    from decoct.passes.prune_empty import PruneEmptyPass
    from decoct.passes.strip_comments import StripCommentsPass
    from decoct.passes.strip_conformant import StripConformantPass
    from decoct.passes.strip_defaults import StripDefaultsPass
    from decoct.passes.strip_secrets import StripSecretsPass
    from decoct.profiles.loader import load_profile
    from decoct.profiles.resolver import resolve_profile
    from decoct.schemas.loader import load_schema
    from decoct.schemas.resolver import resolve_schema

    schema = None
    assertions: list[Any] = []
    passes: list[Any] = []

    if profile_path:
        resolved_profile = resolve_profile(profile_path)
        profile = load_profile(resolved_profile)
        profile_dir = resolved_profile.parent

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
            elif pass_cls == EmitClassesPass and schema:
                passes.append(EmitClassesPass(schema=schema, **config))
            elif pass_cls in (StripConformantPass, AnnotateDeviationsPass, DeviationSummaryPass):
                passes.append(pass_cls(assertions=assertions, **config))
            else:
                passes.append(pass_cls(**config))
    else:
        # Default pipeline: all passes in order
        passes.append(StripSecretsPass())
        passes.append(StripCommentsPass())

        if schema_path:
            schema = load_schema(resolve_schema(schema_path))
            passes.append(StripDefaultsPass(schema=schema))
            passes.append(EmitClassesPass(schema=schema))

        if assertions_path:
            assertions = load_assertions(assertions_path)

        if assertions:
            passes.append(StripConformantPass(assertions=assertions))
            passes.append(AnnotateDeviationsPass(assertions=assertions))
            passes.append(DeviationSummaryPass(assertions=assertions))

        # Always prune empty containers left by other passes
        passes.append(PruneEmptyPass())

    return passes, schema, assertions


@click.group()
@click.version_option(version=__version__, prog_name="decoct")
def cli() -> None:
    """decoct — infrastructure context compression for LLMs."""


def _auto_detect_schema(doc: Any) -> str | None:
    """Auto-detect platform and return bundled schema name, or None."""
    from decoct.formats import detect_platform

    return detect_platform(doc)


_INPUT_EXTENSIONS = {".yaml", ".yml", ".json", ".ini", ".conf", ".cfg", ".cnf", ".properties"}


def _expand_sources(files: tuple[str, ...], recursive: bool) -> list[str | None]:
    """Expand file arguments, resolving directories to matching files."""
    if not files:
        return [None]

    sources: list[str | None] = []
    for f in files:
        p = Path(f)
        if p.is_dir():
            pattern = "**/*" if recursive else "*"
            for child in sorted(p.glob(pattern)):
                if child.is_file() and child.suffix.lower() in _INPUT_EXTENSIONS:
                    sources.append(str(child))
        else:
            sources.append(f)
    return sources


@cli.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--schema", "schema_path", type=str, help="Schema file path or bundled name (e.g. 'docker-compose').")
@click.option("--assertions", "assertions_path", type=click.Path(exists=True), help="Assertions file.")
@click.option("--profile", "profile_path", type=str, help="Profile file path or bundled name (e.g. 'docker-compose').")
@click.option("--stats", is_flag=True, help="Show token statistics.")
@click.option("--stats-only", is_flag=True, help="Show only token statistics.")
@click.option("--show-removed", is_flag=True, help="Show what was stripped.")
@click.option("--output", "-o", type=click.Path(), help="Output file.")
@click.option("--recursive", "-r", is_flag=True, help="Recurse into subdirectories.")
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
    recursive: bool,
    encoding: str,
) -> None:
    """Compress infrastructure data for LLM context windows."""
    from decoct.pipeline import Pipeline
    from decoct.tokens import create_report, format_report

    # Determine input sources — expand directories
    sources = _expand_sources(files, recursive)

    if not sources:
        click.echo("No matching files found.", err=True)
        sys.exit(1)

    # If schema/profile/assertions explicitly given, build pipeline once
    explicit_config = schema_path or assertions_path or profile_path
    fixed_pipeline = None
    if explicit_config:
        try:
            pass_instances, _schema, _assertions = _build_passes(schema_path, assertions_path, profile_path)
        except (ValueError, KeyError, FileNotFoundError) as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        if not pass_instances:
            click.echo("No passes configured.", err=True)
            sys.exit(1)
        fixed_pipeline = Pipeline(pass_instances)

    total_input_tokens = 0
    total_output_tokens = 0

    for source in sources:
        try:
            doc, input_text = _load_yaml_input(source)
        except Exception as e:  # noqa: BLE001
            click.echo(f"Error reading input: {e}", err=True)
            sys.exit(1)

        # Use fixed pipeline or auto-detect platform
        if fixed_pipeline:
            pipeline = fixed_pipeline
        else:
            auto_schema = _auto_detect_schema(doc)
            try:
                pass_instances, _, _ = _build_passes(auto_schema, None, None)
            except (ValueError, KeyError, FileNotFoundError):
                pass_instances, _, _ = _build_passes(None, None, None)
            pipeline = Pipeline(pass_instances)

        pipeline_stats = pipeline.run(doc)
        output_text = _dump_yaml(doc)

        # Output compressed YAML
        if not stats_only:
            if output:
                Path(output).write_text(output_text)
            else:
                if len(sources) > 1 and source is not None:
                    click.echo(f"# --- {source} ---", nl=True)
                click.echo(output_text, nl=False)

        # Show what was removed
        if show_removed:
            if source is not None:
                click.echo(f"=== {source} ===", err=True)
            for result in pipeline_stats.pass_results:
                if result.items_removed > 0 or result.details:
                    click.echo(f"--- {result.name} ---", err=True)
                    if result.items_removed > 0:
                        click.echo(f"  Removed: {result.items_removed} items", err=True)
                    for detail in result.details:
                        click.echo(f"  {detail}", err=True)

        # Accumulate stats
        if stats or stats_only:
            report = create_report(input_text, output_text, encoding)
            total_input_tokens += report.input_tokens
            total_output_tokens += report.output_tokens
            if len(sources) > 1 and source is not None:
                click.echo(f"{source}: {format_report(report)}", err=True)
            else:
                click.echo(format_report(report), err=True)

    # Aggregate stats for multi-file runs
    if (stats or stats_only) and len(sources) > 1:
        saved = total_input_tokens - total_output_tokens
        pct = (saved / total_input_tokens * 100) if total_input_tokens else 0
        click.echo(f"Total: Tokens: {total_input_tokens} → {total_output_tokens} (saved {saved}, {pct:.1f}%)", err=True)


@cli.group()
def assertion() -> None:
    """Assertion management commands."""


@assertion.command("learn")
@click.option("--standard", "-s", "standards", multiple=True, type=click.Path(exists=True), help="Standards docs.")
@click.option("--example", "-e", "examples", multiple=True, type=click.Path(exists=True), help="Example config files.")
@click.option(
    "--corpus", "-c", "corpus_files", multiple=True, type=click.Path(exists=True),
    help="Config files for cross-file pattern analysis.",
)
@click.option("--platform", "-p", type=str, help="Platform name hint (e.g. 'docker-compose', 'kubernetes').")
@click.option("--output", "-o", type=click.Path(), help="Output assertions file path.")
@click.option("--merge", "-m", type=click.Path(exists=True), help="Merge into existing assertions file.")
@click.option("--model", default="claude-sonnet-4-20250514", show_default=True, help="Anthropic model to use.")
def assertion_learn(
    standards: tuple[str, ...],
    examples: tuple[str, ...],
    corpus_files: tuple[str, ...],
    platform: str | None,
    output: str | None,
    merge: str | None,
    model: str,
) -> None:
    """Derive assertions from standards docs, examples, or corpus using Claude.

    Requires the anthropic SDK: pip install decoct[llm]
    """
    from decoct.learn import learn_assertions, merge_assertions

    if corpus_files and examples:
        click.echo("Error: --corpus and --example are mutually exclusive.", err=True)
        sys.exit(1)

    if not standards and not examples and not corpus_files:
        click.echo("Error: at least one --standard, --example, or --corpus file is required.", err=True)
        sys.exit(1)

    standard_paths = [Path(s) for s in standards] if standards else None
    example_paths = [Path(e) for e in examples] if examples else None
    corpus_paths = [Path(c) for c in corpus_files] if corpus_files else None

    try:
        if corpus_files:
            click.echo(f"Analysing {len(corpus_files)} corpus files for cross-file patterns...", err=True)
        else:
            click.echo("Analysing input files...", err=True)
        assertions_yaml = learn_assertions(
            standards=standard_paths,
            examples=example_paths,
            corpus=corpus_paths,
            platform=platform,
            model=model,
        )
    except ImportError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        click.echo(f"Error generating assertions: {e}", err=True)
        sys.exit(1)

    if merge:
        try:
            assertions_yaml = merge_assertions(Path(merge), assertions_yaml)
            click.echo(f"Merged into {merge}", err=True)
        except Exception as e:  # noqa: BLE001
            click.echo(f"Error merging: {e}", err=True)
            sys.exit(1)

    if output:
        Path(output).write_text(assertions_yaml + "\n")
        click.echo(f"Assertions written to {output}", err=True)
    else:
        click.echo(assertions_yaml)


@cli.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--assertions", "assertions_path", type=click.Path(exists=True), help="Assertions file for full tier.")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown", show_default=True)
@click.option("--output", "-o", type=click.Path(), help="Output file.")
@click.option("--recursive", "-r", is_flag=True, help="Recurse into subdirectories.")
@click.option("--verbose", "-v", is_flag=True, help="Show per-pass timing details.")
@click.option("--encoding", default="cl100k_base", show_default=True, help="Tiktoken encoding for token counting.")
def benchmark(
    files: tuple[str, ...],
    assertions_path: str | None,
    fmt: str,
    output: str | None,
    recursive: bool,
    verbose: bool,
    encoding: str,
) -> None:
    """Benchmark compression performance across a corpus of config files.

    Runs the pipeline at three tiers (generic, schema, full) and reports
    per-file and aggregate token savings.
    """
    from decoct.benchmark import format_report_json, format_report_markdown, run_benchmark

    if not files:
        click.echo("Error: at least one file or directory is required.", err=True)
        sys.exit(1)

    report = run_benchmark(
        list(files),
        assertions_path=assertions_path,
        encoding=encoding,
        recursive=recursive,
    )

    if not report.files:
        click.echo("No files processed.", err=True)
        sys.exit(1)

    if fmt == "json":
        result = format_report_json(report)
    else:
        result = format_report_markdown(report, verbose=verbose)

    if output:
        Path(output).write_text(result + "\n")
        click.echo(f"Report written to {output}", err=True)
    else:
        click.echo(result)


@cli.group()
def schema() -> None:
    """Schema management commands."""


@cli.group(name="entity-graph")
def entity_graph() -> None:
    """Entity-graph pipeline commands."""


@entity_graph.command()
@click.option("--input-dir", "-i", required=True, type=click.Path(exists=True), help="Raw input config dir.")
@click.option("--output-dir", "-o", required=True, type=click.Path(exists=True), help="Entity-graph output dir.")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown", show_default=True)
@click.option("--output", type=click.Path(), help="Write report to file.")
@click.option("--encoding", default="cl100k_base", show_default=True, help="Tiktoken encoding for token counting.")
def stats(
    input_dir: str,
    output_dir: str,
    fmt: str,
    output: str | None,
    encoding: str,
) -> None:
    """Report entity-graph compression statistics."""
    from decoct.entity_graph_stats import compute_stats, format_stats_json, format_stats_markdown

    report = compute_stats(Path(input_dir), Path(output_dir), encoding=encoding)

    if fmt == "json":
        result = format_stats_json(report)
    else:
        result = format_stats_markdown(report)

    if output:
        Path(output).write_text(result + "\n")
        click.echo(f"Report written to {output}", err=True)
    else:
        click.echo(result)


@entity_graph.command(name="generate-questions")
@click.option("--config-dir", "-c", required=True, type=click.Path(exists=True), help="Directory of raw config files.")
@click.option("--output", "-o", required=True, type=click.Path(), help="Output JSON path for question bank.")
@click.option("--max-questions", default=200, show_default=True, help="Maximum questions to generate.")
@click.option("--seed", default=42, show_default=True, help="Random seed for reproducibility.")
@click.option(
    "--adapter", "adapter_name", type=click.Choice(["iosxr", "hybrid-infra"]),
    default="iosxr", show_default=True, help="Adapter for parsing config files.",
)
def generate_questions(
    config_dir: str,
    output: str,
    max_questions: int,
    seed: int,
    adapter_name: str,
) -> None:
    """Generate ground-truth Q&A pairs from raw configs."""
    from decoct.qa.questions import generate_question_bank, save_question_bank

    adapter_instance = None
    if adapter_name == "hybrid-infra":
        from decoct.adapters.hybrid_infra import HybridInfraAdapter
        adapter_instance = HybridInfraAdapter()

    bank = generate_question_bank(
        Path(config_dir),
        max_questions=max_questions,
        seed=seed,
        adapter=adapter_instance,
    )
    save_question_bank(bank, Path(output))
    click.echo(
        f"Generated {len(bank.pairs)} questions from {bank.entity_count} entities "
        f"({bank.type_count} types). Written to {output}",
        err=True,
    )


@entity_graph.command(name="evaluate")
@click.option("--questions", "-q", required=True, type=click.Path(exists=True), help="Question bank JSON file.")
@click.option("--config-dir", "-c", type=click.Path(exists=True), help="Directory of raw configs (for raw condition).")
@click.option("--output-dir", type=click.Path(exists=True), help="Entity-graph output dir (for compressed condition).")
@click.option("--manual", type=click.Path(exists=True), help="Reader manual .md file to prepend to compressed context.")
@click.option(
    "--condition", type=click.Choice(["raw", "compressed", "both"]), default="both", show_default=True,
    help="Which conditions to evaluate.",
)
@click.option("--model", default="claude-sonnet-4-20250514", show_default=True, help="Anthropic model to use.")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown", show_default=True)
@click.option("--output", "-o", type=click.Path(), help="Write report to file.")
@click.option("--encoding", default="cl100k_base", show_default=True, help="Tiktoken encoding for token counting.")
def evaluate(
    questions: str,
    config_dir: str | None,
    output_dir: str | None,
    manual: str | None,
    condition: str,
    model: str,
    fmt: str,
    output: str | None,
    encoding: str,
) -> None:
    """Evaluate LLM comprehension on raw vs compressed representations.

    Requires the anthropic SDK: pip install decoct[llm]
    """
    from decoct.qa.evaluate import (
        EvaluationReport,
        build_compressed_context,
        build_raw_context,
        evaluate_questions,
        format_evaluation_json,
        format_evaluation_markdown,
    )
    from decoct.qa.questions import load_question_bank

    bank = load_question_bank(Path(questions))
    report = EvaluationReport(
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
        question_count=len(bank.pairs),
    )

    conditions = []
    if condition in ("raw", "both"):
        if not config_dir:
            click.echo("Error: --config-dir required for raw condition.", err=True)
            sys.exit(1)
        conditions.append("raw")
    if condition in ("compressed", "both"):
        if not output_dir:
            click.echo("Error: --output-dir required for compressed condition.", err=True)
            sys.exit(1)
        conditions.append("compressed")

    for cond in conditions:
        click.echo(f"Evaluating {cond} condition...", err=True)
        if cond == "raw":
            context = build_raw_context(Path(config_dir))  # type: ignore[arg-type]
        else:
            manual_path = Path(manual) if manual else None
            context = build_compressed_context(Path(output_dir), manual_path)  # type: ignore[arg-type]

        run = evaluate_questions(
            context, bank, condition=cond, model=model, encoding=encoding,
        )
        report.runs.append(run)
        click.echo(f"  {cond}: {run.accuracy:.1%} accuracy ({len(run.results)} questions)", err=True)

    if fmt == "json":
        result = format_evaluation_json(report)
    else:
        result = format_evaluation_markdown(report)

    if output:
        Path(output).write_text(result + "\n")
        click.echo(f"Report written to {output}", err=True)
    else:
        click.echo(result)


@entity_graph.command(name="infer-spec")
@click.option("--input-dir", "-i", required=True, type=click.Path(exists=True),
              help="Directory of raw config files.")
@click.option("--adapter", "adapter_name",
              type=click.Choice(["hybrid-infra", "entra-intune"]),
              default="hybrid-infra", show_default=True)
@click.option("--model", default="google/gemini-2.5-flash-lite", show_default=True,
              help="LLM model name (as expected by provider).")
@click.option("--base-url", default="https://openrouter.ai/api/v1", show_default=True,
              help="OpenAI-compatible API base URL.")
@click.option("--api-key-env", default="OPENROUTER_API_KEY", show_default=True,
              help="Environment variable holding the API key.")
@click.option("--output", "-o", type=click.Path(), help="Write spec to file (default: stdout).")
def infer_spec(
    input_dir: str,
    adapter_name: str,
    model: str,
    base_url: str,
    api_key_env: str,
    output: str | None,
) -> None:
    """Infer ingestion spec by identifying unknown platform types with an LLM.

    Requires: pip install decoct[llm]
    """
    from decoct.learn_ingestion import dump_ingestion_spec, infer_ingestion_spec

    try:
        spec = infer_ingestion_spec(
            input_dir=Path(input_dir),
            adapter_name=adapter_name,
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
            on_progress=lambda msg: click.echo(msg, err=True),
        )
    except ImportError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        click.echo(f"Error inferring spec: {e}", err=True)
        sys.exit(1)

    spec_yaml = dump_ingestion_spec(spec)

    if output:
        Path(output).write_text(spec_yaml)
        click.echo(f"Spec written to {output}", err=True)
    else:
        click.echo(spec_yaml, nl=False)


@schema.command()
@click.option("--example", "-e", "examples", multiple=True, type=click.Path(exists=True), help="Example config files.")
@click.option("--doc", "-d", "docs", multiple=True, type=click.Path(exists=True), help="Documentation files.")
@click.option("--platform", "-p", type=str, help="Platform name hint (e.g. 'nginx', 'haproxy').")
@click.option("--output", "-o", type=click.Path(), help="Output schema file path.")
@click.option("--merge", "-m", type=click.Path(exists=True), help="Merge into existing schema file.")
@click.option("--model", default="claude-sonnet-4-20250514", show_default=True, help="Anthropic model to use.")
def learn(
    examples: tuple[str, ...],
    docs: tuple[str, ...],
    platform: str | None,
    output: str | None,
    merge: str | None,
    model: str,
) -> None:
    """Derive a schema from example configs and/or documentation using Claude.

    Requires the anthropic SDK: pip install decoct[llm]
    """
    from decoct.learn import learn_schema, merge_schemas

    if not examples and not docs:
        click.echo("Error: at least one --example or --doc file is required.", err=True)
        sys.exit(1)

    example_paths = [Path(e) for e in examples] if examples else None
    doc_paths = [Path(d) for d in docs] if docs else None

    try:
        click.echo("Analysing input files...", err=True)
        schema_yaml = learn_schema(
            examples=example_paths,
            docs=doc_paths,
            platform=platform,
            model=model,
        )
    except ImportError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        click.echo(f"Error generating schema: {e}", err=True)
        sys.exit(1)

    if merge:
        try:
            schema_yaml = merge_schemas(Path(merge), schema_yaml)
            click.echo(f"Merged into {merge}", err=True)
        except Exception as e:  # noqa: BLE001
            click.echo(f"Error merging: {e}", err=True)
            sys.exit(1)

    if output:
        Path(output).write_text(schema_yaml + "\n")
        click.echo(f"Schema written to {output}", err=True)
    else:
        click.echo(schema_yaml)
