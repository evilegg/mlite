# 🪶 MLite — Feed Your LLM Less, Think More

> **`text/mlite`** — the token-efficient wire format for AI-first document delivery.

Why send 1,000 tokens when 820 will do? 🤔
MLite converts Markdown (and soon HTML, Python, and more) into a compact format purpose-built for LLM context windows — **same content, fewer tokens, lower cost, longer docs**.

---

## ✨ The Big Idea

Every token in a prompt costs money and burns context budget.
Markdown is great for humans — but it's wasteful for machines.
Triple-backtick fences, blank-line separators, `**bold**` wrappers, `[label](url)` link syntax — none of it matters to a model.
MLite strips out every byte that doesn't carry semantic weight.

| Construct       | Markdown                     | MLite                        | Saved            |
| --------------- | ---------------------------- | ---------------------------- | ---------------- |
| H2 heading      | `## Installation`            | `== Installation`            | 1 token          |
| Code fence      | ` ``` ` open + ` ``` ` close | `` ` `` open + `` ` `` close | 4+ tokens/block  |
| Bold span       | `**important**`              | `important`                  | 4 tokens/span    |
| Labeled link    | `[label](url)`               | `url[label]`                 | 2 tokens/link    |
| Block separator | blank line                   | _(none)_                     | 1 token/boundary |

Small wins, everywhere, adding up fast. 🏃

---

## 🔢 Real-World Benchmark

We tested MLite against **125 real-world Markdown files** — READMEs from React, PyTorch, Kubernetes, Rust, LangChain, and 120 more — totalling **~490,000 tokens**.

| Metric               | Result                     |
| -------------------- | -------------------------- |
| 🏆 Aggregate savings | **18.4%**                  |
| 📦 Corpus            | 125 files · 490K tokens    |
| 🚀 Best single file  | trpc/trpc README — **83%** |
| 📊 Typical range     | 10–35%                     |
| 🎯 Spec target       | 15–35% ✅                  |

**Savings by document type:**

| Document type            | Savings |
| ------------------------ | ------- |
| API docs (code-heavy)    | 15–35%  |
| Prose + headings + lists | 10–20%  |
| Badge/link-heavy READMEs | 40–83%  |

Run the benchmark yourself in ~2 seconds:

```bash
pytest mlite/tests/test_corpus.py -v -s
```

---

## 👀 Before & After

**Markdown in:**

````
## Installation

Run **one command** to install:

    ```python
    pip install mlite
    ```

See [the docs](https://mlite.dev) for more.
````

**MLite out** (18% fewer tokens for this snippet 🎉):

```
== Installation
Run one command to install:
`python
pip install mlite
`
See https://mlite.dev[the docs] for more.
```

The full syntax is in [`SPEC.md`](SPEC.md) — it's a short read and everything has a reason.

---

## 🚀 Quick Start

```bash
cd mlite
uv pip install -e ".[dev]"
```

```python
from mlite.adapters.markdown import markdown_to_mlite

with open("README.md") as f:
    compact = markdown_to_mlite(f.read())

# that's it! feed `compact` to your LLM instead
```

Or let the registry pick the right adapter for you:

```python
from mlite.adapters import get_registry

adapter = get_registry().for_path("README.md")
compact = adapter.to_mlite(source)
```

---

## 🗺️ Roadmap

|     | Deliverable                                           | Status      |
| --- | ----------------------------------------------------- | ----------- |
| ✅  | Markdown adapter (mistune AST)                        | **shipped** |
| ✅  | AdapterRegistry (extension + MIME dispatch)           | **shipped** |
| ✅  | 156 tests — unit, golden-file, and 125-file corpus    | **shipped** |
| 🔜  | `mlite` CLI with `--stats` token savings report       | next        |
| 🔜  | `mlite-mcp` FastMCP server (`read_file` + `read_url`) | next        |
| 🔜  | HTML adapter (BeautifulSoup4)                         | planned     |
| 🔜  | Python code adapter (envelope + docstring extraction) | planned     |

---

## 🧪 Development

```bash
cd mlite

# fast unit tests
pytest tests/test_markdown.py -v

# full corpus benchmark with savings table
pytest tests/test_corpus.py -v -s

# everything
pytest

# skip corpus during quick iteration
pytest -m "not corpus"

# refresh the committed corpus from source
python scripts/fetch_corpus.py
```

---

## 📐 Format at a Glance

```
HEADINGS     = H1  == H2  === H3  (up to ======)
CODE BLOCK   `lang\n<content>\n`
INLINE CODE  `code`
UNORDERED    - item  (2-space indent per nesting level)
ORDERED      1) item
BLOCKQUOTE   > text  (>> nested)
LINK         https://url.com[optional label]
IMAGE        !https://url.com[alt text]
TABLE        | col | col |\n|---|\n| val | val |
BREAK        ---
EMPHASIS     stripped by default · preserved as *text* with --preserve-emphasis
```

Full specification with rationale: [`SPEC.md`](SPEC.md) 📖

---

## 📄 License

MIT
