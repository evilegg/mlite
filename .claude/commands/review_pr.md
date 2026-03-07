Run the autonomous PR reviewer for pull request $ARGUMENTS.

Execute the following command from the repository root:

```bash
python scripts/review_pr.py $ARGUMENTS
```

The script will:

1. Fetch the PR body, linked issue, and full diff from GitHub
2. Send them to Claude as a fresh context (no history from the coding session)
3. If approved: post "LGTM" on the PR and linked issue, merge with --merge (no squash), delete the branch
4. If changes requested: post a comment on the PR with specific issues for the coding instance to address

Requires ANTHROPIC_API_KEY and gh CLI authenticated with write access to evilegg/mlite.
