"""LLM-as-judge evaluator using OpenAI function calling."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

# Ensure project root is on sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from openai import AsyncOpenAI

from benchmark.models import Evaluation

if TYPE_CHECKING:
    from benchmark.config import BenchmarkConfig

logger = logging.getLogger(__name__)

EVALUATION_TOOL_SCHEMA = {
    "type": "function",
    "name": "submit_evaluation",
    "description": "Submit structured evaluation of the agent's answer",
    "parameters": {
        "type": "object",
        "required": [
            "verdict",
            "answer_score",
            "answer_reasoning",
            "source_score",
            "source_reasoning",
            "missing_facts",
            "hallucinated_facts",
            "expected_sources",
            "found_sources",
            "missed_sources",
            "extra_sources",
        ],
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["pass", "partial", "fail"],
                "description": (
                    "pass = correct & complete, "
                    "partial = mostly correct but missing details or minor errors, "
                    "fail = wrong or significantly incomplete"
                ),
            },
            "answer_score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "0-100 score for answer quality. 90+ = pass, 60-89 = partial, <60 = fail",
            },
            "answer_reasoning": {
                "type": "string",
                "description": "Explanation of why the answer received this score",
            },
            "source_score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "0-100 score for source coverage",
            },
            "source_reasoning": {
                "type": "string",
                "description": "Explanation of source coverage assessment",
            },
            "missing_facts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Key facts from the expected answer that the agent omitted",
            },
            "hallucinated_facts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Claims the agent made that contradict the expected answer or aren't supported by sources",
            },
            "expected_sources": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Source files listed in the test suite",
            },
            "found_sources": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Expected sources that the agent DID cite (matched by file name)",
            },
            "missed_sources": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Expected sources that the agent did NOT cite",
            },
            "extra_sources": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Sources the agent cited that were not in the expected list",
            },
        },
    },
}


def pre_match_sources(
    expected_sources: list[str],
    agent_citations: list[dict],
) -> tuple[list[str], list[str], list[str]]:
    """Fuzzy-match expected source paths against agent citation file names.

    Returns (found, missed, extra).
    """
    agent_filenames = [c.get("file_name", "") for c in agent_citations]

    # Extract basenames from expected paths
    expected_basenames = [path.split("/")[-1] for path in expected_sources]

    found = []
    missed = []
    for basename in expected_basenames:
        if any(basename.lower() in af.lower() for af in agent_filenames):
            found.append(basename)
        else:
            missed.append(basename)

    extra = [
        af
        for af in agent_filenames
        if not any(eb.lower() in af.lower() for eb in expected_basenames)
    ]

    return found, missed, extra


def _build_evaluator_prompt(
    question: str,
    expected_answer: str,
    agent_answer: str,
    expected_sources: list[str],
    agent_sources: list[str],
    pre_matched: dict,
) -> str:
    return f"""You are an expert evaluator for a document Q&A system. You are given:
1. The QUESTION that was asked
2. The EXPECTED ANSWER (ground truth from the test suite)
3. The AGENT'S ANSWER (what the system produced)
4. The EXPECTED SOURCES (files the answer should come from)
5. The AGENT'S SOURCES (files the agent actually cited)
6. PRE-MATCHED SOURCE ANALYSIS (programmatic fuzzy matching results)

Your job is to judge whether the agent's answer is correct, complete, and
properly sourced. Be strict but fair:
- Minor formatting differences are OK
- Rounding differences in numbers are OK (e.g., $2.14M vs $2,140,500)
- The agent may provide EXTRA correct information — that's fine
- But MISSING key facts or WRONG numbers are failures
- Source coverage matters: the agent should cite the right files

QUESTION:
{question}

EXPECTED ANSWER:
{expected_answer}

AGENT'S ANSWER:
{agent_answer}

EXPECTED SOURCES:
{json.dumps(expected_sources, indent=2)}

AGENT'S SOURCES:
{json.dumps(agent_sources, indent=2)}

PRE-MATCHED SOURCE ANALYSIS:
- Found (matched): {json.dumps(pre_matched['found'])}
- Missed (not cited): {json.dumps(pre_matched['missed'])}
- Extra (cited but not expected): {json.dumps(pre_matched['extra'])}

Call the submit_evaluation function with your assessment."""


async def evaluate_answer(
    question: dict,
    agent_answer: str,
    agent_citations: list[dict],
    config: BenchmarkConfig,
) -> Evaluation | None:
    """Evaluate the agent's answer using an LLM judge.

    Returns an Evaluation or None if the evaluator fails after retries.
    """
    found, missed, extra = pre_match_sources(
        question["sources"], agent_citations
    )
    agent_filenames = [c.get("file_name", "") for c in agent_citations]

    prompt = _build_evaluator_prompt(
        question=question["question"],
        expected_answer=question["expected_answer"],
        agent_answer=agent_answer,
        expected_sources=question["sources"],
        agent_sources=agent_filenames,
        pre_matched={"found": found, "missed": missed, "extra": extra},
    )

    client = AsyncOpenAI(api_key=config.openai_api_key)

    for attempt in range(3):
        try:
            response = await client.responses.create(
                model=config.evaluator_model,
                input=[{"role": "user", "content": prompt}],
                tools=[EVALUATION_TOOL_SCHEMA],
                tool_choice={"type": "function", "name": "submit_evaluation"},
                reasoning={"effort": "high"},
            )

            # Extract function call from response output
            for item in response.output:
                if item.type == "function_call" and item.name == "submit_evaluation":
                    eval_data = json.loads(item.arguments)
                    return Evaluation(**eval_data)

            logger.warning("Evaluator response had no function call (attempt %d)", attempt + 1)

        except Exception:
            logger.exception("Evaluator failed (attempt %d)", attempt + 1)
            if attempt == 2:
                return None

    return None
