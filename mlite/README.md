# MLite

**`text/mlite`** — an AI-first, token-efficient text transmission format.

MLite is not an authoring language.
It is a _wire format_: a conversion target that delivers structured documents to LLM context windows with 15–35% fewer tokens than the Markdown source.
The same content, less context budget consumed.

---

## How it works

A Markdown document is parsed to an AST and re-emitted with every structural token earning its place:

| Construct       | Markdown                     | MLite                        | Savings          |
| --------------- | ---------------------------- | ---------------------------- | ---------------- |
| H2 heading      | `## Installation`            | `== Installation`            | 1 token          |
| Code fence      | ` ``` ` open + ` ``` ` close | `` ` `` open + `` ` `` close | 4+ tokens/block  |
| Bold span       | `**text**`                   | `*text*`                     | 2 tokens/span    |
| Labeled link    | `[label](url)`               | `url[label]`                 | 2 tokens/link    |
| Block separator | blank line                   | no blank line                | 1 token/boundary |

**Markdown input:**

````
## Installation

Run **one command** to install:

    ```python
    pip install mlite
    ```

See [the docs](https://mlite.dev) for more.
````

**MLite output** (18% fewer tokens for this snippet):

```
== Installation
Run one command to install:
`python
pip install mlite
`
See https://mlite.dev[the docs] for more.
```

Full syntax reference: [`SPEC.md`](SPEC.md).

---

## Token savings — corpus results

Measured with the `cl100k_base` tokeniser (GPT-4 / Claude equivalent) across **125 real-world Markdown files** totalling ~490K tokens.

| Metric                 | Value                  |
| ---------------------- | ---------------------- |
| Aggregate savings      | **17.9%**              |
| Corpus size            | 125 files, 490K tokens |
| Best case              | trpc/trpc README — 83% |
| Typical range          | 10–35%                 |
| Plain-text / RST floor | ~3–5%                  |

Savings by document type, per spec targets:

| Document type               | Spec target | Corpus result |
| --------------------------- | ----------- | ------------- |
| Prose + headings + lists    | 12–18%      | ~10–20% ✓     |
| API docs (code-heavy)       | 20–30%      | ~15–35% ✓     |
| Badge/link-heavy READMEs    | —           | 40–83%        |
| RST/plain-text (off-target) | —           | 3–5%          |

The primary savings drivers in order of impact: blank-line elimination, code-fence compression, link-syntax inversion, and emphasis normalisation (bold/italic both collapse to `*text*`).
See the [corpus test](tests/test_corpus.py) for the full per-file breakdown.

To reproduce:

```bash
pytest tests/test_corpus.py -v -s
```

---

## LLM comprehension quality

Token savings only matter if an LLM reading MLite understands the content as well as it would from the original Markdown.
We measure this with a Q&A agreement eval: for each document we ask Claude the same factual questions with the Markdown source and with the MLite output, then use a judge model to score whether the answers agree.

**Fixture results (25 questions, 9 structural element types):**

| document      | questions | agreement | token savings | score     |
| ------------- | --------- | --------- | ------------- | --------- |
| basic.md      | 5         | 100%      | 2.4%          | 1.024     |
| code_heavy.md | 5         | 100%      | 5.3%          | 1.053     |
| emphasis.md   | 5         | 100%      | 22.2%         | 1.222     |
| nested.md     | 5         | 100%      | 2.2%          | 1.022     |
| table.md      | 5         | 100%      | 20.7%         | 1.207     |
| **mean**      | **25**    | **100%**  | **9.4%**      | **1.106** |

Agreement is 100% across every structural element — headings, paragraphs, lists, code blocks, inline code, tables, links, blockquotes, emphasis, and strikethrough.

The **score** column is `agreement_rate × (1 + token_savings_pct / 100)`.
A score above 1.0 means the format delivers equal comprehension at lower cost.
Every fixture scores above 1.0.

**How the eval works:**

1. Each document has a companion `*.qa.json` file with factual questions and canonical answers.
2. Claude (`claude-haiku-4-5`) answers each question twice — once from the Markdown source, once from the MLite output.
3. A judge model compares the two answers and scores agreement.
4. Answers agree if they convey the same factual content regardless of wording or markdown notation.

To run the eval yourself:

```bash
ANTHROPIC_API_KEY=<key> python scripts/run_eval.py --fixtures
```

See [`docs/eval-baseline.md`](docs/eval-baseline.md) for the full baseline record and [`docs/eval-design.md`](docs/eval-design.md) for methodology details.

---

## Installation

```bash
uv pip install -e ".[dev]"
```

Requires Python 3.11+.
Runtime dependencies: `mistune`, `beautifulsoup4`, `fastmcp`, `httpx`, `click`.

---

## Usage

**Python API:**

```python
from mlite.adapters.markdown import markdown_to_mlite

mlite_text = markdown_to_mlite(source)

# preserve bold/italic as *text* instead of stripping
mlite_text = markdown_to_mlite(source, preserve_emphasis=True)
```

**Via the registry (dispatch by file extension or MIME type):**

```python
from mlite.adapters import get_registry

registry = get_registry()
adapter = registry.for_path("README.md")       # by extension
adapter = registry.for_mime("text/markdown")   # by MIME type

mlite_text = adapter.to_mlite(source)
```

**CLI** _(Phase 2 — coming soon)_:

```bash
mlite README.md
mlite README.md --stats          # print token savings to stderr
mlite README.md --preserve-emphasis
```

**MCP server** _(Phase 2 — coming soon)_:

```bash
mlite-mcp   # starts a FastMCP server with read_file and read_url tools
```

---

## Development

```bash
# run unit tests
pytest tests/test_markdown.py -v

# run corpus stress test (125 real-world files, ~2s)
pytest tests/test_corpus.py -v -s

# run everything
pytest

# skip corpus tests during fast iteration
pytest -m "not corpus"

# refresh the corpus (re-downloads missing files)
python scripts/fetch_corpus.py
```

The corpus files are committed to the repo under `tests/corpus/`.
Run `python scripts/fetch_corpus.py --force` to re-download all of them.

---

## Project structure

```
mlite/
├── SPEC.md                   format specification (source of truth)
├── CLAUDE.md                 implementation guide for Claude Code
├── pyproject.toml
├── scripts/
│   ├── fetch_corpus.py       downloads real-world Markdown corpus
│   └── corpus_sources.json   135 source URLs with fallbacks
├── mlite/
│   ├── adapters/
│   │   ├── base.py           FormatAdapter dataclass
│   │   ├── __init__.py       AdapterRegistry
│   │   └── markdown.py       Markdown → MLite converter (mistune AST)
│   ├── cli.py                click CLI (Phase 2)
│   └── mcp_server.py         FastMCP server (Phase 2)
└── tests/
    ├── fixtures/             golden-file regression tests (.md + .mlt pairs)
    ├── corpus/               125 committed real-world Markdown files
    ├── test_markdown.py      30 unit + regression tests
    └── test_corpus.py        corpus stress test with savings reporting
```

## Implementation status

| Phase | Deliverable                        | Status     |
| ----- | ---------------------------------- | ---------- |
| 1     | `FormatAdapter`, `AdapterRegistry` | ✓ complete |
| 1     | `MarkdownAdapter` (mistune AST)    | ✓ complete |
| 1     | Golden-file regression tests       | ✓ complete |
| 1     | Corpus stress test (125 files)     | ✓ complete |
| 2     | `mlite` CLI with `--stats`         | planned    |
| 2     | `mlite-mcp` FastMCP server         | planned    |
| 3     | `HTMLAdapter` (BeautifulSoup4)     | planned    |
| 4     | Python code adapter                | planned    |
