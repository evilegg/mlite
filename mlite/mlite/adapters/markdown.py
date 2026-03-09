"""Markdown → MLite adapter using mistune 3.x AST walker."""

from __future__ import annotations

import mistune

from mlite.adapters.base import FormatAdapter


# ---------------------------------------------------------------------------
# Inline rendering
# ---------------------------------------------------------------------------


def _render_inline(children: list[dict], preserve_emphasis: bool) -> str:
    """Render a list of inline tokens to an MLite string."""
    parts: list[str] = []
    for token in children:
        t = token.get("type")
        if t in ("text", "raw_text"):
            parts.append(token.get("raw", ""))
        elif t == "softbreak":
            parts.append(" ")
        elif t in ("linebreak", "hardbreak"):
            parts.append("\n")
        elif t in ("strong", "emphasis"):
            inner = _render_inline(token.get("children", []), preserve_emphasis)
            if preserve_emphasis:
                parts.append(f"*{inner}*")
            else:
                parts.append(inner)
        elif t == "codespan":
            parts.append(f"`{token['raw']}`")
        elif t == "link":
            url = token["attrs"]["url"]
            inner = _render_inline(token.get("children", []), preserve_emphasis)
            if inner and inner != url:
                parts.append(f"{url}[{inner}]")
            else:
                parts.append(url)
        elif t == "image":
            url = token["attrs"]["url"]
            alt = _render_inline(token.get("children", []), preserve_emphasis)
            parts.append(f"!{url}[{alt}]" if alt else f"!{url}")
        elif t == "strikethrough":
            inner = _render_inline(token.get("children", []), preserve_emphasis)
            parts.append(f"~~{inner}~~")
        # inline_html, ref_link, etc. — silently skip
    return "".join(parts)


# ---------------------------------------------------------------------------
# Block rendering
# ---------------------------------------------------------------------------


def _render_block(
    token: dict,
    preserve_emphasis: bool = False,
    prefix: str = "",
) -> list[str]:
    """Render a single block token to a list of output lines."""
    t = token.get("type")

    if t == "heading":
        level: int = token["attrs"]["level"]
        text = _render_inline(token.get("children", []), preserve_emphasis)
        return [f'{prefix}{"=" * level} {text}']

    if t in ("paragraph", "block_text"):
        text = _render_inline(token.get("children", []), preserve_emphasis)
        # text may contain "\n" from hard line breaks — prefix each line
        return [f"{prefix}{line}" for line in text.split("\n")]

    if t == "block_code":
        info = (token.get("attrs", {}).get("info") or "").strip()
        lang = info.split()[0] if info else ""
        code = token.get("raw", "").rstrip("\n")
        lines = [f"{prefix}`{lang}"]
        lines.extend(f"{prefix}{line}" for line in code.split("\n"))
        lines.append(f"{prefix}`")
        return lines

    if t == "list":
        ordered: bool = token["attrs"].get("ordered", False)
        lines: list[str] = []
        for i, item in enumerate(token.get("children", []), 1):
            lines.extend(_render_list_item(item, ordered, i, preserve_emphasis, prefix))
        return lines

    if t == "block_quote":
        depth = prefix.count(">") + 1
        inner_prefix = ">" * depth + " "
        lines = []
        for child in token.get("children", []):
            lines.extend(_render_block(child, preserve_emphasis, inner_prefix))
        return lines

    if t == "thematic_break":
        return [f"{prefix}---"]

    if t == "table":
        return _render_table(token, preserve_emphasis, prefix)

    # blank_line, block_html, and unrecognised tokens produce no output
    return []


def _render_list_item(
    item: dict,
    ordered: bool,
    index: int,
    preserve_emphasis: bool,
    prefix: str,
) -> list[str]:
    """Render a list_item token."""
    bullet = f"{index})" if ordered else "-"
    children = item.get("children", [])
    lines: list[str] = []
    first_text = True

    for child in children:
        ct = child.get("type")
        if ct in ("block_text", "paragraph") and first_text:
            text = _render_inline(child.get("children", []), preserve_emphasis)
            lines.append(f"{prefix}{bullet} {text}")
            first_text = False
        elif ct == "list":
            sub_ordered: bool = child["attrs"].get("ordered", False)
            for j, sub_item in enumerate(child.get("children", []), 1):
                lines.extend(
                    _render_list_item(sub_item, sub_ordered, j, preserve_emphasis, prefix + "  ")
                )
        elif not first_text:
            # loose list item: additional paragraphs/blocks after the first
            lines.extend(_render_block(child, preserve_emphasis, prefix + "  "))

    return lines


def _render_table(token: dict, preserve_emphasis: bool, prefix: str = "") -> list[str]:
    """Render a table token.

    mistune 3.x table structure:
      table
        table_head  → children are table_cell (no intervening table_row)
        table_body  → children are table_row → children are table_cell
    """
    lines: list[str] = []
    for section in token.get("children", []):
        stype = section["type"]
        if stype == "table_head":
            cells = [
                _render_inline(cell.get("children", []), preserve_emphasis)
                for cell in section.get("children", [])
            ]
            lines.append(f"{prefix}| " + " | ".join(cells) + " |")
            lines.append(f"{prefix}|---|")
        elif stype == "table_body":
            for row in section.get("children", []):
                cells = [
                    _render_inline(cell.get("children", []), preserve_emphasis)
                    for cell in row.get("children", [])
                ]
                lines.append(f"{prefix}| " + " | ".join(cells) + " |")
    return lines


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def markdown_to_mlite(source: str, *, preserve_emphasis: bool = True) -> str:
    """Convert a Markdown string to MLite format.

    Args:
        source: Raw Markdown text.
        preserve_emphasis: If True, emit *text* for bold/italic instead of
            stripping emphasis markers.

    Returns:
        MLite-formatted string, terminated by a single newline.
    """
    md = mistune.create_markdown(renderer=None, plugins=["table", "strikethrough"])
    tokens: list[dict] = md(source)  # type: ignore[assignment]
    lines: list[str] = []
    for token in tokens:
        lines.extend(_render_block(token, preserve_emphasis))
    return "\n".join(lines).strip() + "\n"


MARKDOWN_ADAPTER = FormatAdapter(
    source_mime="text/markdown",
    source_extensions=["md", "markdown", "mdown", "mkd"],
    to_mlite=markdown_to_mlite,
    from_mlite=None,  # lossy: emphasis stripped, link syntax inverted
)
