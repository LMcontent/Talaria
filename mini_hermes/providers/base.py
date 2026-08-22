"""Provider-agnostic message and tool types.

Conversation history is kept in this neutral shape so the same history can
be replayed against either backend (Claude or an OpenAI-compatible router).
Each provider adapter converts to/from its own wire format at call time.

Message shapes used in history:
    {"role": "user", "content": str}
    {"role": "assistant", "content": str, "tool_calls": [ToolCall, ...]}
    {"role": "tool", "tool_call_id": str, "name": str, "content": str}
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    handler: Callable[..., str]


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class ProviderResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class Provider(ABC):
    @abstractmethod
    def chat(
        self, history: list[dict[str, Any]], system: str, tools: list[ToolSpec]
    ) -> ProviderResponse:
        """Send the conversation to the model and return its reply."""


def is_tool_list(obj: object) -> bool:
    """True if obj is a list of genuine ToolSpec instances.

    A skill's TOOLS could otherwise be a list of look-alike objects (e.g. a
    skill that defines its own ToolSpec-shaped class instead of importing
    the real one) — those pass a naive `hasattr(module, "TOOLS")` check but
    break later at the provider layer, which expects `.input_schema` etc.
    """
    return isinstance(obj, list) and bool(obj) and all(isinstance(t, ToolSpec) for t in obj)
