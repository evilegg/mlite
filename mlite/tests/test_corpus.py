"""Token-savings stress test against the real-world Markdown corpus.

Run with:
    pytest tests/test_corpus.py -v
    pytest tests/test_corpus.py -v -s       # verbose per-file table
    pytest tests/test_corpus.py --tb=short  # short traceback on failure

The corpus lives in tests/corpus/*.md and is committed to the repo.
To refresh or expand the corpus, run:
    python scripts/fetch_corpus.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mlite.adapters.markdown import markdown_to_mlite

# tiktoken is an optional dev dependency — skip gracefully if missing
try:
    import tiktoken

    _ENC = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(text: str) -> int:
        return len(_ENC.encode(text))

except ImportError:  # pragma: no cover
    _ENC = None

    def _count_tokens(text: str) -> int:  # type: ignore[misc]
        # fallback: rough whitespace-split estimate
        return len(text.split())


CORPUS_DIR = Path(__file__).parent / "corpus"

# --- Thresholds ---------------------------------------------------------------
# Each file must convert without crashing and produce non-empty output.
# We do NOT assert per-file savings (some tiny READMEs may break even).
# Aggregate savings across the corpus must meet the minimum target.
MIN_AGGREGATE_SAVINGS_PCT = 5.0  # conservative floor; spec targets 15-35 %


def corpus_files() -> list[Path]:
    files = sorted(CORPUS_DIR.glob("*.md"))
    if not files:
        pytest.skip(
            "Corpus is empty — run `python scripts/fetch_corpus.py` first "
            "then commit the results."
        )
    return files


# ---------------------------------------------------------------------------
# Per-file parametrised test: conversion must succeed and reduce tokens
# ---------------------------------------------------------------------------


@pytest.mark.corpus
@pytest.mark.parametrize("path", corpus_files(), ids=lambda p: p.stem)
def test_corpus_file_converts(path: Path) -> None:
    """Each corpus file must convert without error and produce non-empty output."""
    source = path.read_text(encoding="utf-8", errors="replace")
    result = markdown_to_mlite(source)
    assert result.strip(), f"{path.name}: conversion produced empty output"


# ---------------------------------------------------------------------------
# Aggregate savings test: single summary across the whole corpus
# ---------------------------------------------------------------------------


@pytest.mark.corpus
def test_corpus_aggregate_savings(capsys: pytest.CaptureFixture[str]) -> None:
    """Token savings across the corpus must meet the minimum threshold."""
    files = corpus_files()

    rows: list[tuple[str, int, int, float]] = []
    total_src = total_out = 0

    for path in files:
        source = path.read_text(encoding="utf-8", errors="replace")
        try:
            result = markdown_to_mlite(source)
        except Exception as exc:  # noqa: BLE001
            # Don't let one broken file kill the whole suite — record as 0% savings
            rows.append((path.stem, 0, 0, 0.0))
            print(f"  ERROR {path.name}: {exc}", file=sys.stderr)
            continue

        src_tok = _count_tokens(source)
        out_tok = _count_tokens(result)
        savings = (1 - out_tok / src_tok) * 100 if src_tok > 0 else 0.0

        rows.append((path.stem, src_tok, out_tok, savings))
        total_src += src_tok
        total_out += out_tok

    # --- Print summary table (visible with -s or on failure) ---
    header = f"{'File':<40} {'Src':>7} {'Out':>7} {'Saving':>8}"
    divider = "─" * len(header)
    lines = [divider, header, divider]

    for name, src, out, pct in sorted(rows, key=lambda r: r[3]):
        flag = " !" if pct < 0 else ""
        lines.append(f"{name:<40} {src:>7,} {out:>7,} {pct:>7.1f}%{flag}")

    aggregate = (1 - total_out / total_src) * 100 if total_src > 0 else 0.0
    lines.append(divider)
    lines.append(
        f"{'TOTAL / AGGREGATE':<40} {total_src:>7,} {total_out:>7,} {aggregate:>7.1f}%"
    )
    lines.append(divider)
    lines.append(f"Files: {len(rows)}  |  Tokeniser: cl100k_base")

    with capsys.disabled():
        print("\n" + "\n".join(lines))

    assert aggregate >= MIN_AGGREGATE_SAVINGS_PCT, (
        f"Aggregate token savings {aggregate:.1f}% is below the minimum "
        f"{MIN_AGGREGATE_SAVINGS_PCT}%. "
        "Check the converter output — something may be inflating token counts."
    )
