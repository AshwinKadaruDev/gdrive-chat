"""Unified LLM error hierarchy.

Providers wrap their SDK-specific exceptions into these types so that
consumer code (agent, benchmark) catches a single hierarchy instead of
importing SDK-specific exception classes.
"""


class LLMError(Exception):
    """Base class for all LLM-related errors."""


class LLMRateLimitError(LLMError):
    """The provider returned a rate-limit / 429 error."""


class LLMAPIError(LLMError):
    """The provider returned a non-retryable API error."""


class LLMConnectionError(LLMError):
    """Could not connect to the provider."""


class LLMTimeoutError(LLMError):
    """The request to the provider timed out."""


class LLMProviderUnavailableError(LLMError):
    """No provider is configured or available for the requested model."""


# Backward-compat tuple for catch blocks that used to list SDK exceptions.
LLM_ERRORS = (LLMError,)
