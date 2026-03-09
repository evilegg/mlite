# MLite Eval Baseline

Recorded 2026-03-09 using fixture Q&A set (25 questions across 5 fixtures).
Model: `claude-haiku-4-5` for extraction and judging.
Conversion mode: `preserve_emphasis=True` (default for eval tooling).

## Results

| document         | questions | agreement  | token_delta | score     |
| ---------------- | --------- | ---------- | ----------- | --------- |
| basic.md         | 5         | 100.0%     | -2.4%       | 1.024     |
| code_heavy.md    | 5         | 100.0%     | -5.3%       | 1.053     |
| emphasis.md      | 5         | 100.0%     | -22.2%      | 1.222     |
| nested.md        | 5         | 100.0%     | -2.2%       | 1.022     |
| table.md         | 5         | 100.0%     | -20.7%      | 1.207     |
| **TOTAL / MEAN** | **25**    | **100.0%** | **-9.4%**   | **1.106** |

## Per-Element Breakdown

| element       | questions | agreement |
| ------------- | --------- | --------- |
| blockquote    | 1         | 100.0%    |
| code_block    | 5         | 100.0%    |
| emphasis      | 2         | 100.0%    |
| heading       | 2         | 100.0%    |
| inline_code   | 2         | 100.0%    |
| link          | 1         | 100.0%    |
| list          | 6         | 100.0%    |
| strikethrough | 1         | 100.0%    |
| table         | 5         | 100.0%    |

## Interpretation

Perfect agreement on all structural elements across all five fixtures.
Token savings range from 2.4% (basic prose) to 22.2% (emphasis-heavy or table-heavy documents).
Combined quality/efficiency score above 1.0 on all documents — MLite delivers equal comprehension at lower cost.

The fixture set is intentionally minimal.
Run `scripts/generate_qa.py` on corpus files and `scripts/run_eval.py --corpus` for broader coverage.

## How to Reproduce

```bash
ANTHROPIC_API_KEY=<key> python scripts/run_eval.py --fixtures
```
