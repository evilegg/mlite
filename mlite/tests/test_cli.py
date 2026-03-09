"""Tests for the mlite CLI."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from mlite.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def test_converts_markdown_to_stdout(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("## Hello\n\nWorld.\n")
    result = CliRunner().invoke(main, [str(md)])
    assert result.exit_code == 0
    assert "== Hello" in result.output
    assert "World." in result.output


def test_passthrough_unsupported_type(tmp_path):
    txt = tmp_path / "note.txt"
    txt.write_text("plain text content\n")
    result = CliRunner().invoke(main, [str(txt)])
    assert result.exit_code == 0
    assert result.output == "plain text content\n"


def test_stats_flag(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("## Heading\n\nSome paragraph text.\n")
    result = CliRunner().invoke(main, [str(md), "--stats"])
    assert result.exit_code == 0
    # stderr is mixed into output by default CliRunner
    assert "tokens:" in result.output
    assert "cl100k_base" in result.output
    assert "\u2192" in result.output


def test_preserve_emphasis_default(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("This has **bold** and _italic_ text.\n")
    result = CliRunner().invoke(main, [str(md)])
    assert result.exit_code == 0
    assert "*bold*" in result.output
    assert "*italic*" in result.output


def test_no_preserve_emphasis(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("This has **bold** and _italic_ text.\n")
    result = CliRunner().invoke(main, [str(md), "--no-preserve-emphasis"])
    assert result.exit_code == 0
    assert "**" not in result.output
    assert "*bold*" not in result.output
    assert "bold" in result.output


def test_from_mime_override(tmp_path):
    # .txt file forced through the markdown adapter via --from
    f = tmp_path / "doc.txt"
    f.write_text("## Heading\n\nParagraph.\n")
    result = CliRunner().invoke(main, [str(f), "--from", "text/markdown"])
    assert result.exit_code == 0
    assert "== Heading" in result.output


def test_help():
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "FILE" in result.output
    assert "--stats" in result.output
    assert "--from" in result.output


def test_fixture_basic():
    """Golden-file smoke test: basic.md output matches basic.mlt."""
    golden = (FIXTURES / "basic.mlt").read_text()
    result = CliRunner().invoke(main, [str(FIXTURES / "basic.md")])
    assert result.exit_code == 0
    assert result.output == golden
