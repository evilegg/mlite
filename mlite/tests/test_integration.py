"""Claude API integration tests — tool loop against Q&A fixture pairs.

Parameterised over all 25 Q&A pairs in tests/fixtures/*.qa.json.

These tests make real Anthropic API calls.  They are:
- Skipped automatically when ANTHROPIC_API_KEY is not set.
- Excluded from the default pytest run; use ``pytest -m integration`` to run.
- Cheap: Haiku 4.5 is used (factual retrieval, not reasoning).

Each test:
  1. Gives Claude the path to a fixture Markdown file.
  2. Asks the question from the Q&A pair.
  3. Drives the tool loop (max 3 turns) using mlite.tool.
  4. Asserts that all key terms from the expected answer appear in Claude's reply.
"""

from __future__ import annotations

import json
import os
import re
import string
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Markers / skip
# ---------------------------------------------------------------------------

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set",
    ),
]

# ---------------------------------------------------------------------------
# Q&A pair loading
# ---------------------------------------------------------------------------


def _load_qa_pairs() -> list[dict]:
    """Load all Q&A pairs from fixture JSON files, injecting the source path."""
    pairs: list[dict] = []
    for qa_path in sorted(FIXTURES.glob("*.qa.json")):
        stem = qa_path.stem.removesuffix(".qa")   # e.g. "basic"
        md_path = FIXTURES / f"{stem}.md"
        if not md_path.exists():
            continue
        for pair in json.loads(qa_path.read_text()):
            pairs.append({**pair, "md_path": md_path})
    return pairs


_QA_PAIRS = _load_qa_pairs()


def _qa_id(pair: dict) -> str:
    return pair["id"]


# ---------------------------------------------------------------------------
# Tool loop helper
# ---------------------------------------------------------------------------


def _run_tool_loop(question: str, md_path: Path, max_turns: int = 3) -> str:
    """Run the mlite tool loop and return Claude's final text response."""
    import anthropic
    from mlite.tool import READ_FILE_TOOL, SYSTEM_PROMPT_SNIPPET, handle_tool_call

    client = anthropic.Anthropic()

    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                f"Please read the file at {md_path} and answer this question: "
                f"{question}"
            ),
        }
    ]

    for _ in range(max_turns):
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=512,
            system=f"You are a helpful assistant.\n\n{SYSTEM_PROMPT_SNIPPET}",
            tools=[READ_FILE_TOOL],
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            # Collect all text blocks from the final response
            return " ".join(
                block.text for block in response.content if block.type == "text"
            )

        # Execute tool calls and append results
        results = []
        for block in response.content:
            if block.type == "tool_use":
                output = handle_tool_call(block.name, block.input)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                })
        messages.append({"role": "user", "content": results})

    raise RuntimeError(f"Tool loop did not terminate within {max_turns} turns")


# ---------------------------------------------------------------------------
# Answer checking
# ---------------------------------------------------------------------------

_PUNCT = str.maketrans("", "", string.punctuation)


def _normalise(text: str) -> str:
    """Lowercase and strip punctuation for loose matching."""
    return text.lower().translate(_PUNCT)


def _key_terms(answer: str) -> list[str]:
    """Extract meaningful tokens from an expected answer string."""
    # Split on whitespace, common separators, AND quote characters so that
    # f-string tokens like f"Hello," don't produce a spurious fHello term.
    tokens = re.split(r"""[\s,/|"'`]+""", answer)
    stop = {"and", "or", "the", "a", "an", "of", "to", "in", "is", "are", "f"}
    return [t for t in tokens if len(t) > 1 and t.lower() not in stop]


# ---------------------------------------------------------------------------
# Parameterized test
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("qa", _QA_PAIRS, ids=_qa_id)
def test_claude_answers_via_mlite_tool(qa: dict) -> None:
    """Claude reads a Markdown fixture via read_file and answers correctly."""
    answer = _run_tool_loop(qa["question"], qa["md_path"])
    normalised_answer = _normalise(answer)

    terms = _key_terms(qa["answer"])
    missing = [t for t in terms if _normalise(t) not in normalised_answer]

    assert not missing, (
        f"[{qa['id']}] Expected answer terms {missing!r} not found in reply.\n"
        f"  Question: {qa['question']}\n"
        f"  Expected: {qa['answer']}\n"
        f"  Got:      {answer}"
    )
