"""MCP server subprocess E2E tests.

Starts the real ``mlite-mcp`` binary and communicates over stdio JSON-RPC.
Tests the full transport layer: initialize handshake, tools/list, tools/call.

All tests are skipped if ``mlite-mcp`` is not on PATH (e.g. not installed).
No network access or API keys required.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Resolve mlite-mcp binary
# ---------------------------------------------------------------------------

def _find_mlite_mcp() -> str | None:
    """Return path to mlite-mcp binary, checking venv bin dir before PATH."""
    # Check alongside the current Python interpreter first (covers venv usage)
    venv_bin = Path(sys.executable).parent / "mlite-mcp"
    if venv_bin.exists():
        return str(venv_bin)
    return shutil.which("mlite-mcp")


_MLITE_MCP = _find_mlite_mcp()

pytestmark = pytest.mark.skipif(
    _MLITE_MCP is None,
    reason="mlite-mcp not found — run: uv pip install -e .",
)


# ---------------------------------------------------------------------------
# Subprocess fixture
# ---------------------------------------------------------------------------


def _send(proc: subprocess.Popen, method: str, params: dict | None = None, id: int | None = None) -> dict | None:
    """Write one JSON-RPC message; return parsed response if id is given."""
    msg: dict = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if id is not None:
        msg["id"] = id
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    if id is not None:
        line = proc.stdout.readline()
        return json.loads(line)
    return None


def _handshake(proc: subprocess.Popen) -> dict:
    """Perform initialize + notifications/initialized; return init result."""
    result = _send(
        proc,
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "pytest-e2e", "version": "0.0.1"},
        },
        id=1,
    )
    _send(proc, "notifications/initialized")
    return result


@pytest.fixture(scope="module")
def mcp_proc():
    """Start mlite-mcp once for the whole module; tear down after all tests."""
    proc = subprocess.Popen(
        [_MLITE_MCP],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    _handshake(proc)
    yield proc
    proc.terminate()
    proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_next_id = iter(range(2, 10_000))


def call(proc: subprocess.Popen, method: str, params: dict | None = None) -> dict:
    """Send a request and return the parsed response."""
    return _send(proc, method, params, id=next(_next_id))


# ---------------------------------------------------------------------------
# Initialize
# ---------------------------------------------------------------------------


def test_initialize_returns_correct_protocol_version():
    """Server must respond with the protocol version it was asked to use."""
    proc = subprocess.Popen(
        [_MLITE_MCP],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        result = _handshake(proc)
        assert result["result"]["protocolVersion"] == "2024-11-05"
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_initialize_includes_server_info():
    proc = subprocess.Popen(
        [_MLITE_MCP],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        result = _handshake(proc)
        assert "serverInfo" in result["result"]
    finally:
        proc.terminate()
        proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# tools/list
# ---------------------------------------------------------------------------


def test_tools_list_returns_both_tools(mcp_proc):
    result = call(mcp_proc, "tools/list")
    names = {t["name"] for t in result["result"]["tools"]}
    assert names == {"read_file", "read_url"}


def test_tools_list_read_file_has_description(mcp_proc):
    result = call(mcp_proc, "tools/list")
    tools = {t["name"]: t for t in result["result"]["tools"]}
    desc = tools["read_file"]["description"].lower()
    assert "mlite" in desc


def test_tools_list_read_file_schema(mcp_proc):
    result = call(mcp_proc, "tools/list")
    tools = {t["name"]: t for t in result["result"]["tools"]}
    schema = tools["read_file"]["inputSchema"]
    assert schema["type"] == "object"
    assert "path" in schema["properties"]
    assert "path" in schema["required"]


# ---------------------------------------------------------------------------
# tools/call — read_file
# ---------------------------------------------------------------------------


def test_read_file_converts_markdown(mcp_proc, tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("## Section\n\nParagraph text.\n")
    result = call(mcp_proc, "tools/call", {"name": "read_file", "arguments": {"path": str(md)}})
    text = result["result"]["content"][0]["text"]
    assert "== Section" in text
    assert "Paragraph text." in text


def test_read_file_converts_html(mcp_proc, tmp_path):
    html = tmp_path / "page.html"
    html.write_text("<h1>Title</h1><p>Body.</p>")
    result = call(mcp_proc, "tools/call", {"name": "read_file", "arguments": {"path": str(html)}})
    text = result["result"]["content"][0]["text"]
    assert "= Title" in text
    assert "Body." in text


def test_read_file_passthrough_unsupported(mcp_proc, tmp_path):
    txt = tmp_path / "note.txt"
    txt.write_text("plain text\n")
    result = call(mcp_proc, "tools/call", {"name": "read_file", "arguments": {"path": str(txt)}})
    text = result["result"]["content"][0]["text"]
    assert text == "plain text\n"


def test_read_file_preserve_emphasis_default(mcp_proc, tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("**bold** word\n")
    result = call(mcp_proc, "tools/call", {"name": "read_file", "arguments": {"path": str(md)}})
    text = result["result"]["content"][0]["text"]
    assert "*bold*" in text


def test_read_file_strip_emphasis(mcp_proc, tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("**bold** word\n")
    result = call(
        mcp_proc,
        "tools/call",
        {"name": "read_file", "arguments": {"path": str(md), "preserve_emphasis": False}},
    )
    text = result["result"]["content"][0]["text"]
    assert "*" not in text
    assert "bold" in text


def test_read_file_golden_basic(mcp_proc):
    golden = (FIXTURES / "basic.mlt").read_text()
    result = call(
        mcp_proc,
        "tools/call",
        {"name": "read_file", "arguments": {"path": str(FIXTURES / "basic.md")}},
    )
    text = result["result"]["content"][0]["text"]
    assert text == golden


def test_read_file_is_not_error(mcp_proc, tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("# Hello\n")
    result = call(mcp_proc, "tools/call", {"name": "read_file", "arguments": {"path": str(md)}})
    assert result["result"].get("isError") is not True


def test_read_file_missing_path_returns_error(mcp_proc):
    result = call(
        mcp_proc,
        "tools/call",
        {"name": "read_file", "arguments": {"path": "/nonexistent/path/file.md"}},
    )
    # FastMCP surfaces tool exceptions as isError: true
    assert result["result"].get("isError") is True
