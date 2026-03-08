"""Tests for the PythonAdapter (py_adapter)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mlite.adapters.py_adapter import python_to_mlite, PYTHON_ADAPTER
from mlite.adapters import get_registry

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Golden-file tests
# ---------------------------------------------------------------------------


def test_basic_golden() -> None:
    src = (FIXTURES / "sample.py").read_text(encoding="utf-8")
    golden = (FIXTURES / "sample_python.mlt").read_text(encoding="utf-8")
    assert python_to_mlite(src, filename="sample.py") == golden


def test_extract_docs_golden() -> None:
    src = (FIXTURES / "sample.py").read_text(encoding="utf-8")
    golden = (FIXTURES / "sample_python_extract.mlt").read_text(encoding="utf-8")
    assert python_to_mlite(src, filename="sample.py", extract_docs=True) == golden


# ---------------------------------------------------------------------------
# Unit tests — basic envelope
# ---------------------------------------------------------------------------


def test_basic_has_filename_heading() -> None:
    out = python_to_mlite("x = 1\n", filename="utils.py")
    assert out.startswith("= utils.py\n")


def test_basic_has_code_fence() -> None:
    out = python_to_mlite("x = 1\n", filename="utils.py")
    assert "`python\nx = 1\n`\n" in out


def test_basic_no_extract_sections() -> None:
    out = python_to_mlite("def foo(): pass\n", filename="foo.py")
    assert "== Functions" not in out
    assert "== Module Docstring" not in out


def test_output_ends_with_newline() -> None:
    out = python_to_mlite("x = 1\n", filename="a.py")
    assert out.endswith("\n")
    assert not out.endswith("\n\n")


# ---------------------------------------------------------------------------
# Unit tests — extract_docs mode
# ---------------------------------------------------------------------------


def test_extract_module_docstring() -> None:
    src = '"""Top-level module doc."""\n\ndef foo(): pass\n'
    out = python_to_mlite(src, filename="m.py", extract_docs=True)
    assert "== Module Docstring\nTop-level module doc." in out


def test_extract_function_signature() -> None:
    src = 'def greet(name: str) -> str:\n    """Say hello."""\n    return name\n'
    out = python_to_mlite(src, filename="m.py", extract_docs=True)
    assert "- greet(name: str) \u2192 Say hello." in out


def test_extract_class() -> None:
    src = 'class Foo:\n    """A foo class."""\n    pass\n'
    out = python_to_mlite(src, filename="m.py", extract_docs=True)
    assert "== Classes\n- Foo \u2192 A foo class." in out


def test_extract_skips_private_functions() -> None:
    src = "def _helper(): pass\ndef public(): pass\n"
    out = python_to_mlite(src, filename="m.py", extract_docs=True)
    # Private names appear in the source block but must not appear in the
    # Functions section (everything before == Source)
    extract_section = out.split("== Source")[0]
    assert "_helper" not in extract_section
    assert "- public()" in extract_section


def test_extract_skips_private_classes() -> None:
    src = "class _Internal: pass\nclass Public: pass\n"
    out = python_to_mlite(src, filename="m.py", extract_docs=True)
    extract_section = out.split("== Source")[0]
    assert "_Internal" not in extract_section
    assert "- Public" in extract_section


def test_extract_source_block_present() -> None:
    src = '"""doc"""\ndef f(): pass\n'
    out = python_to_mlite(src, filename="m.py", extract_docs=True)
    assert "== Source\n`python\n" in out


def test_extract_no_module_doc_skips_section() -> None:
    src = "def f(): pass\n"
    out = python_to_mlite(src, filename="m.py", extract_docs=True)
    assert "== Module Docstring" not in out


def test_extract_no_functions_skips_section() -> None:
    src = '"""doc"""\nx = 1\n'
    out = python_to_mlite(src, filename="m.py", extract_docs=True)
    assert "== Functions" not in out


def test_syntax_error_falls_back_to_basic() -> None:
    src = "def broken(\n"
    out = python_to_mlite(src, filename="bad.py", extract_docs=True)
    # Should still produce a valid basic envelope — no crash, no extract sections
    assert out.startswith("= bad.py\n")
    assert "== Functions" not in out
    assert "`python\n" in out


def test_value_error_falls_back_to_basic() -> None:
    # ast.parse raises ValueError for source containing null bytes
    src = "x = 1\x00\n"
    out = python_to_mlite(src, filename="bad.py", extract_docs=True)
    assert out.startswith("= bad.py\n")
    assert "== Functions" not in out
    assert "`python\n" in out


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


def test_registry_for_py_extension() -> None:
    reg = get_registry()
    adapter = reg.for_path("script.py")
    assert adapter is not None
    assert adapter.source_mime == "text/x-python"


def test_registry_for_mime() -> None:
    reg = get_registry()
    adapter = reg.for_mime("text/x-python")
    assert adapter is not None


def test_registry_adapter_converts_with_filename() -> None:
    # Callers dispatching through the registry must pass filename as a kwarg;
    # the CLI and MCP server do this using the path they already hold.
    reg = get_registry()
    adapter = reg.for_path("utils.py")
    assert adapter is not None
    result = adapter.to_mlite("x = 1\n", filename="utils.py")
    assert result.startswith("= utils.py\n")


def test_from_mlite_is_none() -> None:
    assert PYTHON_ADAPTER.from_mlite is None


def test_arg_str_renders_defaults() -> None:
    src = "def f(x: int = 0, y: str = 'hi'): pass\n"
    out = python_to_mlite(src, filename="m.py", extract_docs=True)
    assert "f(x: int=0, y: str='hi')" in out


def test_arg_str_renders_posonly_separator() -> None:
    src = "def f(a, b, /, c): pass\n"
    out = python_to_mlite(src, filename="m.py", extract_docs=True)
    assert "f(a, b, /, c)" in out
