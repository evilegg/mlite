<!--
ALL SECTIONS ARE REQUIRED. Do not leave any section blank, write "N/A", or
refer the reader to the commit log, git history, or the linked issue to fill
in a section. Each section must be self-contained prose written by the author.
-->

## Closes

Closes #

## What changed

<!-- 1–3 sentences written here, not a pointer to the issue or commit list.
     What does this PR do, stated plainly? -->

## Approach

<!-- How was it implemented? Call out any non-obvious decisions or tradeoffs.
     If you followed the spec exactly with no surprises, say so explicitly. -->

## Test plan

- [ ] `pytest` passes locally
- [ ] New tests cover the acceptance criteria in the issue
- [ ] Golden files updated if converter output changed (`mlite/tests/fixtures/*.mlt`)
- [ ] Corpus savings threshold still met (`pytest tests/test_corpus.py`)

## Spec changes

- [ ] No spec changes — format and conversion rules are unchanged
- [ ] `SPEC.md` updated before implementation (section: )

## Out of scope / follow-ups

<!-- Anything intentionally deferred from the issue? Write it here as a sentence,
     not a checkbox. If nothing was deferred, write "Nothing deferred." -->

## Ready checklist

- [ ] Every section above is filled with original prose (no "see commits", "see issue", or blank fields)
- [ ] Branch is `feat/<name>` branched from `main`
- [ ] Each commit on this branch passes tests independently
