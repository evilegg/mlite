#!/usr/bin/env python3
"""MLite quality evaluation pipeline.

Measures semantic fidelity (LLM answer agreement) and token efficiency for each
document, producing a combined quality/efficiency score.

Usage:
    python scripts/run_eval.py [--model MODEL] [--no-cache] [--out FILE] FILE.qa.json ...
    python scripts/run_eval.py --fixtures
    python scripts/run_eval.py --corpus
    python scripts/run_eval.py --all

Exit code: 0 if mean agreement >= 90% on corpus, >= 98% on fixtures.
           1 otherwise.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Optional

import anthropic

# Package root on the path
sys.path.insert(0, str(Path(__file__).parent.parent))
from mlite.adapters.markdown import markdown_to_mlite  # noqa: E402

try:
    import tiktoken

    _enc = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_enc.encode(text))

except ImportError:
    def count_tokens(text: str) -> int:
        # Rough fallback: 1 token ≈ 4 chars
        return len(text) // 4


DEFAULT_MODEL = "claude-haiku-4-5"
FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"
CORPUS_DIR = Path(__file__).parent.parent / "tests" / "corpus"
CACHE_DIR = Path(__file__).parent.parent / "eval_cache"

EXTRACT_SYSTEM = (
    "Answer the following question using only the provided document. "
    "Be concise. If the answer is not in the document, say 'not found'."
)

JUDGE_SYSTEM = (
    "You are a grader. Given a reference answer and a candidate answer to the same "
    "question, output a JSON object: {\"agree\": true or false, \"reason\": \"...\"}.\n"
    "Answers agree if they convey the same factual content, even with different wording "
    "or different markdown formatting notation. Ignore markdown emphasis markers "
    "(**bold**, _italic_, etc.) when comparing — focus only on the semantic content. "
    "A candidate that says 'not found' when the reference has a clear answer should "
    "disagree. Output ONLY valid JSON, no prose."
)

# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_key(model: str, system: str, user: str) -> str:
    payload = json.dumps({"model": model, "system": system, "user": user}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _cache_get(key: str) -> Optional[str]:
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())["response"]
    return None


def _cache_set(key: str, response: str) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / f"{key}.json"
    path.write_text(json.dumps({"response": response}))


# ── LLM helpers ───────────────────────────────────────────────────────────────

def _llm(
    client: anthropic.Anthropic,
    model: str,
    system: str,
    user: str,
    use_cache: bool,
) -> str:
    """Call the LLM with optional caching."""
    key = _cache_key(model, system, user)
    if use_cache:
        cached = _cache_get(key)
        if cached is not None:
            return cached

    response = client.messages.create(
        model=model,
        max_tokens=256,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = response.content[0].text.strip()

    if use_cache:
        _cache_set(key, text)

    return text


def extract_answer(
    client: anthropic.Anthropic,
    model: str,
    document: str,
    question: str,
    use_cache: bool,
) -> str:
    """Ask the LLM to answer a question from a document."""
    system = EXTRACT_SYSTEM
    user = f"Document:\n\n{document}\n\nQuestion: {question}"
    return _llm(client, model, system, user, use_cache)


def judge_agreement(
    client: anthropic.Anthropic,
    model: str,
    question: str,
    reference: str,
    candidate: str,
    use_cache: bool,
) -> tuple[bool, str]:
    """Return (agree, reason) for a reference/candidate answer pair."""
    user = (
        f"Question: {question}\n"
        f"Reference answer: {reference}\n"
        f"Candidate answer: {candidate}"
    )
    raw = _llm(client, model, JUDGE_SYSTEM, user, use_cache)

    # Strip accidental code fences
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        obj = json.loads(text)
        return bool(obj.get("agree", False)), str(obj.get("reason", ""))
    except json.JSONDecodeError:
        # Fallback: check for "true" in raw output
        agree = '"agree": true' in raw.lower() or '"agree":true' in raw.lower()
        return agree, f"parse error — raw: {raw[:80]}"


# ── Per-document evaluation ────────────────────────────────────────────────────

def evaluate_document(
    qa_path: Path,
    client: anthropic.Anthropic,
    model: str,
    use_cache: bool,
    preserve_emphasis: bool = True,
) -> dict:
    """Evaluate one .qa.json file. Returns a result dict."""
    # qa_path is like basic.qa.json → strip ".qa" stem suffix to get basic.md
    stem = qa_path.stem  # "basic.qa"
    if stem.endswith(".qa"):
        stem = stem[: -len(".qa")]
    md_path = qa_path.parent / (stem + ".md")
    if not md_path.exists():
        raise FileNotFoundError(f"Source Markdown not found: {md_path}")

    md_source = md_path.read_text()
    questions = json.loads(qa_path.read_text())

    # Convert to MLite
    try:
        mlt_source = markdown_to_mlite(md_source, preserve_emphasis=preserve_emphasis)
    except Exception as exc:
        raise RuntimeError(f"MLite conversion failed: {exc}") from exc

    md_tokens = count_tokens(md_source)
    mlt_tokens = count_tokens(mlt_source)
    token_delta_pct = (mlt_tokens - md_tokens) / md_tokens * 100

    item_results = []
    for q in questions:
        qid = q["id"]
        question = q["question"]
        canonical = q["answer"]

        md_answer = extract_answer(client, model, md_source, question, use_cache)
        mlt_answer = extract_answer(client, model, mlt_source, question, use_cache)
        agree, reason = judge_agreement(
            client, model, question, md_answer, mlt_answer, use_cache
        )

        item_results.append({
            "id": qid,
            "question": question,
            "canonical": canonical,
            "md_answer": md_answer,
            "mlt_answer": mlt_answer,
            "agree": agree,
            "reason": reason,
            "type": q.get("type", ""),
            "source_element": q.get("source_element", ""),
        })

    n = len(item_results)
    n_agree = sum(1 for r in item_results if r["agree"])
    agreement_rate = n_agree / n if n else 0.0
    efficiency_bonus = -token_delta_pct / 100  # positive when MLite is smaller
    score = agreement_rate * (1 + efficiency_bonus)

    return {
        "document": md_path.name,
        "qa_path": str(qa_path),
        "n_questions": n,
        "n_agree": n_agree,
        "agreement_rate": agreement_rate,
        "md_tokens": md_tokens,
        "mlt_tokens": mlt_tokens,
        "token_delta_pct": token_delta_pct,
        "score": score,
        "items": item_results,
    }


# ── Reporting ─────────────────────────────────────────────────────────────────

def print_summary(results: list[dict]) -> None:
    """Print a summary table to stdout."""
    col_w = max(len(r["document"]) for r in results) + 2
    header = (
        f"{'document':<{col_w}} {'questions':>9} {'agreement':>10} "
        f"{'token_delta':>12} {'score':>7}"
    )
    print(header)
    print("-" * len(header))

    total_q = 0
    total_agree = 0
    total_md_tok = 0
    total_mlt_tok = 0
    scores = []

    for r in results:
        total_q += r["n_questions"]
        total_agree += r["n_agree"]
        total_md_tok += r["md_tokens"]
        total_mlt_tok += r["mlt_tokens"]
        scores.append(r["score"])

        print(
            f"{r['document']:<{col_w}} {r['n_questions']:>9} "
            f"{r['agreement_rate']:>9.1%} "
            f"{r['token_delta_pct']:>+11.1f}% "
            f"{r['score']:>7.3f}"
        )

    print("-" * len(header))
    overall_agreement = total_agree / total_q if total_q else 0.0
    overall_delta = (total_mlt_tok - total_md_tok) / total_md_tok * 100 if total_md_tok else 0.0
    mean_score = sum(scores) / len(scores) if scores else 0.0
    print(
        f"{'TOTAL / MEAN':<{col_w}} {total_q:>9} "
        f"{overall_agreement:>9.1%} "
        f"{overall_delta:>+11.1f}% "
        f"{mean_score:>7.3f}"
    )

    # Per-element breakdown
    by_element: dict[str, list[bool]] = {}
    for r in results:
        for item in r["items"]:
            el = item.get("source_element") or "unknown"
            by_element.setdefault(el, []).append(item["agree"])

    if by_element:
        print()
        print("Per-element breakdown:")
        el_col = max(len(e) for e in by_element) + 2
        print(f"  {'element':<{el_col}} {'questions':>9} {'agreement':>10}")
        print(f"  {'-' * (el_col + 21)}")
        for el, agrees in sorted(by_element.items()):
            rate = sum(agrees) / len(agrees)
            print(f"  {el:<{el_col}} {len(agrees):>9} {rate:>9.1%}")


# ── Main ──────────────────────────────────────────────────────────────────────

def collect_qa_paths(fixture_paths: list[Path]) -> list[Path]:
    return [p for p in fixture_paths if p.exists()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, metavar="FILE.qa.json")
    parser.add_argument("--fixtures", action="store_true",
                        help="Evaluate all fixture Q&A files")
    parser.add_argument("--corpus", action="store_true",
                        help="Evaluate all corpus Q&A files")
    parser.add_argument("--all", dest="all_", action="store_true",
                        help="Evaluate fixtures + corpus")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--no-cache", dest="no_cache", action="store_true",
                        help="Disable LLM response caching")
    parser.add_argument("--out", type=Path, default=Path("eval_results.jsonl"),
                        help="Output JSONL file (default: eval_results.jsonl)")
    parser.add_argument("--strip-emphasis", dest="strip_emphasis", action="store_true",
                        help="Convert with preserve_emphasis=False (default: preserve)")
    args = parser.parse_args()

    qa_paths: list[Path] = list(args.files)

    if args.fixtures or args.all_:
        qa_paths += sorted(FIXTURES_DIR.glob("*.qa.json"))
    if args.corpus or args.all_:
        qa_paths += sorted(CORPUS_DIR.glob("*.qa.json"))

    if not qa_paths:
        parser.print_help()
        sys.exit(1)

    use_cache = not args.no_cache
    preserve_emphasis = not args.strip_emphasis
    client = anthropic.Anthropic()
    results = []
    failures = []

    for qa_path in qa_paths:
        print(f"Evaluating {qa_path.name} ...", file=sys.stderr)
        try:
            result = evaluate_document(
                qa_path, client, args.model, use_cache, preserve_emphasis
            )
            results.append(result)
        except Exception as exc:
            print(f"  [error] {exc}", file=sys.stderr)
            failures.append(qa_path.name)

    if not results:
        print("No results.", file=sys.stderr)
        sys.exit(1)

    # Write JSONL output
    with args.out.open("w") as fh:
        for r in results:
            fh.write(json.dumps(r) + "\n")
    print(f"\nDetailed results written to {args.out}", file=sys.stderr)

    # Print summary table
    print()
    print_summary(results)

    if failures:
        print(f"\n{len(failures)} file(s) failed: {', '.join(failures)}", file=sys.stderr)

    # Determine pass/fail
    total_q = sum(r["n_questions"] for r in results)
    total_agree = sum(r["n_agree"] for r in results)
    overall_agreement = total_agree / total_q if total_q else 0.0

    is_fixture_run = (args.fixtures or args.all_) and not args.corpus
    threshold = 0.98 if is_fixture_run else 0.90

    if overall_agreement < threshold:
        print(
            f"\nFAIL: agreement {overall_agreement:.1%} < threshold {threshold:.0%}",
            file=sys.stderr,
        )
        sys.exit(1)
    else:
        print(
            f"\nPASS: agreement {overall_agreement:.1%} >= threshold {threshold:.0%}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
