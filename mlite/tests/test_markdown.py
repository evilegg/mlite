"""Regression tests for the Markdown → MLite adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from mlite.adapters.markdown import markdown_to_mlite
from mlite.adapters import AdapterRegistry, get_registry

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> tuple[str, str]:
    """Return (source_md, golden_mlt) for a fixture pair."""
    src = (FIXTURES / f"{name}.md").read_text()
    golden = (FIXTURES / f"{name}.mlt").read_text()
    return src, golden


# ---------------------------------------------------------------------------
# Golden-file regression tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["basic", "code_heavy", "table", "nested"])
def test_fixture_golden(name: str) -> None:
    src, golden = _load(name)
    assert markdown_to_mlite(src) == golden


@pytest.mark.parametrize(
    "preserve,golden_name",
    [(False, "emphasis"), (True, "emphasis.preserve")],
    ids=["strip", "preserve"],
)
def test_fixture_emphasis(preserve: bool, golden_name: str) -> None:
    src = (FIXTURES / "emphasis.md").read_text(encoding="utf-8")
    golden = (FIXTURES / f"{golden_name}.mlt").read_text(encoding="utf-8")
    assert markdown_to_mlite(src, preserve_emphasis=preserve) == golden


# ---------------------------------------------------------------------------
# Targeted unit tests
# ---------------------------------------------------------------------------


def test_heading_levels() -> None:
    src = "# H1\n## H2\n### H3\n#### H4\n##### H5\n###### H6\n"
    out = markdown_to_mlite(src)
    assert "= H1" in out
    assert "== H2" in out
    assert "=== H3" in out
    assert "==== H4" in out
    assert "===== H5" in out
    assert "====== H6" in out


def test_emphasis_stripped_by_default() -> None:
    src = "**bold** and *italic* text.\n"
    out = markdown_to_mlite(src)
    assert "**" not in out
    assert "__" not in out
    assert out.strip() == "bold and italic text."


def test_preserve_emphasis() -> None:
    src = "**bold** and *italic* text.\n"
    out = markdown_to_mlite(src, preserve_emphasis=True)
    assert "*bold*" in out
    assert "*italic*" in out


def test_inline_code_preserved() -> None:
    src = "Use `pip install mlite` to install.\n"
    out = markdown_to_mlite(src)
    assert "`pip install mlite`" in out


def test_strikethrough_preserved() -> None:
    src = "This is ~~deleted~~ text.\n"
    out = markdown_to_mlite(src)
    assert "~~deleted~~" in out


def test_code_block_fenced() -> None:
    src = "```python\ndef hello():\n    pass\n```\n"
    out = markdown_to_mlite(src)
    lines = out.splitlines()
    assert lines[0] == "`python"
    assert lines[1] == "def hello():"
    assert lines[2] == "    pass"
    assert lines[3] == "`"


def test_code_block_no_language() -> None:
    src = "```\nplain text\n```\n"
    out = markdown_to_mlite(src)
    assert out.startswith("`\n")
    assert "`\nplain text\n`" in out


def test_ordered_list_uses_paren() -> None:
    src = "1. First\n2. Second\n3. Third\n"
    out = markdown_to_mlite(src)
    assert "1) First" in out
    assert "2) Second" in out
    assert "3) Third" in out
    assert "1." not in out


def test_unordered_list() -> None:
    src = "- Alpha\n- Beta\n- Gamma\n"
    out = markdown_to_mlite(src)
    assert "- Alpha" in out
    assert "- Beta" in out


def test_nested_list_indentation() -> None:
    src = "- Parent\n  - Child\n    - Grandchild\n"
    out = markdown_to_mlite(src)
    assert "- Parent" in out
    assert "  - Child" in out
    assert "    - Grandchild" in out


def test_link_url_first() -> None:
    src = "See [the docs](https://example.com) for details.\n"
    out = markdown_to_mlite(src)
    assert "https://example.com[the docs]" in out
    assert "[the docs](https://example.com)" not in out


def test_bare_url_no_delimiters() -> None:
    src = "Visit <https://example.com> today.\n"
    out = markdown_to_mlite(src)
    # bare autolink should become just the URL
    assert "https://example.com" in out


def test_image_syntax() -> None:
    src = "![logo](https://example.com/logo.png)\n"
    out = markdown_to_mlite(src)
    assert "!https://example.com/logo.png[logo]" in out


def test_blockquote() -> None:
    src = "> This is a quote.\n"
    out = markdown_to_mlite(src)
    assert "> This is a quote." in out


def test_nested_blockquote() -> None:
    src = "> Outer.\n>> Inner.\n"
    out = markdown_to_mlite(src)
    assert "> Outer." in out
    assert ">> Inner." in out


def test_thematic_break() -> None:
    src = "Before\n\n---\n\nAfter\n"
    out = markdown_to_mlite(src)
    assert "---" in out


def test_table() -> None:
    src = "| A | B |\n|---|---|\n| 1 | 2 |\n"
    out = markdown_to_mlite(src)
    assert "| A | B |" in out
    assert "|---|" in out
    assert "| 1 | 2 |" in out


def test_no_blank_lines_between_blocks() -> None:
    src = "# Heading\n\nParagraph one.\n\nParagraph two.\n"
    out = markdown_to_mlite(src)
    assert "\n\n" not in out


def test_output_ends_with_single_newline() -> None:
    for name in ["basic", "emphasis", "table"]:
        src, _ = _load(name)
        out = markdown_to_mlite(src)
        assert out.endswith("\n")
        assert not out.endswith("\n\n")


# ---------------------------------------------------------------------------
# AdapterRegistry tests
# ---------------------------------------------------------------------------


def test_registry_for_path_md() -> None:
    reg = get_registry()
    adapter = reg.for_path("README.md")
    assert adapter is not None
    assert adapter.source_mime == "text/markdown"


def test_registry_for_path_markdown() -> None:
    reg = get_registry()
    assert reg.for_path("doc.markdown") is not None


def test_registry_for_path_unknown() -> None:
    reg = get_registry()
    assert reg.for_path("file.xyz") is None


def test_registry_for_mime() -> None:
    reg = get_registry()
    adapter = reg.for_mime("text/markdown")
    assert adapter is not None


def test_registry_for_mime_unknown() -> None:
    reg = get_registry()
    assert reg.for_mime("application/octet-stream") is None


def test_registry_adapter_converts() -> None:
    reg = get_registry()
    adapter = reg.for_path("doc.md")
    assert adapter is not None
    result = adapter.to_mlite("# Hello\n\nWorld.\n")
    assert result == "= Hello\nWorld.\n"
