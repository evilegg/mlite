"""mlite CLI — convert files to MLite format.

Thin click wrapper around the adapter layer. No business logic here.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import click

from mlite.adapters import get_registry


def _count_tokens(text: str) -> int | None:
    """Return token count using tiktoken, or None if not installed."""
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        return None


def _convert(source: str, adapter, preserve_emphasis: bool) -> str:
    """Call adapter.to_mlite, passing preserve_emphasis only if accepted."""
    sig = inspect.signature(adapter.to_mlite)
    if "preserve_emphasis" in sig.parameters:
        return adapter.to_mlite(source, preserve_emphasis=preserve_emphasis)
    return adapter.to_mlite(source)


@click.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--stats",
    is_flag=True,
    help="Print token savings to stderr (requires tiktoken).",
)
@click.option(
    "--preserve-emphasis/--no-preserve-emphasis",
    "preserve_emphasis",
    default=True,
    show_default=True,
    help="Preserve bold/italic as *text* (default). Strip with --no-preserve-emphasis.",
)
@click.option(
    "--from",
    "from_mime",
    default=None,
    metavar="MIME",
    help="Override adapter selection by MIME type (e.g. text/markdown).",
)
def main(file: str, stats: bool, preserve_emphasis: bool, from_mime: str | None) -> None:
    """Convert FILE to MLite and write to stdout.

    Unsupported file types are passed through verbatim.
    """
    path = Path(file)
    source = path.read_text(encoding="utf-8")

    registry = get_registry()
    adapter = registry.for_mime(from_mime) if from_mime else registry.for_path(path)

    if adapter is None:
        # Unsupported type — pass through verbatim
        click.echo(source, nl=False)
        return

    output = _convert(source, adapter, preserve_emphasis)
    click.echo(output, nl=False)

    if stats:
        src_tokens = _count_tokens(source)
        out_tokens = _count_tokens(output)
        if src_tokens is None or out_tokens is None:
            click.echo(
                "stats: tiktoken not installed — run: uv pip install tiktoken",
                err=True,
            )
        else:
            delta = out_tokens - src_tokens
            pct = delta / src_tokens * 100
            click.echo(
                f"tokens: {src_tokens} → {out_tokens}  ({pct:+.1f}%)  [cl100k_base]",
                err=True,
            )
