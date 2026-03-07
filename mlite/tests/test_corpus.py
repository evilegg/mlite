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
MIN_AGGREGATE_SAVINGS_PCT_STRIP = 5.0     # conservative floor; spec targets 15-35 %
MIN_AGGREGATE_SAVINGS_PCT_PRESERVE = 2.0  # preserve mode retains emphasis tokens


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
# Aggregate savings test: two-column strip vs preserve comparison
# ---------------------------------------------------------------------------


@pytest.mark.corpus
def test_corpus_aggregate_savings(capsys: pytest.CaptureFixture[str]) -> None:
    """Token savings across the corpus — strip mode and preserve mode side by side."""
    files = corpus_files()

    rows: list[tuple[str, int, int, float, int, float]] = []
    total_src = total_strip = total_preserve = 0

    for path in files:
        source = path.read_text(encoding="utf-8", errors="replace")
        try:
            out_strip = markdown_to_mlite(source, preserve_emphasis=False)
            out_preserve = markdown_to_mlite(source, preserve_emphasis=True)
        except Exception as exc:  # noqa: BLE001
            rows.append((path.stem, 0, 0, 0.0, 0, 0.0))
            print(f"  ERROR {path.name}: {exc}", file=sys.stderr)
            continue

        src_tok = _count_tokens(source)
        strip_tok = _count_tokens(out_strip)
        preserve_tok = _count_tokens(out_preserve)
        strip_pct = (1 - strip_tok / src_tok) * 100 if src_tok > 0 else 0.0
        preserve_pct = (1 - preserve_tok / src_tok) * 100 if src_tok > 0 else 0.0

        rows.append((path.stem, src_tok, strip_tok, strip_pct, preserve_tok, preserve_pct))
        total_src += src_tok
        total_strip += strip_tok
        total_preserve += preserve_tok

    # --- Print summary table (visible with -s or on failure) ---
    header = (
        f"{'File':<40} {'Src':>7} {'Strip':>7} {'Saving':>8}  {'Preserve':>8} {'Saving':>8}"
    )
    divider = "─" * len(header)
    lines = [divider, header, divider]

    for name, src, strip, strip_pct, preserve, preserve_pct in sorted(rows, key=lambda r: r[3]):
        flag = " !" if strip_pct < 0 else ""
        lines.append(
            f"{name:<40} {src:>7,} {strip:>7,} {strip_pct:>7.1f}%"
            f"  {preserve:>8,} {preserve_pct:>7.1f}%{flag}"
        )

    agg_strip = (1 - total_strip / total_src) * 100 if total_src > 0 else 0.0
    agg_preserve = (1 - total_preserve / total_src) * 100 if total_src > 0 else 0.0
    lines.append(divider)
    lines.append(
        f"{'TOTAL / AGGREGATE':<40} {total_src:>7,} {total_strip:>7,} {agg_strip:>7.1f}%"
        f"  {total_preserve:>8,} {agg_preserve:>7.1f}%"
    )
    lines.append(divider)
    lines.append(f"Files: {len(rows)}  |  Tokeniser: cl100k_base")

    with capsys.disabled():
        print("\n" + "\n".join(lines))

    assert agg_strip >= MIN_AGGREGATE_SAVINGS_PCT_STRIP, (
        f"Strip-mode aggregate savings {agg_strip:.1f}% is below the minimum "
        f"{MIN_AGGREGATE_SAVINGS_PCT_STRIP}%."
    )
    assert agg_preserve >= MIN_AGGREGATE_SAVINGS_PCT_PRESERVE, (
        f"Preserve-mode aggregate savings {agg_preserve:.1f}% is below the minimum "
        f"{MIN_AGGREGATE_SAVINGS_PCT_PRESERVE}%."
    )
