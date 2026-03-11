"""Activity: generate vector embeddings for content chunks using OpenAI."""

from __future__ import annotations

import asyncio
import logging
import os

import openai
from temporalio import activity

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-ada-002"
BATCH_SIZE = 20  # OpenAI rate-limit-friendly batch size


@activity.defn
async def generate_embeddings(chunks: list[dict]) -> list[dict]:
    """Add content_vector embeddings to each chunk.

    Calls the OpenAI Embeddings API in batches of BATCH_SIZE.
    Returns the chunks list with content_vector field added.
    """
    if not chunks:
        return chunks

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set")

    client = openai.AsyncOpenAI(api_key=api_key)

    activity.logger.info("Generating embeddings for %d chunks", len(chunks))

    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        texts = [_prepare_text(c.get("text", "")) for c in batch]

        try:
            response = await client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=texts,
            )

            for j, embedding_data in enumerate(response.data):
                batch[j]["content_vector"] = embedding_data.embedding

        except openai.RateLimitError:
            activity.logger.warning("Rate limited, waiting 10 seconds before retry...")
            await asyncio.sleep(10)
            # Retry this batch
            response = await client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=texts,
            )
            for j, embedding_data in enumerate(response.data):
                batch[j]["content_vector"] = embedding_data.embedding

        # Small delay between batches to be rate-limit friendly
        if i + BATCH_SIZE < len(chunks):
            await asyncio.sleep(0.5)

    activity.logger.info("Embeddings generated for %d chunks", len(chunks))
    return chunks


def _prepare_text(text: str) -> str:
    """Prepare text for embedding -- truncate if needed.

    The ada-002 model supports up to 8191 tokens. We do a rough char-level
    truncation (1 token ~ 4 chars) to avoid exceeding the limit.
    """
    max_chars = 8191 * 4  # ~32k chars
    if len(text) > max_chars:
        return text[:max_chars]
    return text
