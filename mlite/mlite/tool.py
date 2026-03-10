"""Claude API tool definition for transparent MLite file conversion.

Drop-in tool definition and handler for use with the Anthropic Python SDK.
No MCP server required — works with any ``anthropic.Anthropic()`` client.

Minimal usage example::

    import anthropic
    from mlite.tool import READ_FILE_TOOL, SYSTEM_PROMPT_SNIPPET, handle_tool_call

    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": "Summarize README.md"}]

    while True:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            system=f"You are a helpful assistant.\\n\\n{SYSTEM_PROMPT_SNIPPET}",
            tools=[READ_FILE_TOOL],
            messages=messages,
        )

        # Append assistant turn to conversation history
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            # Claude is done — print final text response
            for block in response.content:
                if block.type == "text":
                    print(block.text)
            break

        # Execute each tool call and collect results
        results = []
        for block in response.content:
            if block.type == "tool_use":
                output = handle_tool_call(block.name, block.input)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                })

        messages.append({"role": "user", "content": results})
"""

from __future__ import annotations

from pathlib import Path

from mlite.adapters import get_registry

# ---------------------------------------------------------------------------
# System prompt snippet
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_SNIPPET: str = (
    "When you need to read a local file, use the read_file tool.\n"
    "It converts Markdown (.md, .markdown), HTML (.html, .htm), and Python (.py) "
    "files to MLite — a token-efficient wire format that reduces context consumption "
    "by 15–35% with no information loss.\n"
    "Always prefer read_file over reproducing or summarising file contents verbatim."
)

# ---------------------------------------------------------------------------
# Tool schema
# ---------------------------------------------------------------------------

READ_FILE_TOOL: dict = {
    "name": "read_file",
    "description": (
        "Read a local file and return its contents. "
        "Markdown (.md, .markdown), HTML (.html, .htm), and Python (.py) files are "
        "automatically converted to MLite — a token-efficient format that uses "
        "15–35% fewer tokens than the source while preserving all content. "
        "Unsupported file types are returned verbatim."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or relative path to the file.",
            },
            "preserve_emphasis": {
                "type": "boolean",
                "description": (
                    "If false, strip bold/italic markers entirely for maximum "
                    "token savings. Defaults to true (normalized to *text* form)."
                ),
            },
        },
        "required": ["path"],
    },
}

# ---------------------------------------------------------------------------
# Tool handler
# ---------------------------------------------------------------------------


def handle_tool_call(name: str, input_dict: dict) -> str:
    """Dispatch a tool call and return the result as a string.

    Currently handles ``read_file``.
    Unknown tool names raise ``ValueError``.

    Args:
        name: The tool name from the ``tool_use`` block.
        input_dict: The ``input`` dict from the ``tool_use`` block.

    Returns:
        File contents, converted to MLite for supported types or verbatim
        for unsupported types.

    Raises:
        ValueError: If ``name`` is not a recognised tool.
        FileNotFoundError: If the requested path does not exist.
        OSError: For other I/O errors.
    """
    if name == "read_file":
        return _read_file(**input_dict)
    raise ValueError(f"Unknown tool: {name!r}")


def _read_file(path: str, preserve_emphasis: bool = True) -> str:
    """Implement the read_file tool."""
    import inspect

    file_path = Path(path)
    source = file_path.read_text(encoding="utf-8")

    registry = get_registry()
    adapter = registry.for_path(file_path)

    if adapter is None:
        return source

    # Pass filename to adapters that accept it (e.g. PythonAdapter)
    sig = inspect.signature(adapter.to_mlite)
    kwargs: dict = {}
    if "preserve_emphasis" in sig.parameters:
        kwargs["preserve_emphasis"] = preserve_emphasis
    if "filename" in sig.parameters:
        kwargs["filename"] = file_path.name
    return adapter.to_mlite(source, **kwargs)
