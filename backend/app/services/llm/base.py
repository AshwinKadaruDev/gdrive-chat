"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

from app.services.llm.types import LLMResponse, LLMStreamEvent


class LLMProvider(ABC):
    """Interface that every LLM provider must implement."""

    @abstractmethod
    async def call_with_tools(
        self,
        messages: list,
        tools: list,
        model: str,
        tool_choice: str = "auto",
        temperature: float = 0.1,
    ) -> LLMResponse:
        """Call the LLM with tool definitions and return a normalized response."""

    @abstractmethod
    async def stream_call_with_tools(
        self,
        messages: list,
        tools: list,
        model: str,
        tool_choice: str = "auto",
        temperature: float = 0.1,
    ) -> AsyncGenerator[LLMStreamEvent, None]:
        """Stream an LLM call, yielding text deltas and a final response_complete event."""

    @abstractmethod
    async def complete(self, prompt: str, max_tokens: int = 500) -> str:
        """Simple text completion without tool use."""

    @staticmethod
    @abstractmethod
    def can_handle(model: str) -> bool:
        """Return True if this provider can serve the given model name."""
