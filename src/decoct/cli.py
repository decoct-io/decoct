"""decoct CLI."""

import sys

import click

from decoct import __version__


@click.group()
@click.version_option(version=__version__, prog_name="decoct")
def cli() -> None:
    """decoct — infrastructure context compression for LLMs."""


@cli.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--schema", type=click.Path(exists=True), help="Schema file.")
@click.option("--assertions", type=click.Path(exists=True), help="Assertions file.")
@click.option("--profile", type=click.Path(exists=True), help="Profile file.")
@click.option("--stats", is_flag=True, help="Show token statistics.")
@click.option("--stats-only", is_flag=True, help="Show only token statistics.")
@click.option("--show-removed", is_flag=True, help="Show what was stripped.")
@click.option("--output", "-o", type=click.Path(), help="Output file.")
@click.option("--encoding", default="cl100k_base", show_default=True, help="Tiktoken encoding for token counting.")
def compress(
    files: tuple[str, ...],
    schema: str | None,
    assertions: str | None,
    profile: str | None,
    stats: bool,
    stats_only: bool,
    show_removed: bool,
    output: str | None,
    encoding: str,
) -> None:
    """Compress infrastructure data for LLM context windows."""
    click.echo("decoct compress: not yet implemented", err=True)
    sys.exit(1)
