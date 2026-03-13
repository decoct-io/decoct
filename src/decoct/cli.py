"""decoct CLI — infrastructure config compression."""

from __future__ import annotations

from pathlib import Path

import click

from decoct import __version__


@click.group()
@click.version_option(version=__version__, prog_name="decoct")
def cli() -> None:
    """decoct — infrastructure config compression for LLMs."""


@cli.command()
@click.option("-i", "--input-dir", required=True, type=click.Path(exists=True), help="Directory of config files.")
@click.option("-o", "--output-dir", required=True, type=click.Path(), help="Output directory for compressed YAML.")
def compress(input_dir: str, output_dir: str) -> None:
    """Compress a directory of config files."""
    import sys

    from decoct.pipeline import run_pipeline
    from decoct.reconstruct import ReconstructionError
    from decoct.stats import format_stats

    input_path = Path(input_dir)
    sources = sorted(str(f) for f in input_path.iterdir() if f.is_file() and not f.name.startswith("."))

    try:
        result = run_pipeline(sources, output_dir)
    except ReconstructionError as exc:
        click.echo(f"Output: {output_dir}/tier_b.yaml + {output_dir}/tier_c/")
        if exc.stats:
            click.echo(format_stats(exc.stats))
        click.echo(f"ERROR: Round-trip validation failed for: {', '.join(exc.mismatched_hosts)}", err=True)
        sys.exit(1)

    click.echo(f"Compressed {result['entities']} entities into {result['classes']} classes")
    click.echo(f"Output: {output_dir}/tier_b.yaml + {output_dir}/tier_c/")
    click.echo(format_stats(result["stats"]))
