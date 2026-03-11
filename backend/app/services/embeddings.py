import asyncio
import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class EmbeddingsService:
    """Service for generating text embeddings using OpenAI."""

    def __init__(
        self, api_key: str, model: str = "text-embedding-ada-002"
    ) -> None:
        self.model = model
        self._client = AsyncOpenAI(api_key=api_key)

    async def get_embedding(self, text: str) -> list[float]:
        """Generate an embedding vector for a single text string."""
        # Replace newlines with spaces for cleaner embedding input
        cleaned = text.replace("\n", " ").strip()
        if not cleaned:
            return [0.0] * 1536

        response = await self._client.embeddings.create(
            input=cleaned,
            model=self.model,
        )
        return response.data[0].embedding

    async def get_embeddings_batch(
        self, texts: list[str]
    ) -> list[list[float]]:
        """
        Generate embeddings for a batch of texts.

        Handles rate limiting by processing in chunks and retrying on failure.
        """
        if not texts:
            return []

        results: list[list[float]] = []
        # OpenAI allows up to ~2048 inputs per request; use a safe batch size
        batch_size = 512

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            cleaned = [t.replace("\n", " ").strip() or " " for t in batch]

            retry_count = 0
            max_retries = 5
            while True:
                try:
                    response = await self._client.embeddings.create(
                        input=cleaned,
                        model=self.model,
                    )
                    batch_embeddings = [item.embedding for item in response.data]
                    results.extend(batch_embeddings)
                    break
                except Exception as exc:
                    retry_count += 1
                    if retry_count > max_retries:
                        logger.error(
                            "Failed to get embeddings after %d retries: %s",
                            max_retries,
                            exc,
                        )
                        raise
                    # Exponential back-off for rate limits
                    wait = 2**retry_count
                    logger.warning(
                        "Embedding request failed (attempt %d/%d), retrying in %ds: %s",
                        retry_count,
                        max_retries,
                        wait,
                        exc,
                    )
                    await asyncio.sleep(wait)

        return results
