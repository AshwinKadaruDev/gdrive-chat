"""Model-to-provider routing via a simple registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.llm.base import LLMProvider

# Ordered list of provider classes (checked in registration order).
_PROVIDER_CLASSES: list[type[LLMProvider]] = []


def register_provider(cls: type[LLMProvider]) -> type[LLMProvider]:
    """Class decorator that registers a provider in the global registry."""
    _PROVIDER_CLASSES.append(cls)
    return cls


def get_provider_for_model(
    model: str,
    providers: dict[type[LLMProvider], LLMProvider],
) -> LLMProvider | None:
    """Return the first registered provider that can handle *model* and is instantiated.

    Falls back to *any* available provider if the preferred one wasn't instantiated
    (e.g. Claude model requested but only OpenAI key provided).
    """
    preferred: LLMProvider | None = None
    fallback: LLMProvider | None = None

    for cls in _PROVIDER_CLASSES:
        instance = providers.get(cls)
        if instance is None:
            continue
        if cls.can_handle(model):
            preferred = instance
            break
        if fallback is None:
            fallback = instance

    return preferred or fallback
