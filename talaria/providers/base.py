"""Provider-agnostic message and tool types.

Conversation history is kept in this neutral shape so the same history can
be replayed against either backend (Claude or an OpenAI-compatible router).
Each provider adapter converts to/from its own wire format at call time.

Message shapes used in history:
    {"role": "user", "content": str}
    {"role": "assistant", "content": str, "tool_calls": [ToolCall, ...]}
    {"role": "tool", "tool_call_id": str, "name": str, "content": str}
"""

import threading
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
    cancelled: bool = False


class Provider(ABC):
    @abstractmethod
    def chat(
        self,
        history: list[dict[str, Any]],
        system: str,
        tools: list[ToolSpec],
        on_chunk: Callable[[str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> ProviderResponse:
        """Send the conversation to the model and return its reply.

        Text is always printed to stdout as it streams in. If on_chunk is
        given, it's additionally called with each text delta as it arrives
        — used by the web UI to also stream to the browser. If cancel_event
        is given and gets set while streaming, the provider stops consuming
        the stream at the next chunk boundary and returns whatever text was
        generated so far, with `cancelled=True` — used by the web UI's stop
        button to cut a reply short mid-generation.
        """


def is_tool_list(obj: object) -> bool:
    """True if obj is a list of genuine ToolSpec instances.

    A skill's TOOLS could otherwise be a list of look-alike objects (e.g. a
    skill that defines its own ToolSpec-shaped class instead of importing
    the real one) — those pass a naive `hasattr(module, "TOOLS")` check but
    break later at the provider layer, which expects `.input_schema` etc.
    """
    return isinstance(obj, list) and bool(obj) and all(isinstance(t, ToolSpec) for t in obj)
