"""LLM provider package — backward-compatible re-exports.

Every existing ``from app.services.llm import X`` continues to work.
"""

from app.services.llm.client import LLMClient
from app.services.llm.errors import (
    LLM_ERRORS,
    LLMAPIError,
    LLMConnectionError,
    LLMError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.services.llm.types import (
    Choice,
    FunctionCall,
    LLMResponse,
    LLMStreamEvent,
    MessageContent,
    ToolCall,
)

__all__ = [
    # Client
    "LLMClient",
    # Types
    "Choice",
    "FunctionCall",
    "LLMResponse",
    "LLMStreamEvent",
    "MessageContent",
    "ToolCall",
    # Errors
    "LLM_ERRORS",
    "LLMAPIError",
    "LLMConnectionError",
    "LLMError",
    "LLMProviderUnavailableError",
    "LLMRateLimitError",
    "LLMTimeoutError",
]
