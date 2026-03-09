"""Tests for the HTML → MLite adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from mlite.adapters.html import html_to_mlite
from mlite.adapters import get_registry

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> tuple[str, str]:
    src = (FIXTURES / f"{name}.html").read_text(encoding="utf-8")
    golden = (FIXTURES / f"{name}_html.mlt").read_text(encoding="utf-8")
    return src, golden


# ---------------------------------------------------------------------------
# Golden-file regression tests
# ---------------------------------------------------------------------------


def test_fixture_basic():
    src, golden = _load("basic")
    assert html_to_mlite(src) == golden


def test_fixture_table():
    src, golden = _load("table")
    assert html_to_mlite(src) == golden


def test_fixture_emphasis_preserve():
    src, golden = _load("emphasis")
    assert html_to_mlite(src, preserve_emphasis=True) == golden


def test_fixture_links_images():
    src, golden = _load("links_images")
    assert html_to_mlite(src) == golden


# ---------------------------------------------------------------------------
# Headings
# ---------------------------------------------------------------------------


def test_headings_h1_to_h6():
    src = "".join(f"<h{n}>Level {n}</h{n}>\n" for n in range(1, 7))
    out = html_to_mlite(src)
    for n in range(1, 7):
        assert f"{'=' * n} Level {n}" in out


# ---------------------------------------------------------------------------
# Paragraphs
# ---------------------------------------------------------------------------


def test_paragraph():
    out = html_to_mlite("<p>Hello world.</p>")
    assert out.strip() == "Hello world."


def test_head_stripped():
    src = "<html><head><title>Title</title><style>body{}</style></head><body><p>Content</p></body></html>"
    out = html_to_mlite(src)
    assert "Title" not in out
    assert "body{}" not in out
    assert "Content" in out


def test_script_stripped():
    out = html_to_mlite("<p>Text</p><script>alert('x')</script>")
    assert "alert" not in out
    assert "Text" in out


def test_style_stripped():
    out = html_to_mlite("<p>Text</p><style>.foo { color: red; }</style>")
    assert "color" not in out
    assert "Text" in out


def test_html_comment_stripped():
    out = html_to_mlite("<p>Before</p><!-- a comment --><p>After</p>")
    assert "comment" not in out
    assert "Before" in out
    assert "After" in out


# ---------------------------------------------------------------------------
# Links and images
# ---------------------------------------------------------------------------


def test_link_with_label():
    out = html_to_mlite('<a href="https://example.com">the docs</a>')
    assert "https://example.com[the docs]" in out


def test_link_bare_url():
    out = html_to_mlite('<a href="https://example.com">https://example.com</a>')
    assert "https://example.com" in out
    assert "[" not in out


def test_image():
    out = html_to_mlite('<img src="https://example.com/img.png" alt="diagram">')
    assert "!https://example.com/img.png[diagram]" in out


def test_image_no_alt():
    out = html_to_mlite('<img src="https://example.com/img.png">')
    assert "!https://example.com/img.png" in out


# ---------------------------------------------------------------------------
# Code blocks
# ---------------------------------------------------------------------------


def test_code_block_with_language():
    src = '<pre><code class="language-python">x = 1</code></pre>'
    out = html_to_mlite(src)
    assert "`python" in out
    assert "x = 1" in out
    # closing backtick on its own line
    lines = out.strip().splitlines()
    assert lines[-1] == "`"


def test_code_block_no_language():
    src = "<pre><code>plain block</code></pre>"
    out = html_to_mlite(src)
    assert out.strip().startswith("`\n")
    assert "plain block" in out


def test_inline_code():
    out = html_to_mlite("<p>Use <code>mlite</code> here.</p>")
    assert "`mlite`" in out


# ---------------------------------------------------------------------------
# Emphasis
# ---------------------------------------------------------------------------


def test_emphasis_preserved_by_default():
    out = html_to_mlite("<p><strong>bold</strong> and <em>italic</em></p>")
    assert "*bold*" in out
    assert "*italic*" in out


def test_emphasis_stripped_when_requested():
    out = html_to_mlite("<p><strong>bold</strong> and <em>italic</em></p>", preserve_emphasis=False)
    assert "**" not in out
    assert "*bold*" not in out
    assert "bold" in out
    assert "italic" in out


def test_strikethrough():
    out = html_to_mlite("<p><del>removed</del></p>")
    assert "~~removed~~" in out


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------


def test_unordered_list():
    src = "<ul><li>Alpha</li><li>Beta</li><li>Gamma</li></ul>"
    out = html_to_mlite(src)
    assert "- Alpha" in out
    assert "- Beta" in out
    assert "- Gamma" in out


def test_ordered_list():
    src = "<ol><li>First</li><li>Second</li><li>Third</li></ol>"
    out = html_to_mlite(src)
    assert "1) First" in out
    assert "2) Second" in out
    assert "3) Third" in out


def test_nested_list():
    src = """
    <ul>
      <li>Parent
        <ul><li>Child A</li><li>Child B</li></ul>
      </li>
    </ul>
    """
    out = html_to_mlite(src)
    assert "- Parent" in out
    assert "  - Child A" in out
    assert "  - Child B" in out


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def test_table_basic():
    src = """
    <table>
      <tr><th>Name</th><th>Age</th></tr>
      <tr><td>Alice</td><td>30</td></tr>
    </table>
    """
    out = html_to_mlite(src)
    assert "| Name | Age |" in out
    assert "|---|" in out
    assert "| Alice | 30 |" in out


# ---------------------------------------------------------------------------
# Horizontal rule
# ---------------------------------------------------------------------------


def test_horizontal_rule():
    out = html_to_mlite("<hr>")
    assert "---" in out


# ---------------------------------------------------------------------------
# Token savings
# ---------------------------------------------------------------------------


def test_token_savings_exceeds_25_percent():
    """HTML adapter should save ≥25% tokens on a representative fixture."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
    except ImportError:
        pytest.skip("tiktoken not installed")

    src, _ = _load("basic")
    out = html_to_mlite(src)
    src_tokens = len(enc.encode(src))
    out_tokens = len(enc.encode(out))
    savings_pct = (src_tokens - out_tokens) / src_tokens * 100
    assert savings_pct >= 25, f"Expected ≥25% savings, got {savings_pct:.1f}%"


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


def test_registry_dispatches_html():
    registry = get_registry()
    adapter = registry.for_path("page.html")
    assert adapter is not None
    assert adapter.source_mime == "text/html"


def test_registry_dispatches_htm():
    registry = get_registry()
    adapter = registry.for_path("page.htm")
    assert adapter is not None
    assert adapter.source_mime == "text/html"


def test_registry_dispatches_mime():
    registry = get_registry()
    adapter = registry.for_mime("text/html")
    assert adapter is not None
