# MLite — Project Context for Claude Code

## What This Is

You are implementing **MLite** (`text/mlite`), an AI-first token-efficient text transmission
format. This is not a new authoring language — it is a conversion target: a wire format for
delivering structured documents to LLM context windows with 15–35% fewer tokens than the
source format.

The full specification is in `SPEC.md`. Read it before writing any code. The decisions in it
are final for v0.1 unless a concrete implementation problem forces a revision, in which case
update the spec first and the code second.

---

## Architecture

Three deliverables from one codebase:

```
mlite/                    Python library (the converter core)
mlite CLI                 Thin click wrapper around the library
mlite-mcp                 FastMCP server exposing read_file + read_url tools
```

```
mlite/
├── CLAUDE.md             (this file)
├── SPEC.md               (full format specification — source of truth)
├── pyproject.toml
├── mlite/
│   ├── __init__.py
│   ├── adapters/
│   │   ├── __init__.py   AdapterRegistry — dispatches on extension or MIME type
│   │   ├── base.py       FormatAdapter dataclass / abstract base
│   │   ├── markdown.py   MarkdownAdapter (priority 1 — implement first)
│   │   └── html.py       HTMLAdapter (priority 2)
│   ├── parser.py         MLite → AST (for round-trip validation, lower priority)
│   ├── cli.py            click entrypoint with --stats flag
│   └── mcp_server.py     FastMCP server
└── tests/
    ├── fixtures/          .md and .html source files for regression testing
    ├── test_markdown.py
    ├── test_html.py
    └── test_cli.py
```

---

## Key Design Decisions (Do Not Re-Litigate Without Reading SPEC.md §10)

**Headings:** `=` sigil, counted per level (`==` = H2, `===` = H3). NOT indentation-based.
Indentation for headings is a candidate for v0.2 via `%heading-style indent` directive only.

**Code blocks:** Single backtick opener (`` `lang ``), single backtick closer on its own line.
Closing delimiter is explicit — NOT indentation-based. This is non-negotiable; indentation
breaks code content.

**Emphasis:** Stripped by default. Preserved as `*text*` only with `preserve_emphasis=True`.

**Links:** Inverted from Markdown — URL first, label optional in brackets: `https://url[label]`

**Block separation:** Single newline. Blank lines are not meaningful.

**Ordered lists:** `)` not `.` — avoids ambiguity with sentence-ending periods.

These decisions are documented with full rationale in SPEC.md §10 (Alternatives Considered).

---

## Implementation Order

### Phase 1 — Core (implement this first)

1. `mlite/adapters/base.py` — `FormatAdapter` dataclass
2. `mlite/adapters/__init__.py` — `AdapterRegistry` with `for_path()` and `for_mime()`
3. `mlite/adapters/markdown.py` — `MarkdownAdapter`
   - Use `mistune` or `markdown-it-py` to parse to AST, then walk the AST to emit MLite
   - Do NOT use regex on Markdown source — the AST walk is the only correct approach
   - All block types from SPEC.md §3.2 must be covered
4. `tests/test_markdown.py` — round-trip fixtures
5. `mlite/cli.py` — `mlite` command with `--stats` (tiktoken token delta to stderr)

### Phase 2 — MCP Server

6. `mlite/mcp_server.py` — FastMCP server with `read_file` and `read_url` tools
7. `pyproject.toml` — package entry points for both `mlite` CLI and `mlite-mcp` server

### Phase 3 — HTML Adapter

8. `mlite/adapters/html.py` — `HTMLAdapter` using `beautifulsoup4`
9. `tests/test_html.py`

### Phase 4 — Code Adapters (Python first)

10. `mlite/adapters/python.py` — envelope pattern with optional docstring extraction
11. Extend `AdapterRegistry` with code adapter registrations

---

## Dependencies

```toml
# Runtime
mistune = ">=3.0"          # Markdown → AST
beautifulsoup4 = ">=4.12"  # HTML parsing
fastmcp = ">=0.1"          # MCP server
httpx = ">=0.27"           # read_url HTTP client
click = ">=8.0"            # CLI

# Optional / dev
tiktoken                   # --stats token counting (soft dependency, import-guarded)
pytest
pytest-cov
```

Use `uv` for all package management. The project should be installable as:
```bash
uv pip install -e ".[dev]"
mlite --help
mlite-mcp  # starts the MCP server
```

---

## Code Style

- Python 3.11+
- Functional where practical — prefer pure functions over stateful classes except at
  the registry/adapter boundary where the dataclass pattern is correct
- No business logic in `cli.py` or `mcp_server.py` — they are thin wrappers only
- Type annotations on all public functions
- Adapters must be independently importable — no circular deps
- `AdapterRegistry` is the only global state; it should be lazily instantiated

---

## The MCP Tool Descriptions Matter

The `read_file` and `read_url` tool descriptions in `mcp_server.py` are not documentation —
they are the steering mechanism that causes Claude to prefer these tools over the built-in
`Read` tool for supported file types. Write them carefully. The description should make clear:
- Which file types trigger conversion
- That the output is MLite (token-efficient)
- That unsupported types pass through verbatim

---

## Testing Philosophy

Regression tests should use real fixture files in `tests/fixtures/`. At minimum:

- `basic.md` — headings, paragraphs, lists, a code block, a link
- `code_heavy.md` — multiple code blocks in multiple languages  
- `table.md` — tables with various column counts
- `nested.md` — nested lists, nested blockquotes
- `emphasis.md` — bold, italic, inline code (to verify stripping behavior)

Each fixture should have a corresponding `.mlt` golden output file. Tests assert exact
match against the golden file. When the converter behavior changes intentionally, update
the golden files explicitly — do not auto-update them.

The `--stats` CLI flag uses tiktoken. Token savings for `basic.md` should be ≥10%.
If it is not, something is wrong with the conversion.

---

## Claude Code MCP Registration

Once `mlite-mcp` is installable, register it with:

```json
{
  "mlite": {
    "command": "uvx",
    "args": ["mlite-mcp"]
  }
}
```

At `~/.claude/mcp_servers.json` for user-level availability, or `.claude/mcp_servers.json`
for project-level.

---

## Open Questions (Do Not Block On These — Note and Continue)

From SPEC.md §11, the ones most likely to surface during implementation:

1. **Emphasis round-trip** — collapsing bold+italic to `*text*` means round-trip is ambiguous.
   For v0.1 this is acceptable. Note it in the adapter but do not solve it yet.

2. **Anchor IDs on headings** — reserve `= Heading {#anchor}` syntax in the parser but do
   not emit it from the Markdown adapter yet. The Markdown spec allows `{#id}` in some
   parsers but it is not standard CommonMark.

3. **Math blocks** — treat as typed code block for now: `` `latex ``. Revisit in v0.2.

4. **Tokenizer variance** — `--stats` uses cl100k_base (GPT-4 tokenizer) as a proxy.
   This is good enough for development. Cross-tokenizer analysis is post-v1 work.
