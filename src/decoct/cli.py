"""decoct CLI."""

from __future__ import annotations

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
    """decoct — infrastructure context compression for LLMs."""


@cli.command()
@click.option("--output-dir", "-o", required=True, type=click.Path(exists=True),
              help="Entity-graph output directory to serve.")
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind host.")
@click.option("--port", default=8000, show_default=True, help="Bind port.")
@click.option("--reload", "use_reload", is_flag=True, help="Enable auto-reload for development.")
def serve(output_dir: str, host: str, port: int, use_reload: bool) -> None:
    """Start the Progressive Disclosure API server."""
    import uvicorn

    from decoct.api.app import create_app

    app = create_app(output_dir)
    uvicorn.run(app, host=host, port=port, reload=use_reload)


@cli.group(name="entity-graph")
@click.option("--compression-engine", default="greedy-bundle", show_default=True,
              help="Compression engine to use for class extraction + delta compression.")
@click.pass_context
def entity_graph(ctx: click.Context, compression_engine: str) -> None:
    """Entity-graph pipeline commands."""
    ctx.ensure_object(dict)
    ctx.obj["compression_engine"] = compression_engine


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


@entity_graph.command(name="project")
@click.option("--output-dir", "-o", required=True, type=click.Path(exists=True),
              help="Entity-graph output directory.")
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


@entity_graph.command(name="infer-projections")
@click.option("--output-dir", "-o", required=True, type=click.Path(exists=True),
              help="Entity-graph output directory.")
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


@entity_graph.command(name="review-tier-a")
@click.option("--output-dir", "-o", required=True, type=click.Path(exists=True),
              help="Entity-graph output directory.")
@click.option("--model", default="google/gemini-2.5-flash", show_default=True,
              help="LLM model name (as expected by provider).")
@click.option("--base-url", default="https://openrouter.ai/api/v1", show_default=True,
              help="OpenAI-compatible API base URL.")
@click.option("--api-key-env", default="OPENROUTER_API_KEY", show_default=True,
              help="Environment variable holding the API key.")
@click.option("--output", type=click.Path(), help="Write spec to file (default: stdout).")
def review_tier_a(
    output_dir: str,
    model: str,
    base_url: str,
    api_key_env: str,
    output: str | None,
) -> None:
    """Generate a Tier A spec with corpus description and type summaries using an LLM.

    Requires: pip install decoct[llm]
    """
    from decoct.assembly.tier_a_spec import dump_tier_a_spec
    from decoct.learn_tier_a import infer_tier_a_spec

    try:
        spec = infer_tier_a_spec(
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
        click.echo(f"Error generating Tier A spec: {e}", err=True)
        sys.exit(1)

    spec_yaml = dump_tier_a_spec(spec)

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(spec_yaml)
        click.echo(f"Spec written to {output}", err=True)
    else:
        click.echo(spec_yaml, nl=False)


@entity_graph.command(name="enhance-tier-a")
@click.option("--output-dir", "-o", required=True, type=click.Path(exists=True),
              help="Entity-graph output directory.")
@click.option("--spec", "-s", required=True, type=click.Path(exists=True),
              help="Tier A spec YAML file.")
def enhance_tier_a(
    output_dir: str,
    spec: str,
) -> None:
    """Merge a Tier A spec into tier_a.yaml, adding guide content and projection index."""
    from decoct.assembly.tier_a_spec import load_tier_a_spec
    from decoct.assembly.tier_builder import merge_tier_a_spec

    out_path = Path(output_dir)
    tier_a_file = out_path / "tier_a.yaml"

    if not tier_a_file.exists():
        click.echo(f"Error: Tier A file not found: {tier_a_file}", err=True)
        sys.exit(1)

    try:
        tier_a_spec = load_tier_a_spec(spec)
    except (ValueError, FileNotFoundError) as e:
        click.echo(f"Error loading spec: {e}", err=True)
        sys.exit(1)

    yaml = YAML(typ="safe")
    tier_a = yaml.load(tier_a_file.read_text())

    merged = merge_tier_a_spec(tier_a, tier_a_spec, output_dir=out_path)

    rt_yaml = YAML(typ="rt")
    rt_yaml.default_flow_style = False
    stream = StringIO()
    rt_yaml.dump(merged, stream)
    tier_a_file.write_text(stream.getvalue())

    click.echo(f"Enhanced {tier_a_file}", err=True)


@entity_graph.command(name="generate-eval-questions")
@click.option("--config-dir", "-c", required=True, type=click.Path(exists=True),
              help="Directory of raw config files.")
@click.option("--source", "-s", required=True,
              type=click.Choice(["iosxr", "hybrid-infra", "entra-intune"]),
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

    Generates candidates across 5 question classes (factual, cross-reference,
    operational, compliance, absence). Run validate-eval-questions next.

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


@entity_graph.command(name="validate-eval-questions")
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

    Reads a candidate bank, validates each question against raw configs,
    and prunes to the target count per class.

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


@entity_graph.command(name="run-eval")
@click.option("--questions", "-q", required=True, type=click.Path(exists=True),
              help="Validated question bank YAML file.")
@click.option("--config-dir", "-c", type=click.Path(exists=True),
              help="Directory of raw configs (for raw condition).")
@click.option("--output-dir", type=click.Path(exists=True),
              help="Entity-graph output dir (for compressed condition).")
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

    Uses 5 question classes with weighted scoring rubrics.
    Factual questions are auto-scored; others use LLM-as-judge.

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
