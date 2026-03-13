"""Normalized response dataclasses shared across all LLM providers."""

from dataclasses import dataclass, field


@dataclass
class ToolCall:
    """Normalized tool call representation."""

    id: str
    function: "FunctionCall"


@dataclass
class FunctionCall:
    """Normalized function call with name and JSON arguments."""

    name: str
    arguments: str  # JSON string


@dataclass
class MessageContent:
    """Normalized message from an LLM response."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    _raw_output_items: list = field(default_factory=list)


@dataclass
class Choice:
    """Normalized choice wrapper."""

    message: MessageContent = field(default_factory=MessageContent)


@dataclass
class LLMResponse:
    """Normalized LLM response matching OpenAI-style structure."""

    choices: list[Choice] = field(default_factory=list)


@dataclass
class LLMStreamEvent:
    """Event yielded during streaming LLM calls."""

    type: str  # "text_delta" or "response_complete"
    text: str | None = None
    response: LLMResponse | None = None
