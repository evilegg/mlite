"""HTML → MLite adapter using BeautifulSoup4.

Implements the mapping from SPEC.md §4.2.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from mlite.adapters.base import FormatAdapter

# Tags whose entire subtree is discarded
_STRIP_TAGS = frozenset(
    ["script", "style", "head", "noscript", "template", "iframe", "svg"]
)

# Heading tag → MLite level
_HEADING_LEVEL = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}

# Transparent block containers — recurse into children
_CONTAINERS = frozenset(
    [
        "div", "section", "article", "main", "header", "footer",
        "nav", "aside", "figure", "figcaption", "address", "form",
        "details", "summary", "body", "html",
    ]
)

# Inline emphasis tags
_EMPHASIS_TAGS = frozenset(["strong", "b", "em", "i"])


# ---------------------------------------------------------------------------
# Inline rendering
# ---------------------------------------------------------------------------


def _inline(node: Tag | NavigableString, preserve_emphasis: bool) -> str:
    """Render a node's inline content to an MLite string."""
    if isinstance(node, Comment):
        return ""
    if isinstance(node, NavigableString):
        return str(node)

    tag = (node.name or "").lower()

    if tag in _STRIP_TAGS:
        return ""

    if tag == "br":
        return "\n"

    if tag == "a":
        href = (node.get("href") or "").strip()
        text = _collect_inline(node, preserve_emphasis).strip()
        if href and text and text != href:
            return f"{href}[{text}]"
        return href or text

    if tag == "img":
        src = (node.get("src") or "").strip()
        alt = (node.get("alt") or "").strip()
        if src:
            return f"!{src}[{alt}]" if alt else f"!{src}"
        return ""

    if tag == "code":
        return f"`{node.get_text()}`"

    if tag in _EMPHASIS_TAGS:
        inner = _collect_inline(node, preserve_emphasis).strip()
        return f"*{inner}*" if preserve_emphasis else inner

    if tag == "del" or tag == "s":
        return f"~~{_collect_inline(node, preserve_emphasis)}~~"

    # span, abbr, cite, q, mark, sup, sub, etc. — recurse
    return _collect_inline(node, preserve_emphasis)


def _collect_inline(node: Tag, preserve_emphasis: bool) -> str:
    return "".join(_inline(child, preserve_emphasis) for child in node.children)


def _inline_text(node: Tag, preserve_emphasis: bool) -> str:
    """Collect inline text and normalize whitespace (HTML collapsing rules)."""
    raw = _collect_inline(node, preserve_emphasis)
    # Collapse runs of whitespace (except explicit \n from <br>)
    parts = raw.split("\n")
    parts = [re.sub(r"[ \t]+", " ", p).strip() for p in parts]
    return "\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Table rendering
# ---------------------------------------------------------------------------


def _render_table(node: Tag, preserve_emphasis: bool, prefix: str) -> list[str]:
    lines: list[str] = []
    header_done = False

    for tr in node.find_all("tr"):
        cells: list[str] = []
        for cell in tr.find_all(["th", "td"]):
            cells.append(_inline_text(cell, preserve_emphasis))

        if not cells:
            continue

        lines.append(f"{prefix}| " + " | ".join(cells) + " |")
        # Emit separator after first row (treat as header)
        if not header_done:
            lines.append(f"{prefix}|---|")
            header_done = True

    return lines


# ---------------------------------------------------------------------------
# List rendering
# ---------------------------------------------------------------------------


def _render_list(node: Tag, ordered: bool, preserve_emphasis: bool, prefix: str) -> list[str]:
    lines: list[str] = []
    counter = 1
    for child in node.children:
        if not isinstance(child, Tag) or child.name.lower() != "li":
            continue
        lines.extend(_render_li(child, ordered, counter, preserve_emphasis, prefix))
        if ordered:
            counter += 1
    return lines


def _render_li(
    node: Tag,
    ordered: bool,
    index: int,
    preserve_emphasis: bool,
    prefix: str,
) -> list[str]:
    bullet = f"{index})" if ordered else "-"
    lines: list[str] = []
    first_text = True

    for child in node.children:
        if isinstance(child, NavigableString):
            text = re.sub(r"[ \t]+", " ", str(child)).strip()
            if text and first_text:
                lines.append(f"{prefix}{bullet} {text}")
                first_text = False
            continue

        tag = child.name.lower()

        if tag in ("ul", "ol") :
            sub_ordered = tag == "ol"
            lines.extend(_render_list(child, sub_ordered, preserve_emphasis, prefix + "  "))

        elif tag in _HEADING_LEVEL:
            # heading inside li — unlikely but handle
            level = _HEADING_LEVEL[tag]
            text = _inline_text(child, preserve_emphasis)
            lines.append(f"{prefix}  {'=' * level} {text}")

        elif tag == "p":
            text = _inline_text(child, preserve_emphasis)
            if text:
                if first_text:
                    lines.append(f"{prefix}{bullet} {text}")
                    first_text = False
                else:
                    for line in text.split("\n"):
                        lines.append(f"{prefix}  {line}")

        elif tag in _STRIP_TAGS:
            pass

        else:
            # inline content mixed directly in <li>
            text = _inline_text(child, preserve_emphasis)
            if text and first_text:
                lines.append(f"{prefix}{bullet} {text}")
                first_text = False
            elif text:
                lines.append(f"{prefix}  {text}")

    # li with no recognisable children — emit empty bullet
    if first_text:
        text = re.sub(r"\s+", " ", node.get_text()).strip()
        if text:
            lines.append(f"{prefix}{bullet} {text}")

    return lines


# ---------------------------------------------------------------------------
# Block rendering
# ---------------------------------------------------------------------------


def _render_block(node: Tag | NavigableString, preserve_emphasis: bool, prefix: str) -> list[str]:
    """Render a DOM node to a list of MLite output lines."""
    if isinstance(node, (NavigableString, Comment)):
        # Bare text at block level — emit as paragraph if non-empty
        text = re.sub(r"\s+", " ", str(node)).strip()
        if text and not isinstance(node, Comment):
            return [f"{prefix}{text}"]
        return []

    tag = (node.name or "").lower()

    if tag in _STRIP_TAGS:
        return []

    # Headings
    if tag in _HEADING_LEVEL:
        level = _HEADING_LEVEL[tag]
        text = _inline_text(node, preserve_emphasis)
        if text:
            return [f"{prefix}{'=' * level} {text}"]
        return []

    # Paragraph
    if tag == "p":
        text = _inline_text(node, preserve_emphasis)
        if text:
            return [f"{prefix}{line}" for line in text.split("\n")]
        return []

    # Code block
    if tag == "pre":
        code_tag = node.find("code")
        target = code_tag if code_tag else node
        lang = ""
        if code_tag:
            for cls in code_tag.get("class") or []:
                if cls.startswith("language-"):
                    lang = cls[9:]
                    break
                if cls.startswith("lang-"):
                    lang = cls[5:]
                    break
        code = target.get_text().rstrip("\n")
        lines = [f"{prefix}`{lang}"]
        lines.extend(f"{prefix}{line}" for line in code.split("\n"))
        lines.append(f"{prefix}`")
        return lines

    # Horizontal rule
    if tag == "hr":
        return [f"{prefix}---"]

    # Lists
    if tag in ("ul", "ol"):
        return _render_list(node, tag == "ol", preserve_emphasis, prefix)

    # Blockquote
    if tag == "blockquote":
        depth = prefix.count(">") + 1
        inner_prefix = ">" * depth + " "
        lines: list[str] = []
        for child in node.children:
            lines.extend(_render_block(child, preserve_emphasis, inner_prefix))
        return lines

    # Table
    if tag == "table":
        return _render_table(node, preserve_emphasis, prefix)

    # Containers — recurse into children
    if tag in _CONTAINERS or tag in ("li",):
        lines = []
        for child in node.children:
            lines.extend(_render_block(child, preserve_emphasis, prefix))
        return lines

    # Fallback: treat as inline content (e.g. <span>, <a>, <img> at block level)
    # Use _inline on the node itself so link/image syntax is preserved.
    text = _inline(node, preserve_emphasis).strip()
    if text:
        return [f"{prefix}{text}"]
    return []


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def html_to_mlite(source: str, *, preserve_emphasis: bool = True) -> str:
    """Convert an HTML string to MLite format.

    Args:
        source: Raw HTML text.
        preserve_emphasis: If True, emit *text* for bold/italic instead of
            stripping emphasis markers.

    Returns:
        MLite-formatted string, terminated by a single newline.
    """
    soup = BeautifulSoup(source, "html.parser")

    # Strip noise before walking
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    root = soup.body or soup
    lines: list[str] = []
    for child in root.children:
        lines.extend(_render_block(child, preserve_emphasis, ""))

    # Drop blank lines (MLite uses single newline, no blank separators)
    lines = [ln for ln in lines if ln.strip()]
    return "\n".join(lines).strip() + "\n"


HTML_ADAPTER = FormatAdapter(
    source_mime="text/html",
    source_extensions=["html", "htm"],
    to_mlite=html_to_mlite,
    from_mlite=None,  # lossy: attributes, scripts, styles all discarded
)
