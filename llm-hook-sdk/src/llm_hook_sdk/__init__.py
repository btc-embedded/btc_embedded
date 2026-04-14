"""Public package exports for the LLM hook SDK."""

from .base import LLMHookBase
from .types import (
    ChatResponse,
    ContentBlock,
    Message,
    MessageRole,
    StopReason,
    Tool,
    ToolCall,
    ToolResult,
)

__all__ = [
    "ChatResponse",
    "ContentBlock",
    "LLMHookBase",
    "Message",
    "MessageRole",
    "StopReason",
    "Tool",
    "ToolCall",
    "ToolResult",
]

__version__ = "1.0.0"
