#!/usr/bin/env python3
"""Generate Q&A pairs for MLite eval fixtures using the Claude API.

Usage:
    python scripts/generate_qa.py [--model MODEL] [--n INT] FILE [FILE ...]

Writes <file>.qa.json alongside each input .md file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import anthropic

# Add the package root so mlite is importable
sys.path.insert(0, str(Path(__file__).parent.parent))
from mlite.adapters.markdown import markdown_to_mlite  # noqa: E402

DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_N = 5

SYSTEM_PROMPT = """\
You are creating a question-and-answer dataset for evaluating how well an LLM
comprehends a document in a compressed format versus the original Markdown.

Given a Markdown document, produce a JSON array of Q&A pairs.
Each item must have exactly these fields:
  "id"             - unique string: "<basename>-<zero-padded-seq>" e.g. "basic-001"
  "question"       - a natural-language question answerable from the document alone
  "answer"         - the canonical short answer (phrase or sentence, not a full paragraph)
  "type"           - one of: "factual", "list", "code", "table", "emphasis"
  "source_element" - the document element the answer comes from, one of:
                     "heading", "paragraph", "list", "code_block", "inline_code",
                     "table", "link", "blockquote", "emphasis", "strikethrough"

Rules:
- Cover different structural elements (headings, lists, code, tables, links, etc.)
- Prefer factual questions with a single unambiguous short answer
- Do NOT ask questions requiring inference, arithmetic, or external knowledge
- Do NOT ask questions whose answer is not explicitly present in the document
- Vary the "type" field across items when possible
- Output ONLY valid JSON (a top-level array), no prose or code fences
"""


def generate_qa(
    md_path: Path,
    n: int,
    model: str,
    client: anthropic.Anthropic,
) -> list[dict]:
    """Call the LLM to generate Q&A pairs for a single Markdown file."""
    source = md_path.read_text()
    basename = md_path.stem

    # Verify the file converts successfully (skip if not)
    try:
        markdown_to_mlite(source, preserve_emphasis=True)
    except Exception as exc:
        print(f"  [skip] conversion failed: {exc}", file=sys.stderr)
        return []

    user_prompt = (
        f"Document basename for IDs: {basename}\n"
        f"Number of Q&A pairs to generate: {n}\n\n"
        f"--- BEGIN DOCUMENT ---\n{source}\n--- END DOCUMENT ---"
    )

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = response.content[0].text.strip()
    # Strip accidental code fences
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0]

    items = json.loads(raw)

    # Basic schema validation
    required = {"id", "question", "answer", "type", "source_element"}
    valid = []
    for item in items:
        if required.issubset(item.keys()):
            valid.append(item)
        else:
            missing = required - item.keys()
            print(f"  [warn] item missing fields {missing}, skipping", file=sys.stderr)

    return valid


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path, metavar="FILE")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--n", type=int, default=DEFAULT_N, metavar="INT",
                        help="Q&A pairs per document (default: %(default)s)")
    args = parser.parse_args()

    client = anthropic.Anthropic()
    total_qa = 0
    failures = 0

    for md_path in args.files:
        md_path = md_path.resolve()
        if not md_path.exists():
            print(f"[error] not found: {md_path}", file=sys.stderr)
            failures += 1
            continue
        if md_path.suffix != ".md":
            print(f"[skip] not a .md file: {md_path}", file=sys.stderr)
            continue

        out_path = md_path.with_suffix(".qa.json")
        print(f"Generating {args.n} Q&A pairs for {md_path.name} ...", end=" ", flush=True)

        try:
            items = generate_qa(md_path, args.n, args.model, client)
        except Exception as exc:
            print(f"FAILED ({exc})", file=sys.stderr)
            failures += 1
            continue

        if not items:
            print("0 items (skipped)")
            continue

        out_path.write_text(json.dumps(items, indent=2) + "\n")
        total_qa += len(items)
        print(f"{len(items)} items → {out_path.name}")

    print(f"\nDone. {total_qa} Q&A pairs generated across {len(args.files) - failures} files.")
    if failures:
        print(f"{failures} file(s) failed.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
