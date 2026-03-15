"""decoct CLI — infrastructure config compression."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import click
from ruamel.yaml import YAML

from decoct import __version__


@click.group()
@click.version_option(version=__version__, prog_name="decoct")
def cli() -> None:
    """decoct -- infrastructure context compression for LLMs."""


@cli.command()
@click.option("--input-dir", "-i", required=True, type=click.Path(exists=True), help="Input config directory.")
@click.option("--output-dir", "-o", required=True, type=click.Path(), help="Output directory.")
@click.option("--no-secrets", is_flag=True, help="Disable secrets masking.")
@click.option("--no-validate", is_flag=True, help="Skip reconstruction validation.")
@click.option("--no-dissolve", is_flag=True, help="Skip dissolving unprofitable classes.")
@click.option("--threshold", default=100.0, show_default=True, type=float,
              help="Majority-vote threshold (0-100). Fields shared by >= T%% of hosts enter the class.")
@click.option("--max-delta-pct", default=20.0, show_default=True, type=float,
              help="Max delta %% for nearest-class assignment (0-100).")
@click.option("--min-group-size", default=3, show_default=True, type=int,
              help="Minimum group size for class extraction.")
@click.option("--stats", "show_stats", is_flag=True, help="Print compression statistics after output.")
@click.option("--encoding", default="cl100k_base", show_default=True, help="Tiktoken encoding for token counting.")
@click.option("--workers", default=None, type=int,
              help="Worker processes for parallel compression (default: min(cpu_count, 8)).")
def compress(
    input_dir: str, output_dir: str, no_secrets: bool, no_validate: bool,
    no_dissolve: bool, threshold: float, max_delta_pct: float,
    min_group_size: int, show_stats: bool, encoding: str,
    workers: int | None,
) -> None:
    """Compress a fleet of config files into classes + per-host deltas."""
    from decoct.pipeline import PipelineConfig, run_pipeline, write_output

    if workers is None:
        workers = min(os.cpu_count() or 1, 8)

    config = PipelineConfig(
        secrets=not no_secrets,
        validate=not no_validate,
        dissolve=not no_dissolve,
        threshold=threshold,
        max_delta_pct=max_delta_pct,
        min_group_size=min_group_size,
        workers=workers,
    )

    # Set up live TUI if --stats and Rich is available
    display = None
    on_host = None
    on_section = None
    if show_stats:
        try:
            from decoct.tui import CompressionProgress, LiveDisplay

            progress = CompressionProgress(input_path=input_dir)
            display = LiveDisplay(progress)
            on_host = display.update_ingestion
            on_section = lambda name, event: (  # noqa: E731
                display.section_started(name) if event == "start"
                else display.section_done(name)
            )
            display.start()
        except ImportError:
            pass

    click.echo(f"Input: {input_dir}", err=True)
    result = run_pipeline(input_dir, config, on_host=on_host, on_section=on_section)

    if display is not None:
        display.stop()

    if not result.tier_c:
        click.echo("No input files found.", err=True)
        sys.exit(1)

    write_output(result, output_dir)

    click.echo(f"Output: {output_dir}", err=True)
    click.echo(f"  Format: {result.format}", err=True)
    click.echo(f"  Tier B: {len(result.tier_b)} classes", err=True)
    click.echo(f"  Tier C: {len(result.tier_c)} hosts", err=True)

    if config.secrets:
        click.echo(f"  Secrets masked: {len(result.secrets_audit)}", err=True)
    else:
        click.echo("  Secrets masking: disabled", err=True)

    if not no_validate:
        if config.secrets:
            target = "post-masking state"
        else:
            target = "original input"
        if result.validation_ok:
            click.echo(
                f"  Validation: PASS ({len(result.tier_c)}/{len(result.tier_c)} hosts,"
                f" reconstructed to {target})",
                err=True,
            )
        else:
            click.echo(
                f"  Validation: FAIL ({len(result.validation_errors)} errors,"
                f" reconstructed to {target})",
                err=True,
            )
            for err in result.validation_errors[:10]:
                click.echo(f"    - {err}", err=True)
            sys.exit(1)

    if result.class_profitability:
        dissolved_count = sum(1 for p in result.class_profitability if p.dissolved)
        if dissolved_count:
            click.echo(f"  Dissolved: {dissolved_count} unprofitable classes", err=True)

    if show_stats:
        from decoct.stats import compute_stats, format_stats_markdown

        report = compute_stats(Path(input_dir), Path(output_dir), encoding=encoding)
        click.echo("")
        click.echo(format_stats_markdown(report))


@cli.command()
@click.option("--input-dir", "-i", required=True, type=click.Path(exists=True), help="Raw input config dir.")
@click.option("--output-dir", "-o", required=True, type=click.Path(exists=True), help="Compressed output dir.")
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
    """Report compression statistics."""
    from decoct.stats import compute_stats, format_stats_json, format_stats_markdown

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


@cli.command()
@click.option("--output-dir", "-o", required=True, type=click.Path(exists=True),
              help="Output directory to serve.")
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind host.")
@click.option("--port", default=8000, show_default=True, help="Bind port.")
@click.option("--reload", "use_reload", is_flag=True, help="Enable auto-reload for development.")
def serve(output_dir: str, host: str, port: int, use_reload: bool) -> None:
    """Start the Progressive Disclosure API server."""
    import uvicorn

    from decoct.api.app import create_app

    app = create_app(output_dir)
    uvicorn.run(app, host=host, port=port, reload=use_reload)


@cli.command(name="generate-questions")
@click.option("--config-dir", "-c", required=True, type=click.Path(exists=True), help="Directory of raw config files.")
@click.option("--output", "-o", required=True, type=click.Path(), help="Output JSON path for question bank.")
@click.option("--max-questions", default=200, show_default=True, help="Maximum questions to generate.")
@click.option("--seed", default=42, show_default=True, help="Random seed for reproducibility.")
def generate_questions(
    config_dir: str,
    output: str,
    max_questions: int,
    seed: int,
) -> None:
    """Generate ground-truth Q&A pairs from raw configs."""
    from decoct.qa.questions import generate_question_bank, save_question_bank

    bank = generate_question_bank(
        Path(config_dir),
        max_questions=max_questions,
        seed=seed,
    )
    save_question_bank(bank, Path(output))
    click.echo(
        f"Generated {len(bank.pairs)} questions from {bank.entity_count} entities "
        f"({bank.type_count} types). Written to {output}",
        err=True,
    )


@cli.command(name="evaluate")
@click.option("--questions", "-q", required=True, type=click.Path(exists=True), help="Question bank JSON file.")
@click.option("--config-dir", "-c", type=click.Path(exists=True), help="Directory of raw configs (for raw condition).")
@click.option("--output-dir", type=click.Path(exists=True), help="Compressed output dir (for compressed condition).")
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


@cli.command(name="infer-spec")
@click.option("--input-dir", "-i", required=True, type=click.Path(exists=True),
              help="Directory of raw config files.")
@click.option("--model", default="google/gemini-2.5-flash-lite", show_default=True,
              help="LLM model name (as expected by provider).")
@click.option("--base-url", default="https://openrouter.ai/api/v1", show_default=True,
              help="OpenAI-compatible API base URL.")
@click.option("--api-key-env", default="OPENROUTER_API_KEY", show_default=True,
              help="Environment variable holding the API key.")
@click.option("--output", "-o", type=click.Path(), help="Write spec to file (default: stdout).")
def infer_spec(
    input_dir: str,
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


@cli.command(name="project")
@click.option("--output-dir", "-o", required=True, type=click.Path(exists=True),
              help="Compressed output directory.")
@click.option("--spec", "-s", required=True, type=click.Path(exists=True),
              help="Projection spec YAML file.")
@click.option("--type", "type_id", type=str, help="Entity type to project (default: from spec source_type).")
@click.option("--subjects", type=str, help="Comma-separated subject names to project (default: all).")
def project(
    output_dir: str,
    spec: str,
    type_id: str | None,
    subjects: str | None,
) -> None:
    """Generate subject projections from Tier B/C output."""
    from decoct.projections.generator import generate_projection, validate_projection
    from decoct.projections.spec_loader import load_projection_spec

    try:
        proj_spec = load_projection_spec(spec)
    except (ValueError, FileNotFoundError) as e:
        click.echo(f"Error loading spec: {e}", err=True)
        sys.exit(1)

    effective_type = type_id or proj_spec.source_type
    out_path = Path(output_dir)

    # Load Tier B and C
    classes_file = out_path / f"{effective_type}_classes.yaml"
    instances_file = out_path / f"{effective_type}_instances.yaml"

    if not classes_file.exists():
        click.echo(f"Error: Tier B file not found: {classes_file}", err=True)
        sys.exit(1)
    if not instances_file.exists():
        click.echo(f"Error: Tier C file not found: {instances_file}", err=True)
        sys.exit(1)

    yaml = YAML(typ="safe")
    tier_b = yaml.load(classes_file.read_text())
    tier_c = yaml.load(instances_file.read_text())

    # Filter subjects if requested
    subject_filter = set(subjects.split(",")) if subjects else None
    selected = [
        s for s in proj_spec.subjects
        if subject_filter is None or s.name in subject_filter
    ]

    if not selected:
        click.echo("Error: no matching subjects found.", err=True)
        sys.exit(1)

    # Create output directory
    proj_dir = out_path / "projections" / effective_type
    proj_dir.mkdir(parents=True, exist_ok=True)

    rt_yaml = YAML(typ="rt")
    rt_yaml.default_flow_style = False

    for subj in selected:
        click.echo(f"Projecting {subj.name}...", err=True)
        projected = generate_projection(tier_b, tier_c, subj)

        errors = validate_projection(projected, tier_b, tier_c)
        if errors:
            click.echo(f"  Validation warnings for {subj.name}:", err=True)
            for err in errors:
                click.echo(f"    - {err}", err=True)

        out_file = proj_dir / f"{subj.name}.yaml"
        stream = StringIO()
        rt_yaml.dump(projected, stream)
        out_file.write_text(stream.getvalue())
        click.echo(f"  -> {out_file}", err=True)

    click.echo(f"Generated {len(selected)} projections in {proj_dir}", err=True)


@cli.command(name="infer-projections")
@click.option("--output-dir", "-o", required=True, type=click.Path(exists=True),
              help="Compressed output directory.")
@click.option("--type", "type_id", required=True, type=str,
              help="Entity type to infer projections for.")
@click.option("--model", default="google/gemini-2.5-flash", show_default=True,
              help="LLM model name (as expected by provider).")
@click.option("--base-url", default="https://openrouter.ai/api/v1", show_default=True,
              help="OpenAI-compatible API base URL.")
@click.option("--api-key-env", default="OPENROUTER_API_KEY", show_default=True,
              help="Environment variable holding the API key.")
@click.option("--output", type=click.Path(), help="Write spec to file (default: stdout).")
def infer_projections(
    output_dir: str,
    type_id: str,
    model: str,
    base_url: str,
    api_key_env: str,
    output: str | None,
) -> None:
    """Infer projection spec by identifying subjects from Tier B with an LLM.

    Requires: pip install decoct[llm]
    """
    from decoct.learn_projections import infer_projection_spec
    from decoct.projections.spec_loader import dump_projection_spec

    try:
        spec = infer_projection_spec(
            output_dir=Path(output_dir),
            type_id=type_id,
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
            on_progress=lambda msg: click.echo(msg, err=True),
        )
    except ImportError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        click.echo(f"Error inferring projections: {e}", err=True)
        sys.exit(1)

    spec_yaml = dump_projection_spec(spec)

    if output:
        Path(output).write_text(spec_yaml)
        click.echo(f"Spec written to {output}", err=True)
    else:
        click.echo(spec_yaml, nl=False)


@cli.command(name="generate-eval-questions")
@click.option("--config-dir", "-c", required=True, type=click.Path(exists=True),
              help="Directory of raw config files.")
@click.option("--source", "-s", required=True,
              type=click.Choice(["standard", "iosxr", "hybrid-infra", "entra-intune"]),
              help="Source corpus label.")
@click.option("--output", "-o", required=True, type=click.Path(),
              help="Output YAML path for candidate question bank.")
@click.option("--questions-per-class", default=120, show_default=True,
              help="Number of candidate questions per class.")
@click.option("--model", default="google/gemini-2.5-flash", show_default=True,
              help="LLM model name (as expected by provider).")
@click.option("--base-url", default="https://openrouter.ai/api/v1", show_default=True,
              help="OpenAI-compatible API base URL.")
@click.option("--api-key-env", default="OPENROUTER_API_KEY", show_default=True,
              help="Environment variable holding the API key.")
def generate_eval_questions_cmd(
    config_dir: str,
    source: str,
    output: str,
    questions_per_class: int,
    model: str,
    base_url: str,
    api_key_env: str,
) -> None:
    """Generate LLM-based evaluation questions for weighted scoring.

    Requires: pip install decoct[llm]
    """
    from decoct.qa.generate_eval import generate_eval_questions, save_eval_bank

    try:
        bank = generate_eval_questions(
            config_dir=Path(config_dir),
            source=source,
            questions_per_class=questions_per_class,
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
            on_progress=lambda msg: click.echo(msg, err=True),
        )
    except ImportError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        click.echo(f"Error generating questions: {e}", err=True)
        sys.exit(1)

    save_eval_bank(bank, Path(output))
    click.echo(
        f"Generated {len(bank.questions)} candidates ({bank.class_counts}). "
        f"Written to {output}",
        err=True,
    )


@cli.command(name="validate-eval-questions")
@click.option("--questions", "-q", required=True, type=click.Path(exists=True),
              help="Candidate question bank YAML file.")
@click.option("--config-dir", "-c", required=True, type=click.Path(exists=True),
              help="Directory of raw config files.")
@click.option("--output", "-o", required=True, type=click.Path(),
              help="Output YAML path for validated question bank.")
@click.option("--target-per-class", default=100, show_default=True,
              help="Maximum questions to keep per class.")
@click.option("--model", default="google/gemini-2.5-flash", show_default=True,
              help="LLM model name (as expected by provider).")
@click.option("--base-url", default="https://openrouter.ai/api/v1", show_default=True,
              help="OpenAI-compatible API base URL.")
@click.option("--api-key-env", default="OPENROUTER_API_KEY", show_default=True,
              help="Environment variable holding the API key.")
def validate_eval_questions_cmd(
    questions: str,
    config_dir: str,
    output: str,
    target_per_class: int,
    model: str,
    base_url: str,
    api_key_env: str,
) -> None:
    """Validate and prune candidate evaluation questions via LLM.

    Requires: pip install decoct[llm]
    """
    from decoct.qa.generate_eval import load_eval_bank, save_eval_bank, validate_eval_questions

    bank = load_eval_bank(Path(questions))
    click.echo(f"Loaded {len(bank.questions)} candidates ({bank.class_counts})", err=True)

    try:
        validated = validate_eval_questions(
            bank,
            config_dir=Path(config_dir),
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
            target_per_class=target_per_class,
            on_progress=lambda msg: click.echo(msg, err=True),
        )
    except ImportError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        click.echo(f"Error validating questions: {e}", err=True)
        sys.exit(1)

    save_eval_bank(validated, Path(output))
    click.echo(
        f"Validated {len(validated.questions)} questions ({validated.class_counts}). "
        f"Written to {output}",
        err=True,
    )


@cli.command(name="run-eval")
@click.option("--questions", "-q", required=True, type=click.Path(exists=True),
              help="Validated question bank YAML file.")
@click.option("--config-dir", "-c", type=click.Path(exists=True),
              help="Directory of raw configs (for raw condition).")
@click.option("--output-dir", type=click.Path(exists=True),
              help="Compressed output dir (for compressed condition).")
@click.option("--manual", type=click.Path(exists=True),
              help="Reader manual .md file to prepend to compressed context.")
@click.option("--condition", type=click.Choice(["raw", "compressed", "both"]),
              default="both", show_default=True, help="Which conditions to evaluate.")
@click.option("--model-answer", default="google/gemini-2.5-flash", show_default=True,
              help="Model for answering questions.")
@click.option("--model-judge", default="google/gemini-2.5-flash", show_default=True,
              help="Model for judging answers.")
@click.option("--base-url", default="https://openrouter.ai/api/v1", show_default=True,
              help="OpenAI-compatible API base URL.")
@click.option("--api-key-env", default="OPENROUTER_API_KEY", show_default=True,
              help="Environment variable holding the API key.")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]),
              default="markdown", show_default=True)
@click.option("--output", "-o", type=click.Path(), help="Write report to file.")
def run_eval_cmd(
    questions: str,
    config_dir: str | None,
    output_dir: str | None,
    manual: str | None,
    condition: str,
    model_answer: str,
    model_judge: str,
    base_url: str,
    api_key_env: str,
    fmt: str,
    output: str | None,
) -> None:
    """Run weighted evaluation of LLM comprehension on raw vs compressed.

    Requires: pip install decoct[llm]
    """
    from decoct.qa.eval_evaluate import (
        evaluate_eval_questions,
        format_eval_report_json,
        format_eval_report_markdown,
    )
    from decoct.qa.eval_models import EvalEvaluationReport
    from decoct.qa.generate_eval import load_eval_bank

    bank = load_eval_bank(Path(questions))

    report = EvalEvaluationReport(
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
        source=bank.source,
        question_count=len(bank.questions),
    )

    conditions: list[str] = []
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

    manual_path = Path(manual) if manual else None

    for cond in conditions:
        click.echo(f"Evaluating {cond} condition...", err=True)
        try:
            run = evaluate_eval_questions(
                bank,
                config_dir=Path(config_dir) if config_dir else None,
                output_dir=Path(output_dir) if output_dir else None,
                condition=cond,
                model_answer=model_answer,
                model_judge=model_judge,
                base_url=base_url,
                api_key_env=api_key_env,
                manual_path=manual_path,
                on_progress=lambda msg: click.echo(msg, err=True),
            )
            report.runs.append(run)
            pct = run.total_score / run.max_total_score if run.max_total_score else 0
            click.echo(
                f"  {cond}: {run.total_score}/{run.max_total_score} ({pct:.1%})",
                err=True,
            )
        except ImportError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        except Exception as e:  # noqa: BLE001
            click.echo(f"Error evaluating {cond}: {e}", err=True)
            sys.exit(1)

    if fmt == "json":
        result = format_eval_report_json(report)
    else:
        result = format_eval_report_markdown(report)

    if output:
        Path(output).write_text(result + "\n")
        click.echo(f"Report written to {output}", err=True)
    else:
        click.echo(result)


@cli.command(name="section-project")
@click.option("--output-dir", "-o", required=True, type=click.Path(exists=True),
              help="Compressed output directory (with tier_b.yaml + per-host files).")
@click.option("--spec", "-s", required=True, type=click.Path(exists=True),
              help="Section projection spec YAML file (version 2).")
@click.option("--subjects", type=str, help="Comma-separated subject names to project (default: all).")
@click.option("--tier-a/--no-tier-a", default=True, show_default=True,
              help="Generate Tier A orientation file.")
def section_project(
    output_dir: str,
    spec: str,
    subjects: str | None,
    tier_a: bool,
) -> None:
    """Generate section projections from compressed tier_b/tier_c output."""
    from decoct.render import render_yaml
    from decoct.section_projections.generator import (
        generate_content_projection,
        generate_section_projection,
        validate_section_projection,
    )
    from decoct.section_projections.spec_loader import load_section_projection_spec
    from decoct.section_projections.tier_a import generate_tier_a

    try:
        proj_spec = load_section_projection_spec(spec)
    except (ValueError, FileNotFoundError) as e:
        click.echo(f"Error loading spec: {e}", err=True)
        sys.exit(1)

    out_path = Path(output_dir)

    # Load Tier B
    tier_b_file = out_path / "tier_b.yaml"
    if not tier_b_file.exists():
        click.echo(f"Error: tier_b.yaml not found in {out_path}", err=True)
        sys.exit(1)

    yaml = YAML(typ="safe")
    tier_b_data = yaml.load(tier_b_file.read_text())

    # Load all per-host Tier C files
    tier_c_data: dict[str, dict[str, object]] = {}
    for f in sorted(out_path.glob("*.yaml")):
        if f.name == "tier_b.yaml" or f.name == "tier_a.yaml":
            continue
        host_data = yaml.load(f.read_text())
        if isinstance(host_data, dict):
            tier_c_data[f.stem] = host_data

    if not tier_c_data:
        click.echo("Error: no host files found.", err=True)
        sys.exit(1)

    # Filter subjects
    subject_filter = set(subjects.split(",")) if subjects else None
    selected = [
        s for s in proj_spec.subjects
        if subject_filter is None or s.name in subject_filter
    ]
    if not selected:
        click.echo("Error: no matching subjects found.", err=True)
        sys.exit(1)

    # Create projections directory
    proj_dir = out_path / "projections"
    proj_dir.mkdir(parents=True, exist_ok=True)

    projections: dict[str, dict[str, object]] = {}
    for subj in selected:
        click.echo(f"Projecting {subj.name}...", err=True)

        # Choose generator based on subject type
        if subj.content_filters and not subj.section_patterns:
            # Pure customer projection
            projected = generate_content_projection(
                tier_b_data, tier_c_data, subj, proj_spec.identity_sections,
            )
        else:
            # Protocol projection (may also have content_filters)
            projected = generate_section_projection(
                tier_b_data, tier_c_data, subj, proj_spec.identity_sections,
            )
            # Validate refs
            errors = validate_section_projection(projected, tier_b_data, tier_c_data)
            if errors:
                click.echo(f"  Validation warnings for {subj.name}:", err=True)
                for err_msg in errors[:10]:
                    click.echo(f"    - {err_msg}", err=True)

        projections[subj.name] = projected
        out_file = proj_dir / f"{subj.name}.yaml"
        out_file.write_text(render_yaml(projected))
        host_count = projected.get("meta", {}).get("host_count", 0)
        click.echo(f"  -> {out_file} ({host_count} hosts)", err=True)

    # Generate Tier A
    if tier_a:
        tier_a_data = generate_tier_a(
            tier_b_data, tier_c_data, proj_spec, projections, out_path,
        )
        tier_a_file = out_path / "tier_a.yaml"
        tier_a_file.write_text(render_yaml(tier_a_data))
        click.echo(f"Tier A -> {tier_a_file}", err=True)

    click.echo(f"Generated {len(selected)} projections in {proj_dir}", err=True)


@cli.command(name="infer-section-projections")
@click.option("--output-dir", "-o", required=True, type=click.Path(exists=True),
              help="Compressed output directory (with tier_b.yaml + per-host files).")
@click.option("--model", default="google/gemini-2.5-flash", show_default=True,
              help="LLM model name (as expected by provider).")
@click.option("--base-url", default="https://openrouter.ai/api/v1", show_default=True,
              help="OpenAI-compatible API base URL.")
@click.option("--api-key-env", default="OPENROUTER_API_KEY", show_default=True,
              help="Environment variable holding the API key.")
@click.option("--output", type=click.Path(), help="Write spec to file (default: stdout).")
def infer_section_projections(
    output_dir: str,
    model: str,
    base_url: str,
    api_key_env: str,
    output: str | None,
) -> None:
    """Infer section projection spec from compressed output with an LLM.

    Requires: pip install decoct[llm]
    """
    from decoct.learn_section_projections import infer_section_projection_spec
    from decoct.section_projections.spec_loader import dump_section_projection_spec

    try:
        result_spec = infer_section_projection_spec(
            output_dir=Path(output_dir),
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
            on_progress=lambda msg: click.echo(msg, err=True),
        )
    except ImportError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        click.echo(f"Error inferring section projections: {e}", err=True)
        sys.exit(1)

    spec_yaml = dump_section_projection_spec(result_spec)

    if output:
        Path(output).write_text(spec_yaml)
        click.echo(f"Spec written to {output}", err=True)
    else:
        click.echo(spec_yaml, nl=False)


@cli.command()
@click.option("--db", required=True, type=click.Path(), help="Compressed fleet database file.")
@click.option("--hosts", type=str, help="Comma-separated hostnames to include.")
@click.option("--query", "-q", "query_str", type=str, help="Natural language query for host/section selection.")
@click.option("--budget", default=100_000, show_default=True, type=int, help="Token budget for output.")
@click.option("--sections", type=str, help="Comma-separated section names to include.")
@click.option("--prioritise", type=click.Choice(["delta", "alphabetical", "random"]),
              default="delta", show_default=True, help="Host selection strategy.")
@click.option("--no-tier-a", is_flag=True, help="Omit Tier A summary from output.")
@click.option("--output", "-o", type=click.Path(), help="Write payload to file (default: stdout).")
def retrieve(
    db: str,
    hosts: str | None,
    query_str: str | None,
    budget: int,
    sections: str | None,
    prioritise: str,
    no_tier_a: bool,
    output: str | None,
) -> None:
    """Retrieve a token-budgeted context payload from a compressed fleet."""
    from decoct.fleet import CompressedFleet

    fleet = CompressedFleet(db)

    if query_str:
        payload = fleet.retrieve_for_query(query_str, token_budget=budget)
    else:
        host_list = hosts.split(",") if hosts else None
        section_list = sections.split(",") if sections else None
        payload = fleet.retrieve(
            hosts=host_list,
            sections=section_list,
            token_budget=budget,
            include_tier_a=not no_tier_a,
            prioritise=prioritise,
        )

    fleet.close()

    if output:
        Path(output).write_text(payload)
        click.echo(f"Payload written to {output} ({len(payload)} chars)", err=True)
    else:
        click.echo(payload, nl=False)


@cli.command(name="fleet-info")
@click.option("--db", required=True, type=click.Path(exists=True), help="Compressed fleet database file.")
def fleet_info(db: str) -> None:
    """Show fleet statistics from a compressed fleet database."""
    from decoct.fleet import CompressedFleet

    fleet = CompressedFleet(db)

    click.echo(f"Fleet: {db}")
    click.echo(f"  Hosts: {fleet.host_count()}")
    click.echo(f"  Classes: {fleet.class_count()}")
    click.echo(f"  Sections: {len(fleet.sections())}")

    # Zero-delta count
    zero = len([h for h in fleet.hosts() if fleet.host_info(h).is_zero_delta])
    click.echo(f"  Zero-delta hosts: {zero}")

    # Top delta hosts
    top = fleet.hosts_by_delta_size(min_delta=1)[:5]
    if top:
        click.echo("  Top delta hosts:")
        for h in top:
            info = fleet.host_info(h)
            click.echo(f"    {h}: delta={info.total_delta}")

    fleet.close()
