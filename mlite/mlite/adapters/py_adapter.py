"""PythonAdapter — wraps Python source in a structured MLite envelope.

Basic mode: filename heading + verbatim code block.
extract_docs mode: additionally extracts module docstring and top-level
function/class signatures with first-line docstrings before the source block.
"""

from __future__ import annotations

import ast

from mlite.adapters.base import FormatAdapter


def _first_line(docstring: str | None) -> str:
    """Return the first non-empty line of a docstring, or empty string."""
    if not docstring:
        return ""
    for line in docstring.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def _arg_str(args: ast.arguments) -> str:
    """Render an ast.arguments node as a compact parameter string."""
    params: list[str] = []

    # positional-only (Python 3.8+)
    for arg in args.posonlyargs:
        params.append(arg.arg if arg.annotation is None else f"{arg.arg}: {ast.unparse(arg.annotation)}")

    for arg in args.args:
        params.append(arg.arg if arg.annotation is None else f"{arg.arg}: {ast.unparse(arg.annotation)}")

    if args.vararg:
        a = args.vararg
        params.append(f"*{a.arg}" if a.annotation is None else f"*{a.arg}: {ast.unparse(a.annotation)}")

    for arg in args.kwonlyargs:
        params.append(arg.arg if arg.annotation is None else f"{arg.arg}: {ast.unparse(arg.annotation)}")

    if args.kwarg:
        a = args.kwarg
        params.append(f"**{a.arg}" if a.annotation is None else f"**{a.arg}: {ast.unparse(a.annotation)}")

    return ", ".join(params)


def _extract(source: str) -> tuple[str, list[str], list[str]]:
    """Parse source and return (module_doc, function_lines, class_lines)."""
    tree = ast.parse(source)
    module_doc = ast.get_docstring(tree) or ""

    functions: list[str] = []
    classes: list[str] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            sig = f"{node.name}({_arg_str(node.args)})"
            doc = _first_line(ast.get_docstring(node))
            functions.append(f"- {sig}" + (f" \u2192 {doc}" if doc else ""))
        elif isinstance(node, ast.ClassDef):
            if node.name.startswith("_"):
                continue
            doc = _first_line(ast.get_docstring(node))
            classes.append(f"- {node.name}" + (f" \u2192 {doc}" if doc else ""))

    return module_doc, functions, classes


def python_to_mlite(
    source: str,
    *,
    filename: str = "source.py",
    extract_docs: bool = False,
) -> str:
    lines: list[str] = [f"= {filename}"]

    if extract_docs:
        try:
            module_doc, functions, classes = _extract(source)
        except (SyntaxError, ValueError):
            # Fall back to basic envelope on unparseable source.
            # ast.parse raises SyntaxError for invalid syntax and ValueError
            # for source containing null bytes or other illegal content.
            extract_docs = False
        else:
            if module_doc:
                lines.append("== Module Docstring")
                lines.append(_first_line(module_doc))
            if functions:
                lines.append("== Functions")
                lines.extend(functions)
            if classes:
                lines.append("== Classes")
                lines.extend(classes)
            lines.append("== Source")

    # Build the code fence as a single string so source is preserved verbatim.
    # Ensure source ends with exactly one newline so the closing backtick
    # sits on its own line without introducing an extra blank line.
    src_body = source if source.endswith("\n") else source + "\n"
    fence = "`python\n" + src_body + "`\n"

    return "\n".join(lines) + "\n" + fence


PYTHON_ADAPTER = FormatAdapter(
    source_mime="text/x-python",
    source_extensions=["py"],
    to_mlite=python_to_mlite,
    from_mlite=None,
)
