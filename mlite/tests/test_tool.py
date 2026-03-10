"""Tests for mlite.tool — Claude API tool definition and handler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from mlite.tool import READ_FILE_TOOL, SYSTEM_PROMPT_SNIPPET, handle_tool_call


FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# READ_FILE_TOOL schema
# ---------------------------------------------------------------------------


def test_tool_is_dict():
    assert isinstance(READ_FILE_TOOL, dict)


def test_tool_has_required_keys():
    assert "name" in READ_FILE_TOOL
    assert "description" in READ_FILE_TOOL
    assert "input_schema" in READ_FILE_TOOL


def test_tool_name():
    assert READ_FILE_TOOL["name"] == "read_file"


def test_tool_description_mentions_mlite():
    assert "mlite" in READ_FILE_TOOL["description"].lower()


def test_tool_description_mentions_supported_types():
    desc = READ_FILE_TOOL["description"].lower()
    assert ".md" in desc
    assert ".html" in desc
    assert ".py" in desc


def test_tool_schema_path_required():
    schema = READ_FILE_TOOL["input_schema"]
    assert "path" in schema["required"]


def test_tool_schema_preserve_emphasis_optional():
    schema = READ_FILE_TOOL["input_schema"]
    assert "preserve_emphasis" in schema["properties"]
    assert "preserve_emphasis" not in schema.get("required", [])


def test_tool_schema_valid_json_schema_type():
    schema = READ_FILE_TOOL["input_schema"]
    assert schema["type"] == "object"
    assert schema["properties"]["path"]["type"] == "string"
    assert schema["properties"]["preserve_emphasis"]["type"] == "boolean"


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT_SNIPPET
# ---------------------------------------------------------------------------


def test_system_prompt_is_str():
    assert isinstance(SYSTEM_PROMPT_SNIPPET, str)


def test_system_prompt_mentions_read_file():
    assert "read_file" in SYSTEM_PROMPT_SNIPPET


def test_system_prompt_mentions_mlite():
    assert "MLite" in SYSTEM_PROMPT_SNIPPET or "mlite" in SYSTEM_PROMPT_SNIPPET.lower()


def test_system_prompt_mentions_token_savings():
    assert "%" in SYSTEM_PROMPT_SNIPPET


def test_system_prompt_concatable():
    """Should be safely concatenable into a larger system prompt."""
    combined = f"You are a helpful assistant.\n\n{SYSTEM_PROMPT_SNIPPET}"
    assert "read_file" in combined


# ---------------------------------------------------------------------------
# handle_tool_call — Markdown conversion
# ---------------------------------------------------------------------------


def test_handle_converts_markdown(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("## Hello\n\nWorld.\n")
    result = handle_tool_call("read_file", {"path": str(md)})
    assert "== Hello" in result
    assert "World." in result


def test_handle_converts_html(tmp_path):
    html = tmp_path / "page.html"
    html.write_text("<h2>Hello</h2><p>World.</p>")
    result = handle_tool_call("read_file", {"path": str(html)})
    assert "== Hello" in result
    assert "World." in result


def test_handle_converts_python(tmp_path):
    py = tmp_path / "mod.py"
    py.write_text('"""A module."""\ndef foo(): pass\n')
    result = handle_tool_call("read_file", {"path": str(py)})
    assert "mod.py" in result
    assert "`python" in result


def test_handle_passthrough_unsupported(tmp_path):
    txt = tmp_path / "note.txt"
    txt.write_text("plain text\n")
    result = handle_tool_call("read_file", {"path": str(txt)})
    assert result == "plain text\n"


def test_handle_passthrough_binary_extension(tmp_path):
    """Non-text extensions with no registered adapter pass through verbatim."""
    data = tmp_path / "data.csv"
    data.write_text("a,b,c\n1,2,3\n")
    result = handle_tool_call("read_file", {"path": str(data)})
    assert result == "a,b,c\n1,2,3\n"


# ---------------------------------------------------------------------------
# handle_tool_call — preserve_emphasis flag
# ---------------------------------------------------------------------------


def test_handle_preserve_emphasis_default(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("**bold** and _italic_\n")
    result = handle_tool_call("read_file", {"path": str(md)})
    assert "*bold*" in result
    assert "*italic*" in result


def test_handle_strip_emphasis(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("**bold** and _italic_\n")
    result = handle_tool_call("read_file", {"path": str(md), "preserve_emphasis": False})
    assert "*" not in result
    assert "bold" in result
    assert "italic" in result


# ---------------------------------------------------------------------------
# handle_tool_call — golden file
# ---------------------------------------------------------------------------


def test_handle_golden_basic_md():
    golden = (FIXTURES / "basic.mlt").read_text()
    result = handle_tool_call("read_file", {"path": str(FIXTURES / "basic.md")})
    assert result == golden


# ---------------------------------------------------------------------------
# handle_tool_call — error cases
# ---------------------------------------------------------------------------


def test_handle_unknown_tool_raises():
    with pytest.raises(ValueError, match="Unknown tool"):
        handle_tool_call("nonexistent_tool", {"path": "x"})


def test_handle_file_not_found_raises():
    with pytest.raises(FileNotFoundError):
        handle_tool_call("read_file", {"path": "/nonexistent/path/file.md"})


# ---------------------------------------------------------------------------
# Integration: tool dict is compatible with anthropic SDK shape
# ---------------------------------------------------------------------------


def test_tool_dict_matches_anthropic_sdk_shape():
    """Verify the dict has the exact keys the Anthropic SDK expects."""
    assert set(READ_FILE_TOOL.keys()) == {"name", "description", "input_schema"}
    schema = READ_FILE_TOOL["input_schema"]
    assert schema["type"] == "object"
    assert isinstance(schema["properties"], dict)
    assert isinstance(schema["required"], list)
