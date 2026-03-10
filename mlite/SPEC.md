# MLite Format Specification

**Version:** 0.1.0
**Status:** Implemented
**MIME Type:** `text/mlite`  
**File Extension:** `.mlt`

---

## 1. Abstract

MLite is an AI-first text serialization format designed to convey structured prose, code, and data with maximum token efficiency for large language model consumption. It is not a replacement for Markdown as an authoring format — it is a transmission format, analogous to the relationship between HTML and its wire-compressed form, or between JSON and MessagePack.

The primary design constraint is: **every byte must earn its place in the context window.** Secondary constraints are linear parseability, lossless round-trip conversion from its source formats, and extensibility to non-Markdown source documents.

---

## 2. Goals and Non-Goals

### Goals

- Reduce token count of structured text by 15–35% versus Markdown source
- Preserve all semantically meaningful structure (headings, lists, code, tables, links)
- Be parseable in a single forward pass with no lookahead
- Support HTTP content negotiation via `Accept: text/mlite`
- Be extensible to other source formats (HTML, Python, JavaScript, Rust, Go, etc.)
- Provide a Claude tool definition for automatic invocation on Markdown content

### Non-Goals

- Human authoring ergonomics (MLite is a machine-generated format)
- Pixel-perfect visual rendering (presentation layer concerns are out of scope)
- Replacing Markdown, reStructuredText, or Org-mode as authoring formats
- Encoding binary content

---

## 3. Core Syntax

### 3.1 Document Model

An MLite document is a sequence of **blocks** separated by a single newline (`\n`). Blocks are not separated by blank lines. Two consecutive newlines are treated identically to one. Block type is determined by the first character(s) of each line.

The document model maps to a flat, prefix-determined tree. Nesting (list items, blockquotes) is expressed via indentation — two spaces per level.

### 3.2 Block Elements

#### 3.2.1 Headings

Headings use `=` sigils. Each additional `=` denotes one level of nesting. The sigil is followed by a single space and the heading text.

```
= Top-level heading        (H1)
== Section heading         (H2)
=== Subsection             (H3)
==== Sub-subsection        (H4)
===== H5
====== H6
```

**Rationale for `=` over `#`:** The `#` sigil is a Markdown artifact and signals to tokenizers "this is Markdown." The `=` sigil is borrowed from Org-mode, is visually clean, and tokenizes as a single character per level rather than as punctuation clusters.

#### 3.2.2 Paragraphs

Bare lines of text not beginning with a recognized sigil are paragraph content. Consecutive bare lines are joined as a single paragraph. A paragraph ends when a block sigil is encountered or the document ends.

```
This is a paragraph. It may span
multiple lines and is joined on parse.
```

#### 3.2.3 Code Blocks

Code blocks use a single backtick as both opener and closer. The opener is followed immediately (no space) by the language identifier. The closing backtick appears alone on its own line.

```
`python
def hello():
    return "world"
`
```

**Savings versus Markdown:** Eliminates one full ` ``` ` line (the closing fence), saving 4+ tokens per code block. The opening ` ``` ` is collapsed from 3 characters to 1.

**Inline code** retains the single-backtick Markdown convention: `` `identifier` ``

#### 3.2.4 Lists

Unordered list items use `- ` (hyphen-space), identical to Markdown. Ordered list items use `N) ` (number, close-paren, space). Nesting is expressed by two-space indentation.

```
- First item
- Second item
  - Nested item
  - Another nested
- Third item

1) First ordered
2) Second ordered
  1) Nested ordered
```

**Rationale for `)` over `.`:** The period in `1. ` is ambiguous with sentence-ending punctuation at the tokenizer level. Close-paren `1)` is unambiguous.

#### 3.2.5 Blockquotes

Blockquotes use `> ` (greater-than, space), identical to Markdown. Nested blockquotes use `>> `, etc.

```
> This is a quoted block.
>> This is a nested quote.
```

#### 3.2.6 Tables

Tables retain Markdown's pipe syntax. The header separator row is collapsed from `| --- | --- |` to `|---|` (a single-cell sentinel signaling "separator follows"). Alignment markers are dropped — alignment is a rendering concern irrelevant to LLM consumption.

```
| Column A | Column B | Column C |
|---|
| val1 | val2 | val3 |
| val4 | val5 | val6 |
```

#### 3.2.7 Thematic Break

A horizontal rule is expressed as `---` alone on a line, identical to Markdown.

#### 3.2.8 Definition Lists

Definition lists use a `::` sigil:

```
:: term
   Definition text here.
:: another term
   Its definition.
```

#### 3.2.9 Admonitions / Callouts

Admonitions use a `! TYPE` prefix followed by indented content. TYPE is a bare word (`note`, `warning`, `tip`, `danger`, etc.):

```
! warning
  This will overwrite your data.
```

### 3.3 Inline Elements

#### 3.3.1 Emphasis

**Strong emphasis (bold)** and _italic_ are **preserved by default** in MLite, normalized to a single-delimiter `*text*` form (collapsed from both `**bold**` and `_italic_`).
This retains the author's emphasis signal while costing 2 tokens per span instead of 4.

**Stripping mode:** With `--no-preserve-emphasis` / `preserve_emphasis=False`, all emphasis markers are stripped and bare text is emitted.
Use this for maximum token savings when emphasis carries no semantic weight.

**Token cost:** Default (preserved) costs 2 tokens per span vs. 0 when stripped.
A 1,000-word document with 20 emphasis spans costs ~40 extra tokens in preserve mode.

**Round-trip ambiguity:** Collapsing bold and italic to the same `*form*` is the single intentional round-trip ambiguity in the base format. See Section 6 for full analysis.

#### 3.3.2 Links

Links invert the Markdown `[label](url)` convention to `url[label]`. The URL appears first (it is the primary semantic payload), followed by an optional bracket-enclosed label.

```
https://example.com
https://example.com[Example Site]
```

Bare URLs (no label) require no delimiters at all.

**Savings versus Markdown:** Eliminates the leading `[`, `](`, `)` tokens. A labeled link drops from 4 structural tokens to 2. A bare URL drops from 2 structural tokens to 0.

#### 3.3.3 Images

Images use `!url[alt text]`. Analogous to links with `!` prefix.

```
!https://example.com/image.png[A diagram of the system]
```

#### 3.3.4 Strikethrough

Retained as `~~text~~`, identical to GitHub Flavored Markdown.

---

## 4. Source Format Extensions

MLite is the canonical _target_ format. The following source formats each have a defined conversion path into MLite. Extensions are registered as format adapters and share the same output grammar.

### 4.1 Extension Architecture

Each adapter implements the interface:

```python
@dataclass
class FormatAdapter:
    source_mime: str           # e.g. "text/html"
    source_extensions: list[str]
    to_mlite: Callable[[str], str]
    from_mlite: Callable[[str], str] | None  # None if conversion is lossy
```

Adapters are registered with a central `AdapterRegistry`. The MLite toolchain resolves the appropriate adapter from file extension, MIME type, or explicit `--from` flag.

### 4.2 HTML Adapter

HTML is the highest-priority secondary source. Conversion maps:

| HTML                             | MLite                |
| -------------------------------- | -------------------- |
| `<h1>…</h1>`                     | `= …`                |
| `<h2>` – `<h6>`                  | `==` – `======`      |
| `<p>…</p>`                       | bare paragraph       |
| `<ul><li>`                       | `- `                 |
| `<ol><li>`                       | `1) `                |
| `<pre><code class="lang">`       | `` `lang ``          |
| `<blockquote>`                   | `> `                 |
| `<a href="url">label</a>`        | `url[label]`         |
| `<img src="url" alt="alt">`      | `!url[alt]`          |
| `<table>`                        | pipe table           |
| `<strong>`, `<em>`, `<b>`, `<i>` | stripped (bare text) |
| `<code>`                         | `` `code` ``         |
| `<hr>`                           | `---`                |

Script and style tags, HTML comments, and `<head>` content are stripped entirely.

### 4.3 Code File Adapters

Code files (Python, JavaScript, Rust, Go, etc.) are not converted _to_ MLite in the document sense. Instead, they are **wrapped** in a structured MLite envelope that preserves the original source verbatim inside a typed code block, with extracted metadata as MLite structure.

**Python example:**

Given `utils.py`, the MLite envelope renders as:

```
= utils.py
`python
<full source content>
`
```

With optional docstring extraction (when `--extract-docs` is enabled):

```
= utils.py
== Module Docstring
Utility functions for data processing.
== Functions
- process_items(items: list) → Processes a list of items.
- filter_empty(seq) → Removes falsy values from a sequence.
== Source
`python
<full source content>
`
```

The same envelope pattern applies to:

| Language                | Adapter Key        | Extraction Capability                               |
| ----------------------- | ------------------ | --------------------------------------------------- |
| Python                  | `text/x-python`    | docstrings, function signatures, class hierarchy    |
| JavaScript / TypeScript | `text/javascript`  | JSDoc comments, exports, function signatures        |
| Rust                    | `text/x-rustsrc`   | doc comments (`///`), `pub` items, module structure |
| Go                      | `text/x-go`        | godoc comments, exported symbols                    |
| C / C++                 | `text/x-csrc`      | header comments, function declarations              |
| Shell                   | `application/x-sh` | comment blocks, function names                      |
| SQL                     | `application/sql`  | table definitions, comments                         |

For all code adapters, the source is preserved verbatim in the code block. The envelope metadata is additive, not a replacement.

### 4.4 Structured Data Adapters

JSON and YAML adapters convert data files into MLite definition lists or tables where the structure is tabular, and code blocks where it is not.

```
! note
  JSON/YAML adapters emit code blocks for non-tabular data to prevent
  lossy structural flattening.
```

---

## 5. Claude Tool Definition

The following tool definition enables Claude sessions to automatically request MLite-formatted content when encountering Markdown or other supported source formats.

```json
{
  "name": "render_as_mlite",
  "description": "Convert a document or code file to MLite format for token-efficient processing. Use this tool whenever you receive a document in Markdown, HTML, or source code format that you will need to reason over extensively. Call it before beginning analysis, summarization, or transformation tasks on large documents. Do not call it for documents shorter than approximately 500 tokens — the overhead is not worthwhile at small sizes.",
  "input_schema": {
    "type": "object",
    "properties": {
      "content": {
        "type": "string",
        "description": "The raw source content to convert."
      },
      "source_format": {
        "type": "string",
        "enum": [
          "markdown",
          "html",
          "python",
          "javascript",
          "typescript",
          "rust",
          "go",
          "c",
          "cpp",
          "shell",
          "sql",
          "json",
          "yaml"
        ],
        "description": "The format of the source content."
      },
      "preserve_emphasis": {
        "type": "boolean",
        "default": true,
        "description": "If true (default), retain emphasis as single-delimiter *text* form. Set to false to strip all emphasis for maximum token savings."
      },
      "extract_docs": {
        "type": "boolean",
        "default": false,
        "description": "For code files only. If true, extract docstrings and signatures as MLite structure above the source block."
      }
    },
    "required": ["content", "source_format"]
  }
}
```

### 5.1 Tool Invocation Guidelines

Claude SHOULD invoke `render_as_mlite` when:

- A Markdown document exceeds ~500 tokens and will be re-read or referenced multiple times in the session
- An HTML page is provided for content extraction or summarization
- A code file is provided for review, explanation, or transformation

Claude SHOULD NOT invoke `render_as_mlite` when:

- The document is short (< ~500 tokens)
- The user has explicitly requested the original format be preserved
- The task is purely syntactic (e.g., "count the headings in this Markdown file")
- The content will only be read once and discarded

### 5.2 System Prompt Snippet

Include the following in system prompts to activate automatic MLite behavior:

```
When you receive documents in Markdown, HTML, or source code formats that you will
reason over extensively, use the render_as_mlite tool to convert them first.
Work from the MLite output for all subsequent reasoning. This reduces your context
consumption and improves your ability to reference document structure.
```

---

## 6. Information Loss Analysis

MLite's design aspires to be lossless for semantic content. The following is an honest accounting of where information is reduced or lost, and the justification for each trade-off.

### 6.1 Intentional Losses (Base Format)

| Element                                   | What is Lost                        | Severity                      | Justification                                                                                                                                     |
| ----------------------------------------- | ----------------------------------- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Bold / strong emphasis                    | Visual weight signal                | Low                           | LLMs derive emphasis from context, not delimiters. No downstream NLP task benefits from `**` markers.                                             |
| Italic emphasis                           | Stylistic distinction               | Low                           | Same as above. Exception: titles of works (e.g., _Moby Dick_) — these should be preserved with `--preserve-emphasis`.                             |
| HTML attributes beyond `href`/`src`/`alt` | `class`, `id`, `data-*`, ARIA roles | Medium                        | Irrelevant to LLM content comprehension. Loss matters if the task is HTML analysis rather than content extraction.                                |
| CSS / `<style>` blocks                    | All styling information             | High (if task is CSS-related) | Out of scope for content extraction. The HTML adapter MUST NOT strip style blocks if `source_format` is `css` or the task is stylesheet analysis. |
| Markdown HTML passthrough                 | Raw inline HTML in `.md` files      | Medium                        | Stripped. If the embedded HTML is structurally meaningful, the document should be processed through the HTML adapter instead.                     |
| Table alignment markers                   | Column alignment                    | Negligible                    | Purely presentational.                                                                                                                            |
| Ordered list start values                 | `start="5"` on `<ol>`               | Low                           | Lost. If exact numbering semantics matter, use `--preserve-list-start`.                                                                           |

### 6.2 Recoverable Losses (`--preserve-emphasis` mode)

| Element         | Recovery Mechanism                                                                                              |
| --------------- | --------------------------------------------------------------------------------------------------------------- |
| Bold / italic   | Collapsed to single `*delimiter*` form; distinguishable from source on round-trip if original form is annotated |
| Nested emphasis | Flattened to single level                                                                                       |

### 6.3 Losses by Adapter Type

**HTML adapter:**

- `id` and `class` attributes on headings (anchor links) — lost. Future versions may encode as `= Heading {#anchor}`.
- `<details>` / `<summary>` — collapsed to paragraph. Future work.
- Embedded `<script>` blocks — stripped. This is intentional and not recoverable.

**Code adapters:**

- No source loss. The code block is the verbatim original.
- Extracted doc metadata is additive, not substitutive.

### 6.4 The Emphasis Trade-Off In Depth

The stripping of bold/italic is the most contested decision in this spec. The argument for stripping:

1. LLMs are trained on vast corpora with inconsistent emphasis usage. The semantic signal of `**word**` vs `word` is weak.
2. Emphasis tokens consume 4 tokens per span (open-open, content, close-close) for bold. A 1,000-word document with 20 bold spans saves 80 tokens — measurable.
3. The format is AI-_first_. Human reading is not a design constraint.

The argument for preserving it (why `--preserve-emphasis` exists):

1. Technical specs and legal documents use emphasis with specific intent (e.g., RFC 2119 keywords are often bolded).
2. Authors of documents like API references may bold return types or parameter names structurally.
3. Round-trippability requires preserving it in some form.

The default is to preserve (`preserve_emphasis=True`).
Use `--no-preserve-emphasis` only when emphasis carries no semantic weight and maximum token savings are the priority.

---

## 7. Token Efficiency Analysis

The following estimates are based on GPT-family tokenizer behavior and are indicative, not guaranteed, for all model tokenizers.

| Document Type                               | Expected Savings                    |
| ------------------------------------------- | ----------------------------------- |
| Prose with headings and lists               | 12–18%                              |
| API documentation (heavy code blocks)       | 20–30%                              |
| HTML pages (news articles, docs sites)      | 30–45%                              |
| Source code files with docstrings           | 5–10% (envelope overhead amortized) |
| Dense table content                         | 8–12%                               |
| Mixed documentation (prose + code + tables) | 18–28%                              |

Primary savings drivers in order of impact:

1. HTML tag stripping (HTML adapter)
2. Code fence closing line elimination
3. Blank line elimination between blocks
4. Link syntax inversion (2 vs 4 structural tokens)
5. Heading sigil reduction (`#` to `=`)
6. Emphasis stripping

---

## 8. HTTP Content Negotiation

### 8.1 MIME Type Registration

MLite registers as `text/mlite`. No IANA registration exists at this draft stage; this is a project-internal type pending adoption.

### 8.2 Accept Header Negotiation

Clients supporting MLite SHOULD include it in their `Accept` header with an appropriate quality factor:

```
Accept: text/mlite;q=0.9, text/html;q=0.8, text/plain;q=0.6
```

Servers supporting MLite MUST:

1. Check for `text/mlite` in the `Accept` header
2. If present and content can be served as MLite, respond with `Content-Type: text/mlite`
3. Include `Vary: Accept` in the response to enable correct caching behavior

### 8.3 Server Implementation Notes

A minimal server-side MLite responder in Python (framework-agnostic):

```python
from mlite import MarkdownAdapter

def negotiate_content(accept_header: str, markdown_source: str) -> tuple[str, str]:
    """Return (content_type, body) based on Accept header."""
    accepts_mlite = "text/mlite" in accept_header
    return (
        ("text/mlite", MarkdownAdapter().to_mlite(markdown_source))
        if accepts_mlite
        else ("text/markdown", markdown_source)
    )
```

### 8.4 Stretch Goal: Middleware Pattern

A WSGI/ASGI middleware that transparently converts Markdown responses:

```python
class MLiteMiddleware:
    """
    Intercepts responses with Content-Type text/markdown and re-encodes
    as text/mlite when the request Accept header permits it.
    """
    def __init__(self, app):
        self.app = app
        self._adapter = MarkdownAdapter()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        accepts_mlite = self._accepts_mlite(scope.get("headers", []))
        if not accepts_mlite:
            return await self.app(scope, receive, send)
        # wrap send to intercept text/markdown responses
        return await self.app(scope, receive, self._make_send(send))
```

Full middleware implementation is deferred to the implementation phase.

---

## 9. Versioning and Extensibility

### 9.1 Format Version Header

MLite documents MAY include a version header as the first line:

```
%mlite 0.1
```

Parsers encountering an unknown version SHOULD warn and attempt best-effort parsing. If no version header is present, parsers assume the latest stable version.

### 9.2 Extension Sigils

The following sigil namespace is reserved for future use:

| Sigil    | Reserved For                                        |
| -------- | --------------------------------------------------- |
| `@`      | Metadata / frontmatter key-value pairs              |
| `%`      | Directives (version, encoding, adapter hints)       |
| `^`      | Footnote definitions                                |
| `[^ref]` | Footnote references (inline)                        |
| `::`     | Definition lists (already allocated, Section 3.2.8) |
| `! TYPE` | Admonitions (already allocated, Section 3.2.9)      |

### 9.3 Frontmatter

Document metadata is expressed using `@key value` directives at the top of the document, before any block content:

```
%mlite 0.1
@title MLite Specification
@author Anthropic
@date 2025-01-01
@source-format markdown
= MLite Format Specification
…
```

### 9.4 Adapter Registration (Future)

The adapter registry will support third-party adapter packages installable as Python packages with the entry point:

```toml
[project.entry-points."mlite.adapters"]
myformat = "mypackage.adapters:MyFormatAdapter"
```

---

## 10. Alternatives Considered

This section documents design paths that were evaluated and rejected, or partially adopted, during the specification process. It exists to prevent re-litigation of settled decisions and to provide context for future contributors who may arrive at the same alternatives independently.

### 10.1 Indentation-Based Hierarchy vs. Sigil Counting

**Proposal:** Replace heading sigil repetition (`=`, `==`, `===`) with a single `=` sigil whose nesting depth is determined by indentation level — analogous to Python's use of indentation to replace explicit block delimiters.

```
= Document Title
  = Introduction
    = Background
    paragraph content here
  = Next Section
```

vs. the current approach:

```
= Document Title
== Introduction
=== Background
paragraph content here
== Next Section
```

**The appeal:** The indentation model is visually cleaner. A single canonical `=` means "heading at this depth" rather than "count my sigils." It aligns with a widely understood programming convention and eliminates the awkward visual asymmetry between `=` and `======`.

**Why it was rejected for the general case:**

The Python indentation model works because Python has unambiguous block-opening sigils — the colon at the end of `def`, `class`, `if`, etc. is a syntactic contract that the next indented block belongs to this line. Without an equivalent contract, a MLite parser cannot distinguish a heading line from a paragraph continuation without lookahead or indentation tracking across lines.

More critically, the proposal breaks down at code blocks, which are the highest-value content in the format. Code content already uses indentation structurally. If MLite uses indentation to close a code block, all code content must be indented one additional level relative to its containing scope:

```
= Top Level
  = Section
    `python
      def process(items):          # artificial extra indent
          return [x for x in items if x]   # and here
    `
```

The consequences are severe:

- Every line of code pays an additional indentation prefix in tokens, directly counteracting the format's primary goal
- Code copied out of an MLite document is broken and requires dedenting before it runs
- Python code nested inside a deeply scoped MLite section would need multiple levels of artificial indentation, corrupting its apparent structure

The single closing backtick is essentially free — one character on one line. It is the correct solution for a delimiter that must survive inside indentation-sensitive content.

**Tokenizer behavior compounds the problem.** LLM tokenizers handle leading whitespace inconsistently. In GPT-family tokenizers, `  def` (two spaces + identifier) often tokenizes as a different sequence than `def` alone. At nesting depths of 3–4 levels, indentation prefixes fragment across token boundaries in ways that are difficult to predict and may erode the savings the format is designed to deliver. Sigil-based structure keeps the structural marker at column 0 on every line, where tokenization behavior is predictable.

**LLM generation reliability** is a further concern. When an LLM generates MLite, indentation-based structure requires the model to maintain an implicit depth counter as hidden state across lines. Sigil-based structure is locally self-describing: each line encodes its own nesting level without reference to prior lines. This is meaningfully more reliable for generation, and generation reliability matters if MLite is used as an output format (e.g., a model summarizing a document into MLite).

**What was partially adopted:** The core insight — that a single `=` sigil is cleaner than sigil counting — is valid and worth revisiting for a future version. A hybrid that applies indentation-based depth _only to headings_ (which are short, rarely nest past 3 levels, and never contain code) would capture the readability benefit at minimal tokenization cost. This is deferred to a post-v1 consideration. For v0.1, sigil counting is retained for its self-describing, generation-friendly properties.

**Decision:** Sigil counting retained for v0.1. Single-sigil + indentation for headings deferred as a candidate for v0.2 behind a `%heading-style indent` directive, allowing both modes to coexist during evaluation.

---

### 10.2 AST / JSON Serialization

**Proposal:** Rather than a text format, represent documents as a JSON AST — the canonical intermediate representation used by most Markdown parsers (e.g., `commonmark`, `pandoc`).

**Why it was rejected:** JSON AST representations are significantly _more_ token-intensive than their source Markdown, not less. A short paragraph and heading in Markdown AST form:

```json
{
  "type": "document",
  "children": [
    {
      "type": "heading",
      "depth": 2,
      "children": [{ "type": "text", "value": "Getting Started" }]
    },
    {
      "type": "paragraph",
      "children": [{ "type": "text", "value": "Install the package." }]
    }
  ]
}
```

This is 3–5× the token count of the source. JSON is the right intermediate format for programmatic transformation pipelines; it is the wrong format for context window transmission.

---

### 10.3 Stripping to Plain Text

**Proposal:** The most token-efficient representation is plain text with all structure removed. Strip headings, list markers, code fences, and all delimiters.

**Why it was rejected:** This approach conflates token efficiency with information destruction. Structure is meaning. A heading is not decoration — it scopes everything that follows it. A code block boundary is not decoration — it signals a mode switch from prose to executable content. An LLM reading a stripped document must reconstruct structural inference from prose cues alone, which is lower quality reasoning than reading structure that is explicitly encoded. The goal of MLite is _token reduction without information loss_, not maximum compression.

---

### 10.4 XML / SGML Envelope

**Proposal:** Use a lightweight XML-like format with short tag names: `<h>`, `<p>`, `<c>`, `<l>`.

**Why it was rejected:** Any tag-based format has a fundamental asymmetry: opening and closing tags both consume tokens. MLite's block-prefix design means every block pays a small fixed cost at the _start_ of the line and zero cost to close (the next sigil-prefixed line implicitly closes the previous block). For a document with 50 blocks, tag-based formats pay 100 structural token-events; MLite pays 50.

Short XML tags also tokenize poorly. `<h>` is typically 3 tokens (`<`, `h`, `>`). The `=` sigil is 1 token. Closing tags are entirely absent in MLite for prose blocks.

---

### 10.5 Whitespace-Only Compression (Blank Line Removal)

**Proposal:** Keep full Markdown syntax but strip redundant blank lines, which Markdown requires as block separators.

**Why it was not adopted as the sole strategy:** Blank line removal alone yields roughly 3–8% token savings on typical documents — meaningful but insufficient as the primary mechanism. It is, however, adopted as one layer of MLite's savings stack (see Section 7). The point of MLite is that the savings are cumulative across many small wins; no single change is dominant except the HTML tag stripping in the HTML adapter.

---

### 10.6 Closing Delimiter for Code Blocks: Single Backtick vs. Alternatives

**Proposal considered:** Use `|lang` as the code block opener instead of `` `lang ``, since the single backtick is already used for inline code in Markdown. Several alternatives were evaluated:

| Sigil        | Trade-off                                                                                                  |
| ------------ | ---------------------------------------------------------------------------------------------------------- |
| `` `lang ``  | Reuses inline-code sigil; distinguished by being alone on a line with no closing backtick on the same line |
| `\|lang`     | Clean disambiguation, but `\|` is heavily used in table syntax                                             |
| `@code lang` | Verbose; `@` is reserved for frontmatter metadata                                                          |
| `::lang`     | Conflicts with definition list sigil                                                                       |

**Decision:** Single backtick retained. The disambiguation rule is simple: a backtick alone at the start of a line followed by an identifier and newline is a code block opener; a backtick inline within a line is inline code. This is locally unambiguous and consistent with how most tokenizers already handle the character.

---

## 11. Open Questions (v0.2+)

1. **Emphasis round-trip fidelity.** _Resolved for v0.1:_ default is `preserve_emphasis=True`, collapsing `**bold**` and `_italic_` to `*text*`.
   Full disambiguation (separate bold vs italic forms) is deferred to v0.2.

2. **Table complexity.** Multi-line cells and merged cells (colspan/rowspan) have no MLite representation.
   Current behavior: best-effort cell extraction; complex tables fall back to pipe table with flattened content.
   Full solution (HTML passthrough block for unsupported tables) is v0.2 work.

3. **Anchor IDs on headings.** Documentation sites depend on `{#anchor}` heading IDs for deep links.
   The `= Heading {#id}` syntax is reserved but not yet emitted by any adapter.
   Parser should accept it without error (forward-compatible).

4. **Math blocks.** LaTeX math (`$$...$$`) is currently emitted as `` `latex `` typed code blocks.
   A dedicated math block sigil is a v0.2 consideration.

5. **Right-to-left (RTL) text.** No assumptions made about text directionality.
   A `%rtl` directive is reserved for future use.

6. **Streaming.** MLite's block-prefix design is inherently streaming-friendly (each line is self-describing).
   A streaming parser implementation and explicit documentation are deferred to post-v1.

7. **Tokenizer variance.** Token savings estimates assume GPT-family tokenizers (cl100k_base).
   Cross-tokenizer analysis (LLaMA, Mistral, Gemini, Claude) is post-v1 work.

8. **Additional code adapters.** JavaScript/TypeScript, Rust, Go, C, Shell, SQL adapters are specified in §4.3 but not yet implemented.
   The Python adapter (`py_adapter.py`) is the reference implementation for the envelope pattern.

---

## Appendix A: Quick Reference Card

```
HEADINGS     = H1  == H2  === H3  (up to ======)
CODE BLOCK   `lang\n<content>\n`
INLINE CODE  `code`
UNORDERED    - item  (indent 2sp per level)
ORDERED      1) item
BLOCKQUOTE   > text  (>> nested)
LINK         https://url.com[optional label]
IMAGE        !https://url.com[alt text]
TABLE        | col | col |\n|---|\n| val | val |
BREAK        ---
ADMONITION   ! warning\n  indented content
DEFINITION   :: term\n   definition
FRONTMATTER  @key value  (before first block)
DIRECTIVE    %mlite 0.1
EMPHASIS     *text* (default, preserved) or stripped (--no-preserve-emphasis)
```

---

## Appendix B: Comparison Table

| Feature                 | Markdown            | MLite                                 | HTML                       |
| ----------------------- | ------------------- | ------------------------------------- | -------------------------- |
| Heading tokens (H2)     | 3 (`##`, ` `, text) | 3 (`==`, ` `, text)                   | 5+ (`<h2>`, text, `</h2>`) |
| Code fence (open+close) | 2 lines, 6+ tokens  | 2 lines, 2 tokens                     | 2 lines, 15+ tokens        |
| Bold span               | 4 delimiters        | 2 (`*text*`, default) or 0 (stripped) | 2 tags                     |
| Labeled link            | 4 structural tokens | 2 structural tokens                   | 3 structural tokens        |
| Block separator         | 2 newlines          | 1 newline                             | implicit                   |
| Machine-readable        | ✗ (ambiguous)       | ✓                                     | ✓                          |
| AI-first                | ✗                   | ✓                                     | ✗                          |
| Human-authorable        | ✓                   | ✗ (generated)                         | ✗                          |
| HTTP negotiable         | ✗                   | ✓                                     | ✓                          |
| Streamable              | partial             | ✓                                     | partial                    |

---

_End of MLite Specification v0.1.0_
