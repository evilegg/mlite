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
├── README.md
├── pyproject.toml
├── mlite/
│   ├── __init__.py
│   ├── adapters/
│   │   ├── __init__.py   AdapterRegistry — dispatches on extension or MIME type
│   │   ├── base.py       FormatAdapter dataclass / abstract base
│   │   ├── markdown.py   MarkdownAdapter
│   │   ├── html.py       HTMLAdapter (BeautifulSoup4)
│   │   └── py_adapter.py PythonAdapter (envelope + optional doc extraction)
│   ├── cli.py            click entrypoint with --stats flag
│   └── mcp_server.py     FastMCP server (read_file + read_url tools)
├── tests/
│   ├── fixtures/          .md, .html, .py source files + .mlt golden outputs
│   │                      + .qa.json Q&A pairs for eval
│   ├── corpus/            real-world URLs for corpus eval
│   ├── test_markdown.py
│   ├── test_html.py
│   ├── test_python.py
│   ├── test_cli.py
│   ├── test_mcp_server.py
│   └── test_corpus.py     token-savings regression on real URLs
├── scripts/
│   ├── run_eval.py        Q&A agreement eval (fixtures + corpus modes)
│   ├── generate_qa.py     LLM-based Q&A generation for corpus files
│   ├── fetch_corpus.py    Download and cache corpus HTML pages
│   └── corpus_sources.json  Real-world URL list for corpus eval
└── docs/
    ├── eval-design.md     Q&A eval methodology
    └── eval-baseline.md   Baseline results (100% agreement, score 1.106)
```

---

## Key Design Decisions (Do Not Re-Litigate Without Reading SPEC.md §10)

**Headings:** `=` sigil, counted per level (`==` = H2, `===` = H3). NOT indentation-based.
Indentation for headings is a candidate for v0.2 via `%heading-style indent` directive only.

**Code blocks:** Single backtick opener (`` `lang ``), single backtick closer on its own line.
Closing delimiter is explicit — NOT indentation-based. This is non-negotiable; indentation
breaks code content.

**Emphasis:** Preserved as `*text*` by default (`preserve_emphasis=True`).
Strip with `preserve_emphasis=False` / `--no-preserve-emphasis`.

**Links:** Inverted from Markdown — URL first, label optional in brackets: `https://url[label]`

**Block separation:** Single newline. Blank lines are not meaningful.

**Ordered lists:** `)` not `.` — avoids ambiguity with sentence-ending periods.

These decisions are documented with full rationale in SPEC.md §10 (Alternatives Considered).

---

## Implementation Status

All four phases are complete.
230 tests pass.

### Phase 1 — Core ✓

1. `mlite/adapters/base.py` — `FormatAdapter` dataclass
2. `mlite/adapters/__init__.py` — `AdapterRegistry` with `for_path()`, `for_mime()`, lazy `get_registry()`
3. `mlite/adapters/markdown.py` — `MarkdownAdapter` via mistune 3.x AST walk
   - `block_code`, `table`, `strikethrough`, `softbreak` plugins active
   - `preserve_emphasis=True` default (normalized to `*text*`)
4. `tests/test_markdown.py` — 5 golden-file regressions + 25 unit tests
5. `mlite/cli.py` — `mlite` command with `--stats` (tiktoken cl100k_base, delta to stderr)

### Phase 2 — MCP Server ✓

6. `mlite/mcp_server.py` — FastMCP 3.x server, `@mcp.tool()` decorator
   - `read_file(path, preserve_emphasis=True)` — dispatches via `AdapterRegistry`
   - `read_url(url, preserve_emphasis=True)` — sniffs MIME from `Content-Type`, falls back to URL extension
7. `pyproject.toml` — `[project.scripts]` entries for `mlite` and `mlite-mcp`

### Phase 3 — HTML Adapter ✓

8. `mlite/adapters/html.py` — BeautifulSoup4 DOM walker
   - Strips `<script>`, `<style>`, `<head>`, HTML comments
   - Handles headings, paragraphs, code blocks, lists, tables, blockquotes, links, images, hr
9. `tests/test_html.py` — 4 golden-file regressions + 25 unit tests

### Phase 4 — Python Adapter ✓

10. `mlite/adapters/py_adapter.py` — envelope pattern
    - Basic mode: `= filename.py` heading + verbatim `\`python` block
    - `extract_docs=True`: adds `== Module Docstring`, `== Functions`, `== Classes` sections
    - Falls back to basic mode on `SyntaxError` / `ValueError`
11. `tests/test_python.py` — 2 golden-file regressions + 22 unit tests

### Eval Framework ✓

- `scripts/run_eval.py` — SHA256-keyed LLM response cache, extractor+judge two-LLM pattern
- `tests/fixtures/*.qa.json` — 25 hand-authored Q&A pairs across all fixture types
- `docs/eval-baseline.md` — 100% agreement, -9.4% tokens, score 1.106
- `tests/test_corpus.py` — token-savings regression on real-world URLs

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

Regression tests use real fixture files in `tests/fixtures/`.
Current Markdown fixtures: `basic`, `code_heavy`, `table`, `nested`, `emphasis`.
Current HTML fixtures: `basic`, `table`, `emphasis`, `links_images`.
Current Python fixtures: `basic`, `extract_docs`.

Each fixture has a corresponding `.mlt` golden output file.
Tests assert exact match against the golden file.
When converter behavior changes intentionally, update the golden files explicitly — do not auto-update them.

The `--stats` CLI flag uses tiktoken cl100k_base.
Token savings for `basic.md` should be ≥10%.
HTML fixtures should save ≥25%.

### Q&A Eval

`tests/fixtures/*.qa.json` files contain 25 hand-authored question/answer pairs.
`scripts/run_eval.py --fixtures` runs the full eval against these pairs.
Threshold: ≥98% agreement (fixtures), ≥90% (corpus).
Baseline: 100% agreement, score 1.106 (see `docs/eval-baseline.md`).

---

## Claude Code MCP Registration

Register the installed server with:

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

## Open Questions (v0.2+)

1. **Emphasis round-trip** — `*text*` collapses bold and italic; ambiguous on round-trip.
   Acceptable for v0.1.
   Default changed to `preserve_emphasis=True` to reduce information loss.

2. **Anchor IDs on headings** — `= Heading {#anchor}` syntax reserved but not emitted.
   CommonMark does not standardize `{#id}`.

3. **Math blocks** — currently emitted as `` `latex `` typed code blocks. v0.2 consideration.

4. **Tokenizer variance** — `--stats` uses cl100k_base (GPT-4) as a proxy.
   Cross-tokenizer analysis (LLaMA, Gemini, Claude) is post-v1 work.

5. **Additional code adapters** — JavaScript/TypeScript, Rust, Go, etc. not yet implemented.
   The `py_adapter.py` envelope pattern is the reference implementation.
