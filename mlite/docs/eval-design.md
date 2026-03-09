# MLite Quality Evaluation Framework

## 1. Purpose

MLite reduces token count, but token count is not the product.
The product is _equivalent LLM comprehension at lower cost_.
This document specifies a framework for measuring both dimensions together so that
converter changes can be evaluated against a concrete quality/efficiency trade-off curve.

## 2. What We Are Measuring

### 2.1 Efficiency (already implemented)

Token delta between source and MLite output, measured with tiktoken `cl100k_base`.
Reported by `mlite --stats`.
Target: ≥15% reduction on real-world corpus.

### 2.2 Semantic Fidelity

The degree to which an LLM answering questions from MLite produces the same answers
as it would from the original Markdown.

Operationalised as: **answer agreement rate** across a fixed Q&A benchmark.

We do _not_ measure whether the answers are correct in an absolute sense — only whether
the two formats yield the same answer.
Agreement with the Markdown answer is the gold standard because Markdown is the
established, lossless source of truth.

### 2.3 The Combined Metric

```
score = agreement_rate × (1 + efficiency_bonus)
```

Where `efficiency_bonus = token_savings_pct / 100` (e.g. 0.25 for 25% savings).

This rewards formats that maintain quality while saving tokens.
A format that saves 25% tokens with 100% agreement scores 1.25.
A format that saves 40% tokens but drops to 80% agreement scores 1.12 — worse.

## 3. Dataset

### 3.1 Sources

Two tiers:

**Tier 1 — Fixtures** (`tests/fixtures/`)
Five hand-crafted files covering specific structural features:
`basic.md`, `code_heavy.md`, `table.md`, `nested.md`, `emphasis.md`.
These are used for targeted regression: if a specific feature regresses, a fixture
test will show which one.

**Tier 2 — Corpus** (`tests/corpus/`)
~80 real-world README files from popular open-source projects, fetched by
`scripts/fetch_corpus.py`.
These are used for aggregate statistics: distribution of token savings and agreement
rates across diverse, real documents.

### 3.2 Q&A File Format

Each evaluated document `foo.md` has a companion `foo.qa.json`:

```json
[
  {
    "id": "basic-001",
    "question": "What command installs mlite?",
    "answer": "pip install mlite",
    "type": "factual",
    "source_element": "code_block"
  },
  {
    "id": "basic-002",
    "question": "What file formats does mlite support?",
    "answer": "Markdown and HTML",
    "type": "list",
    "source_element": "list"
  }
]
```

Fields:

| Field            | Description                                                                                       |
| ---------------- | ------------------------------------------------------------------------------------------------- |
| `id`             | Unique across the full dataset. `<fixture>-<seq>`.                                                |
| `question`       | Natural language question answerable from the document alone.                                     |
| `answer`         | Canonical answer extracted from Markdown source.                                                  |
| `type`           | `factual` \| `list` \| `code` \| `table` \| `emphasis` — for per-category breakdowns.             |
| `source_element` | The MLite element type the answer comes from. Identifies which converter features are under test. |

### 3.3 Q&A Generation

For Tier 1 fixtures: hand-authored.
One question per distinct structural element in the document.
Minimum: 3 questions per fixture; maximum: 10.

For Tier 2 corpus: LLM-generated, then human-spot-checked.
Use `scripts/generate_qa.py` (specified below) to produce candidates.
Review and prune: reject questions whose answers require inference or external knowledge.
Accept only questions with a single unambiguous answer extractable from the document.

Target: 5 questions per corpus file × 80 files = ~400 corpus Q&A pairs.

## 4. Evaluation Pipeline

### 4.1 Overview

```
for each document:
  md_answers  = ask_llm(document_as_markdown, questions)
  mlt_answers = ask_llm(document_as_mlite,    questions)
  agreement   = judge(md_answers, mlt_answers, questions)

report:
  per-document: agreement_rate, token_delta, combined_score
  aggregate:    mean ± stddev of each, broken down by type
```

### 4.2 LLM Call Contract

Each question is a separate API call with the document in the system prompt:

```
system: "Answer the following question using only the provided document.
         Be concise. If the answer is not in the document, say 'not found'."
user:   "<question>"
```

The document text fills the system prompt without additional framing.
Model: `claude-haiku-4-5-20251001` (cheapest, fast; adequate for factual extraction).
Temperature: 0 (deterministic).
Max tokens: 256.

### 4.3 Judge

A second LLM call scores each `(md_answer, mlt_answer, question)` triple:

```
system: "You are a grader. Given a reference answer and a candidate answer to the
         same question, output a JSON object: {"agree": true|false, "reason": "..."}.
         Answers agree if they convey the same information, even with different wording."
user: |
  Question: <question>
  Reference: <md_answer>
  Candidate: <mlt_answer>
```

Model: `claude-haiku-4-5-20251001`.
Temperature: 0.
Parse `{"agree": bool}` from response; if parse fails, log as `agree: false`.

This two-LLM design separates the extraction step from the comparison step and avoids
position bias in a single prompt that sees both answers.

### 4.4 Caching

All LLM responses are cached to `eval_cache/<sha256_of_prompt>.json`.
Re-running the eval suite after a converter change only re-calls the MLite leg.
The Markdown leg is stable unless the source document changes.

Cache invalidation: keyed on `(model_id, system_prompt_hash, user_prompt_hash)`.

## 5. File Layout

```
mlite/
├── docs/
│   └── eval-design.md          (this file)
├── scripts/
│   ├── corpus_sources.json      (already exists)
│   ├── fetch_corpus.py          (already exists)
│   ├── generate_qa.py           (new — LLM-based Q&A generation for corpus)
│   └── run_eval.py              (new — full eval pipeline runner)
├── tests/
│   ├── fixtures/
│   │   ├── basic.md
│   │   ├── basic.qa.json        (new — hand-authored)
│   │   ├── code_heavy.md
│   │   ├── code_heavy.qa.json   (new)
│   │   ├── table.md
│   │   ├── table.qa.json        (new)
│   │   ├── nested.md
│   │   ├── nested.qa.json       (new)
│   │   ├── emphasis.md
│   │   └── emphasis.qa.json     (new)
│   └── corpus/
│       ├── <repo>.md            (already exists, ~80 files)
│       └── <repo>.qa.json       (new — LLM-generated, spot-checked)
└── eval_cache/                  (gitignored — LLM response cache)
    └── <sha256>.json
```

## 6. Script Specifications

### 6.1 `scripts/generate_qa.py`

Inputs: one or more `.md` file paths.
Output: writes `<file>.qa.json` alongside each input.

```
usage: generate_qa.py [--model MODEL] [--n INT] FILE [FILE ...]
```

Algorithm:

1. For each file, convert to MLite and compute token delta.
   Skip files where MLite output is empty or conversion fails.
2. Call Claude with the Markdown text and prompt it to produce N Q&A pairs as JSON.
3. Validate schema, write `<file>.qa.json`.
4. Print summary: files processed, total Q&A pairs generated, failures.

Prompt instructs the model to:

- Cover different structural elements (headings, lists, code, tables, links).
- Prefer factual questions with single-word or short-phrase answers.
- Avoid questions that require inference or external knowledge.
- Output a JSON array matching the schema in §3.2.

### 6.2 `scripts/run_eval.py`

Inputs: one or more `.qa.json` file paths (or `--fixtures` / `--corpus` shorthand flags).

```
usage: run_eval.py [--model MODEL] [--no-cache] [--out FILE] [FILE ...]
       run_eval.py --fixtures
       run_eval.py --corpus
       run_eval.py --all
```

Outputs:

- `--out FILE` (default: `eval_results.jsonl`): one JSON line per Q&A item with full detail.
- A summary table to stdout.

Summary table columns:

```
document              questions  agreement  token_delta  score
basic.md              5          100.0%     -18.2%       1.182
table.md              7           85.7%     -24.1%       1.063
...
TOTAL / MEAN          412         96.3%     -22.4%       1.181
```

Exit code: 0 if mean agreement ≥ 90%, else 1.
This allows `run_eval.py --fixtures` as a CI gate on the fixture set.

## 7. What the Results Mean

### 7.1 Per-Element Breakdown

Because each Q&A item has a `source_element` field, we can report:

```
element         questions  agreement  interpretation
heading         48         100%       heading conversion is lossless
code_block      61          98%       one language label lost
table           55          87%       some table cell precision lost  ← investigate
list            72          96%
link            38          89%       link label stripping causes losses
```

A low agreement rate for a specific element type is a direct signal to inspect
the converter for that element.

### 7.2 The Emphasis Case

Questions of `type: emphasis` specifically target `**WARNING:**`-style content.
We expect slight degradation here because emphasis is stripped by default.
If degradation exceeds 5%, consider promoting frequently-prefixed bold phrases
(e.g. `**Note:**`, `**Warning:**`, `**Important:**`) to preserved output.

### 7.3 Regression Threshold

On the fixture set: agreement must be ≥95% per fixture file and ≥98% overall.
These are tight because fixtures are hand-crafted for structural coverage.

On the corpus set: agreement must be ≥90% overall.
Individual corpus files may dip lower (documents vary in structure quality).

## 8. Implementation Order

1. Hand-author `tests/fixtures/*.qa.json` (5 files × ~5 questions = ~25 items).
2. Implement `scripts/run_eval.py` (core pipeline, caching, summary table).
3. Run against fixtures to establish baseline.
4. Implement `scripts/generate_qa.py`.
5. Generate and spot-check corpus Q&A for 10–20 representative corpus files.
6. Run full corpus eval; record baseline in `docs/eval-baseline.md`.
7. Add `run_eval.py --fixtures` as an optional CI step (not blocking by default — requires API key).

## 9. Out of Scope for v0.1

- Perplexity measurement (requires base LM access, not instruction-tuned).
- Embedding similarity (lower signal than Q&A agreement for this use case).
- Cross-tokenizer analysis (tiktoken `cl100k_base` proxy is sufficient for development).
- Automated Q&A spot-checking (manual review of generated Q&A is required).
- Parallel model comparison (single model evaluation is sufficient for format comparison).
