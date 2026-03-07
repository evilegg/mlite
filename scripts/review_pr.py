#!/usr/bin/env python3
"""Autonomous PR reviewer for the mlite project.

Fetches the PR diff, PR description, and linked issue from GitHub,
sends them to Claude as a fresh context (no history from the coding session),
then either approves+merges or posts a change-request comment.

Usage:
    python scripts/review_pr.py <pr_number>

Requires:
    - ANTHROPIC_API_KEY environment variable
    - gh CLI authenticated with repo write access
    - Run from the repository root
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

_TMP_MSG = Path(__file__).parent.parent / ".tmp_msg"


def run(cmd: str, check: bool = True) -> str:
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Command failed: {cmd}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def get_pr(number: int) -> dict:
    raw = run(
        f"gh pr view {number} --json number,title,body,headRefName,baseRefName,state"
    )
    return json.loads(raw)


def get_issue_number(pr_body: str) -> int | None:
    match = re.search(r"(?:closes|fixes|resolves)\s+#(\d+)", pr_body, re.IGNORECASE)
    return int(match.group(1)) if match else None


def get_issue(number: int) -> dict:
    raw = run(f"gh issue view {number} --json number,title,body")
    return json.loads(raw)


def get_diff(pr_number: int) -> str:
    diff = run(f"gh pr diff {pr_number}")
    # Truncate very large diffs to avoid exceeding context limits
    lines = diff.splitlines()
    if len(lines) > 2000:
        truncated = "\n".join(lines[:2000])
        return truncated + f"\n\n[... diff truncated at 2000 lines ({len(lines)} total) ...]"
    return diff


def build_prompt(pr: dict, issue: dict | None, diff: str) -> str:
    issue_section = ""
    if issue:
        issue_section = f"""
## Linked issue: #{issue['number']} — {issue['title']}

{issue['body']}
"""

    return f"""You are an independent code reviewer for the mlite project — a Python library that converts Markdown to a token-efficient wire format called MLite.

You have NO context from the coding session that produced this PR. You are seeing only what is below. This separation is intentional: your job is to catch things the author might have missed.

Review this pull request and decide: APPROVE or REQUEST_CHANGES.

---
{issue_section}
## PR #{pr['number']} — {pr['title']}

{pr['body']}

## Diff

```diff
{diff}
```

---

## Your review criteria

**Approve if ALL of the following are true:**
1. Every PR template section contains original prose (not blank, not "see commits", not "see issue")
2. The diff is scoped to what the issue asked for — no unrelated refactors or extra features
3. New tests exist and plausibly cover the acceptance criteria in the issue
4. If converter output changed, golden files in `mlite/tests/fixtures/` were updated
5. If the issue required spec changes, `SPEC.md` was updated
6. The implementation is focused and clean — no over-engineering

**Request changes if ANY of the following are true:**
- A PR template section is empty, says "N/A", or defers to git history
- The diff touches files or logic outside the issue's stated scope
- Acceptance criteria from the issue are not addressed by the diff
- Tests are missing or clearly incomplete
- The code introduces unnecessary complexity

## Response format

Respond with ONLY valid JSON — no prose before or after:

{{
  "verdict": "APPROVE" or "REQUEST_CHANGES",
  "summary": "One paragraph. If approving, state what was done and why it meets the bar. If requesting changes, state clearly what is wrong and what needs to be fixed. Write for the coding instance that will action this — be specific.",
  "issues": ["specific issue 1", "specific issue 2"]
}}

The "issues" array must be empty ([]) for APPROVE. For REQUEST_CHANGES it must contain at least one item.
"""


def post_pr_comment(pr_number: int, body: str) -> None:
    _TMP_MSG.write_text(body, encoding="utf-8")
    run(f"gh pr comment {pr_number} --body-file {_TMP_MSG}")


def post_issue_comment(issue_number: int, body: str) -> None:
    _TMP_MSG.write_text(body, encoding="utf-8")
    run(f"gh issue comment {issue_number} --body-file {_TMP_MSG}")


def merge_pr(pr_number: int, branch: str) -> None:
    run(f"gh pr merge {pr_number} --merge --delete-branch")
    print(f"Merged PR #{pr_number} and deleted branch {branch}.")


def main(pr_number: int) -> int:
    import anthropic

    print(f"Reviewing PR #{pr_number}...")

    pr = get_pr(pr_number)
    if pr["state"] != "OPEN":
        print(f"PR #{pr_number} is {pr['state']}, skipping.")
        return 0

    issue_number = get_issue_number(pr["body"] or "")
    issue = get_issue(issue_number) if issue_number else None
    if issue:
        print(f"Linked issue: #{issue_number}")
    else:
        print("No linked issue found.")

    diff = get_diff(pr_number)
    prompt = build_prompt(pr, issue, diff)

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=(
            "You are a rigorous code reviewer. "
            "You respond only with valid JSON matching the schema in the user prompt. "
            "You have no memory of any prior coding session."
        ),
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        print(f"Could not parse reviewer response:\n{raw}", file=sys.stderr)
        return 1

    verdict = result.get("verdict", "").upper()
    summary = result.get("summary", "")
    issues = result.get("issues", [])

    print(f"\nVerdict: {verdict}")
    print(f"Summary: {summary}")

    if verdict == "APPROVE":
        lgtm_comment = f"LGTM\n\n{summary}"
        post_pr_comment(pr_number, lgtm_comment)
        if issue_number:
            post_issue_comment(issue_number, f"PR #{pr_number} approved and merged.\n\n{summary}")
        merge_pr(pr_number, pr["headRefName"])

    elif verdict == "REQUEST_CHANGES":
        issue_list = "\n".join(f"- {i}" for i in issues)
        comment = f"## Changes requested\n\n{summary}\n\n### Specific issues\n\n{issue_list}"
        post_pr_comment(pr_number, comment)
        print("Change-request comment posted.")

    else:
        print(f"Unexpected verdict '{verdict}' — no action taken.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <pr_number>", file=sys.stderr)
        sys.exit(1)
    try:
        pr_num = int(sys.argv[1].lstrip("#"))
    except ValueError:
        print(f"Invalid PR number: {sys.argv[1]}", file=sys.stderr)
        sys.exit(1)
    sys.exit(main(pr_num))
