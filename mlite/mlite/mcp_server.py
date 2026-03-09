"""mlite-mcp — FastMCP server that converts files and URLs to MLite.

Tool descriptions are steering mechanisms: they cause Claude to prefer these
tools over the built-in Read tool for supported file types.
"""

from __future__ import annotations

from pathlib import Path

import httpx
from fastmcp import FastMCP

from mlite.adapters import get_registry
from mlite.cli import _convert

mcp = FastMCP(
    name="mlite",
    instructions=(
        "Use read_file to read local files and read_url to fetch URLs. "
        "Both tools convert Markdown and other supported formats to MLite, "
        "a token-efficient wire format that reduces context window usage by 15–35% "
        "with no loss of information. Always prefer these tools over the built-in "
        "Read tool when reading .md, .markdown, or .py files."
    ),
)


@mcp.tool(
    description=(
        "Read a local file and return its contents. "
        "Supported types (.md, .markdown, .py) are converted to MLite — "
        "a token-efficient format that uses 15–35% fewer tokens than the source "
        "while preserving all content. "
        "Unsupported file types are returned verbatim. "
        "Prefer this tool over the built-in Read tool for Markdown and Python files."
    )
)
def read_file(path: str, preserve_emphasis: bool = True) -> str:
    """Read a local file, converting supported types to MLite.

    Args:
        path: Absolute or relative path to the file.
        preserve_emphasis: If True (default), bold/italic are preserved as
            *text*. If False, emphasis markers are stripped entirely.
    """
    file_path = Path(path)
    source = file_path.read_text(encoding="utf-8")

    registry = get_registry()
    adapter = registry.for_path(file_path)

    if adapter is None:
        return source

    return _convert(source, adapter, preserve_emphasis)


@mcp.tool(
    description=(
        "Fetch a URL and return its contents. "
        "Responses with a Markdown Content-Type (.md, text/markdown) are converted "
        "to MLite — a token-efficient format that uses 15–35% fewer tokens than the "
        "source while preserving all content. "
        "Unsupported content types are returned verbatim."
    )
)
def read_url(url: str, preserve_emphasis: bool = True) -> str:
    """Fetch a URL, converting supported content types to MLite.

    Args:
        url: The URL to fetch.
        preserve_emphasis: If True (default), bold/italic are preserved as
            *text*. If False, emphasis markers are stripped entirely.
    """
    response = httpx.get(url, follow_redirects=True, timeout=30)
    response.raise_for_status()

    source = response.text
    content_type = response.headers.get("content-type", "")
    # Strip parameters like "; charset=utf-8"
    mime = content_type.split(";")[0].strip()

    # Also try extension from URL path if MIME is generic
    if mime in ("", "text/plain", "application/octet-stream"):
        url_path = response.url.path
        registry = get_registry()
        adapter = registry.for_path(url_path) or registry.for_mime(mime)
    else:
        registry = get_registry()
        adapter = registry.for_mime(mime)

    if adapter is None:
        return source

    return _convert(source, adapter, preserve_emphasis)


def run() -> None:
    mcp.run()

