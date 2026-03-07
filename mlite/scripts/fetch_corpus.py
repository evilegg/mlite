#!/usr/bin/env python3
"""Fetch the markdown corpus for stress testing.

Downloads files listed in corpus_sources.json into tests/corpus/.
Already-present files are skipped, so re-running is safe and fast.

Usage (from the mlite/ project directory):
    python scripts/fetch_corpus.py [--force]

Options:
    --force   Re-download all files, overwriting existing ones.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

SOURCES_FILE = Path(__file__).parent / "corpus_sources.json"
CORPUS_DIR = Path(__file__).parent.parent / "tests" / "corpus"
REQUEST_DELAY = 0.3  # seconds between requests, to be polite to GitHub


MIN_BYTES = 200  # reject stub files / symlink references


def fetch_url(client: httpx.Client, url: str) -> str | None:
    try:
        r = client.get(url, follow_redirects=True, timeout=20)
        if r.status_code == 200:
            # Reject HTML error pages
            ct = r.headers.get("content-type", "")
            if "html" in ct:
                return None
            # Reject stub files that are just a path reference
            if len(r.content) < MIN_BYTES:
                return None
            return r.text
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"    exception: {exc}", file=sys.stderr)
        return None


def main(force: bool = False) -> int:
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    sources: list[dict] = json.loads(SOURCES_FILE.read_text())

    ok = skip = fail = 0

    with httpx.Client(
        headers={"User-Agent": "mlite-corpus-fetcher/0.1 (github.com/evilegg/mlite)"}
    ) as client:
        for entry in sources:
            dest = CORPUS_DIR / entry["filename"]

            if dest.exists() and not force:
                skip += 1
                continue

            print(f"  {entry['description']}  ...", end=" ", flush=True)
            content: str | None = None

            for url in entry["urls"]:
                content = fetch_url(client, url)
                if content:
                    break
                time.sleep(REQUEST_DELAY)

            if content:
                dest.write_text(content, encoding="utf-8")
                kb = len(content.encode()) / 1024
                print(f"ok  ({kb:.1f} KB)")
                ok += 1
            else:
                print("FAILED")
                fail += 1

            time.sleep(REQUEST_DELAY)

    total = ok + skip + fail
    print(f"\n{'─' * 50}")
    print(f"Total sources : {total}")
    print(f"  Downloaded  : {ok}")
    print(f"  Skipped     : {skip}  (already present)")
    print(f"  Failed      : {fail}")
    print(f"Corpus dir    : {CORPUS_DIR.resolve()}")

    md_files = list(CORPUS_DIR.glob("*.md"))
    print(f"Markdown files: {len(md_files)}")

    if fail > 0:
        print(f"\nWARN: {fail} sources could not be fetched.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Re-download all files")
    args = parser.parse_args()
    sys.exit(main(force=args.force))
