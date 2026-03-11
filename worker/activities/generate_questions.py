"""Activity: generate hypothetical questions for each chunk, then embed them."""

from __future__ import annotations

import asyncio
import logging
import os

import openai
from temporalio import activity

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-ada-002"
QUESTION_BATCH_SIZE = 5  # Process a few chunks at a time for question generation

QUESTION_SYSTEM_PROMPT = """You are a helpful assistant that generates hypothetical questions a user might ask that would be answered by the given text chunk. Generate 3 to 5 specific, diverse questions. Return ONLY the questions, one per line, with no numbering or bullet points."""


@activity.defn
async def generate_questions(chunks: list[dict]) -> list[dict]:
    """For each chunk, generate hypothetical questions and embed them.

    Adds 'questions' (list[str]) and 'questions_vector' (list[float]) to each chunk.
    Uses OpenAI for both question generation and embedding.
    Falls back to Anthropic for question generation if ANTHROPIC_API_KEY is set.
    """
    if not chunks:
        return chunks

    openai_key = os.environ.get("OPENAI_API_KEY", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set")

    oai_client = openai.AsyncOpenAI(api_key=openai_key)

    # Decide which LLM to use for question generation
    use_anthropic = bool(anthropic_key)
    anthropic_client = None
    if use_anthropic:
        try:
            import anthropic
            anthropic_client = anthropic.AsyncAnthropic(api_key=anthropic_key)
        except ImportError:
            use_anthropic = False

    activity.logger.info(
        "Generating questions for %d chunks (LLM=%s)",
        len(chunks),
        "anthropic" if use_anthropic else "openai",
    )

    for i in range(0, len(chunks), QUESTION_BATCH_SIZE):
        batch = chunks[i : i + QUESTION_BATCH_SIZE]

        for chunk in batch:
            text = chunk.get("text", "")
            if not text.strip():
                chunk["questions"] = []
                chunk["questions_vector"] = []
                continue

            # Generate questions
            try:
                if use_anthropic and anthropic_client:
                    questions = await _generate_questions_anthropic(anthropic_client, text)
                else:
                    questions = await _generate_questions_openai(oai_client, text)
            except Exception as e:
                activity.logger.warning("Question generation failed for chunk %s: %s", chunk.get("chunk_id"), e)
                chunk["questions"] = []
                chunk["questions_vector"] = []
                continue

            chunk["questions"] = questions

            # Embed the concatenated questions
            if questions:
                joined = " ".join(questions)
                try:
                    emb_response = await oai_client.embeddings.create(
                        model=EMBEDDING_MODEL,
                        input=joined[:32000],  # safety truncation
                    )
                    chunk["questions_vector"] = emb_response.data[0].embedding
                except Exception as e:
                    activity.logger.warning("Question embedding failed: %s", e)
                    chunk["questions_vector"] = []
            else:
                chunk["questions_vector"] = []

        # Rate-limit-friendly pause between batches
        if i + QUESTION_BATCH_SIZE < len(chunks):
            await asyncio.sleep(1.0)

    activity.logger.info("Questions generated for %d chunks", len(chunks))
    return chunks


async def _generate_questions_openai(client: openai.AsyncOpenAI, text: str) -> list[str]:
    """Generate hypothetical questions using OpenAI ChatCompletion."""
    # Truncate text for the prompt
    truncated = text[:6000]

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": QUESTION_SYSTEM_PROMPT},
            {"role": "user", "content": f"Generate questions for this text:\n\n{truncated}"},
        ],
        temperature=0.7,
        max_tokens=500,
    )

    raw = response.choices[0].message.content or ""
    return _parse_questions(raw)


async def _generate_questions_anthropic(client, text: str) -> list[str]:
    """Generate hypothetical questions using Anthropic Claude."""
    truncated = text[:6000]

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=QUESTION_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": f"Generate questions for this text:\n\n{truncated}"},
        ],
    )

    raw = response.content[0].text if response.content else ""
    return _parse_questions(raw)


def _parse_questions(raw: str) -> list[str]:
    """Parse LLM output into a list of question strings."""
    lines = raw.strip().split("\n")
    questions = []
    for line in lines:
        cleaned = line.strip().lstrip("0123456789.-) ").strip()
        if cleaned and cleaned.endswith("?"):
            questions.append(cleaned)
        elif cleaned and len(cleaned) > 10:
            # Might be a question without a trailing question mark
            questions.append(cleaned)

    # Return at most 5 questions
    return questions[:5]
