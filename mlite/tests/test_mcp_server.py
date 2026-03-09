"""Tests for the mlite-mcp FastMCP server tools.

Tools are plain Python functions and can be tested directly without
starting the server.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mlite.mcp_server import read_file, read_url, mcp

FIXTURES = Path(__file__).parent / "fixtures"


# ── read_file ─────────────────────────────────────────────────────────────────

def test_read_file_converts_markdown(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("## Hello\n\nWorld.\n")
    result = read_file(str(md))
    assert "== Hello" in result
    assert "World." in result


def test_read_file_passthrough_unsupported(tmp_path):
    txt = tmp_path / "note.txt"
    txt.write_text("plain text\n")
    result = read_file(str(txt))
    assert result == "plain text\n"


def test_read_file_preserve_emphasis_default(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("**bold** and _italic_\n")
    result = read_file(str(md))
    assert "*bold*" in result
    assert "*italic*" in result


def test_read_file_strip_emphasis(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("**bold** and _italic_\n")
    result = read_file(str(md), preserve_emphasis=False)
    assert "**" not in result
    assert "*bold*" not in result
    assert "bold" in result


def test_read_file_golden_basic():
    golden = (FIXTURES / "basic.mlt").read_text()
    result = read_file(str(FIXTURES / "basic.md"))
    assert result == golden


# ── read_url ──────────────────────────────────────────────────────────────────

def _mock_response(text: str, content_type: str, url: str = "https://example.com/doc.md"):
    resp = MagicMock()
    resp.text = text
    resp.headers = {"content-type": content_type}
    resp.url.path = url.split("//", 1)[-1].split("/", 1)[-1]
    resp.raise_for_status = MagicMock()
    return resp


@patch("mlite.mcp_server.httpx.get")
def test_read_url_converts_markdown_mime(mock_get):
    mock_get.return_value = _mock_response(
        "## Title\n\nBody.\n", "text/markdown"
    )
    result = read_url("https://example.com/doc.md")
    assert "== Title" in result
    assert "Body." in result


@patch("mlite.mcp_server.httpx.get")
def test_read_url_converts_by_extension_fallback(mock_get):
    # Generic MIME but .md extension in path → should still convert
    mock_get.return_value = _mock_response(
        "## Title\n\nBody.\n",
        "text/plain",
        url="https://example.com/README.md",
    )
    mock_get.return_value.url.path = "/README.md"
    result = read_url("https://example.com/README.md")
    assert "== Title" in result


@patch("mlite.mcp_server.httpx.get")
def test_read_url_passthrough_unsupported_mime(mock_get):
    # application/pdf has no registered adapter — should pass through verbatim
    content = b"%PDF-1.4 binary content"
    mock_get.return_value = _mock_response(content.decode("latin-1"), "application/pdf")
    result = read_url("https://example.com/doc.pdf")
    assert result == content.decode("latin-1")


@patch("mlite.mcp_server.httpx.get")
def test_read_url_preserve_emphasis_default(mock_get):
    mock_get.return_value = _mock_response(
        "**bold** text\n", "text/markdown"
    )
    result = read_url("https://example.com/doc.md")
    assert "*bold*" in result


@patch("mlite.mcp_server.httpx.get")
def test_read_url_strip_emphasis(mock_get):
    mock_get.return_value = _mock_response(
        "**bold** text\n", "text/markdown"
    )
    result = read_url("https://example.com/doc.md", preserve_emphasis=False)
    assert "*bold*" not in result
    assert "bold" in result


# ── server metadata ───────────────────────────────────────────────────────────

def test_server_has_two_tools():
    import asyncio
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert "read_file" in names
    assert "read_url" in names


def test_tool_descriptions_mention_mlite():
    import asyncio
    tools = asyncio.run(mcp.list_tools())
    for tool in tools:
        desc = (tool.description or "").lower()
        assert "mlite" in desc
