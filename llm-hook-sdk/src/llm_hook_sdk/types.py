"""Protocol types for the LLM hook SDK."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

ContentBlock = Dict[str, Any]
"""
A single content block within a message or tool result.

Discriminated by the ``"type"`` field::

    {"type": "text",       "text": "Hello"}
    {"type": "image",      "data": "<base64>", "mimeType": "image/png"}
    {"type": "structured", "data": {"key": "value"}}
    {"type": "resource",   "uri": "file://data.csv", "mimeType": "text/csv",         "data": "<base64>"}
    {"type": "resource",   "uri": "file://doc.pdf",  "mimeType": "application/pdf",  "data": "<base64>"}

For ``resource`` blocks, ``data`` is always base64-encoded regardless of whether the underlying
content is text or binary. Use ``mimeType`` to determine how to decode and handle the content.
"""


class MessageRole(str, Enum):
    """
    Valid message roles in conversations.

    Roles:
        SYSTEM: System instructions/prompts that guide the LLM's behavior
        USER: Messages from the user
        ASSISTANT: Responses from the LLM
        TOOL: Tool execution results
    """

    SYSTEM = "SYSTEM"
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    TOOL = "TOOL"


class StopReason(str, Enum):
    """
    Standardized stop reasons.

    Reasons:
        COMPLETE: Natural completion of the response
        MAX_TOKENS: Response truncated due to token limit
        TOOL_USE: LLM stopped to call one or more tools
        OTHER: Other/unknown stop reason
    """

    COMPLETE = "complete"
    MAX_TOKENS = "max_tokens"
    TOOL_USE = "tool_use"
    OTHER = "other"


class Tool:
    """
    MCP tool definition.

    Describes a tool that the LLM can call. The input_schema follows JSON Schema format.

    Fields:
        name:         Unique tool identifier, e.g. ``"read_file"``.
        description:  Human-readable explanation of what the tool does. Shown to the LLM.
        input_schema: JSON Schema object describing the tool's accepted parameters.

    Example:
        tool.name          # "read_file"
        tool.description   # "Read the contents of a file from disk"
        tool.input_schema  # {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
    """

    def __init__(self, raw: Dict[str, Any]):
        self._raw = raw

    @property
    def name(self) -> str:
        return self._raw.get("name", "")

    @property
    def description(self) -> str:
        return self._raw.get("description", "")

    @property
    def input_schema(self) -> Dict[str, Any]:
        return self._raw.get("inputSchema", {})

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Tool":
        return cls(d)

    def to_dict(self) -> Dict[str, Any]:
        return self._raw


class ToolCall:
    """
    A tool call requested by the LLM.

    When the LLM decides to use a tool, it returns one or more ToolCall objects.
    The ``id`` must be echoed back in the matching ToolResult so the LLM can
    correlate the request and response.

    Fields:
        id:        Unique identifier for this call.
        name:      Name of the tool to invoke.
        arguments: Dict of arguments to pass to the tool, matching its ``input_schema``.

    Example:
        tool_call.id         # "call_abc123"
        tool_call.name       # "read_file"
        tool_call.arguments  # {"path": "/tmp/data.csv"}
    """

    def __init__(
        self,
        raw: Optional[Dict[str, Any]] = None,
        *,
        id: Optional[str] = None,
        name: Optional[str] = None,
        arguments: Optional[Dict[str, Any]] = None,
    ):
        if raw is not None:
            self._raw = raw
            return

        self._raw: Dict[str, Any] = {}
        if id is not None:
            self._raw["id"] = id
        if name is not None:
            self._raw["name"] = name
        if arguments is not None:
            self._raw["arguments"] = arguments

    @property
    def id(self) -> str:
        return self._raw.get("id", "")

    @property
    def name(self) -> str:
        return self._raw.get("name", "")

    @property
    def arguments(self) -> Dict[str, Any]:
        return self._raw.get("arguments", {})

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ToolCall":
        return cls(d)

    def to_dict(self) -> Dict[str, Any]:
        return self._raw


class ToolResult:
    """
    Result of a tool execution, sent back to the LLM.

    Fields:
        tool_call_id: ID of the ToolCall this result corresponds to.
        content:      List of content blocks carrying the result payload. May contain
                      text, image, structured, or resource blocks (see ContentBlock).
        error:        True if the tool execution failed. The LLM will treat the
                      content as an error description rather than a successful result.

    Example:
        tool_result.tool_call_id  # "call_abc123"
        tool_result.content       # [{"type": "text", "text": "file contents here"}]
        tool_result.error         # False
    """

    def __init__(self, raw: Dict[str, Any]):
        self._raw = raw

    @property
    def tool_call_id(self) -> str:
        return self._raw.get("toolCallId", "")

    @property
    def content(self) -> Optional[List[ContentBlock]]:
        return self._raw.get("content")

    @property
    def error(self) -> bool:
        """Whether this tool result represents an error."""
        return self._raw.get("error", False)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ToolResult":
        return cls(d)

    def to_dict(self) -> Dict[str, Any]:
        return self._raw


class Message:
    """
    A single message in the conversation history.

    The ``role`` determines which fields are populated:

    * ``SYSTEM``    — ``content`` contains instruction blocks (typically text).
    * ``USER``      — ``content`` contains the user's input blocks.
    * ``ASSISTANT`` — ``content`` contains the LLM's response blocks; ``tool_calls``
                      is set when the LLM wants to invoke tools.
    * ``TOOL``      — ``tool_results`` contains the outcomes of tool executions.

    Fields:
        role:         The sender role (see MessageRole).
        content:      List of content blocks (see ContentBlock). Present for SYSTEM,
                      USER, and ASSISTANT messages; None for TOOL messages.
        tool_calls:   Tool invocations requested by the LLM. Set on ASSISTANT messages
                      when stop_reason is TOOL_USE; None otherwise.
        tool_results: Outcomes of tool executions. Set on TOOL messages; None otherwise.

    Example:
        msg.role          # MessageRole.USER
        msg.content       # [{"type": "text", "text": "What is 2 + 2?"}]
        msg.tool_calls    # [ToolCall(...), ...] or None
        msg.tool_results  # [ToolResult(...), ...] or None
    """

    def __init__(self, raw: Dict[str, Any]):
        self._raw = raw

    @property
    def role(self) -> MessageRole:
        return MessageRole(self._raw["role"])

    @property
    def content(self) -> Optional[List[ContentBlock]]:
        return self._raw.get("content")

    @property
    def tool_calls(self) -> Optional[List[ToolCall]]:
        tool_calls = self._raw.get("toolCalls")
        return [ToolCall.from_dict(item) for item in tool_calls] if tool_calls else None

    @property
    def tool_results(self) -> Optional[List[ToolResult]]:
        tool_results = self._raw.get("toolResults")
        return [ToolResult.from_dict(item) for item in tool_results] if tool_results else None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Message":
        return cls(d)

    def to_dict(self) -> Dict[str, Any]:
        return self._raw


class ChatResponse:
    """
    Response returned from ``LLMHookBase.chat()``.

    Fields:
        content:           List of content blocks produced by the LLM (see ContentBlock).
                           Typically one text block, but may include image or structured
                           blocks depending on the model.
        stop_reason:       Why the LLM stopped generating (see StopReason).
        prompt_tokens:     Number of input tokens consumed. Use 0 if not available.
        completion_tokens: Number of output tokens generated. Use 0 if not available.
        tool_calls:        Tool invocations requested by the LLM. Set when
                           stop_reason is TOOL_USE; None otherwise.

    Example:
        ChatResponse(
            content=[{"type": "text", "text": "The answer is 4"}],
            stop_reason=StopReason.COMPLETE,
            prompt_tokens=12,
            completion_tokens=8,
        )
    """

    def __init__(
        self,
        *,
        content: Optional[List[ContentBlock]] = None,
        stop_reason: StopReason = StopReason.COMPLETE,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        tool_calls: Optional[List[ToolCall]] = None,
    ):
        self._raw: Dict[str, Any] = {
            "content": content or [],
            "stopReason": stop_reason.value,
            "promptTokens": prompt_tokens,
            "completionTokens": completion_tokens,
        }
        if tool_calls:
            self._raw["toolCalls"] = [tool_call.to_dict() for tool_call in tool_calls]

    @property
    def content(self) -> List[ContentBlock]:
        return self._raw.get("content", [])

    @property
    def stop_reason(self) -> StopReason:
        return StopReason(self._raw.get("stopReason", StopReason.COMPLETE.value))

    @property
    def prompt_tokens(self) -> int:
        return self._raw.get("promptTokens", 0)

    @property
    def completion_tokens(self) -> int:
        return self._raw.get("completionTokens", 0)

    @property
    def tool_calls(self) -> Optional[List[ToolCall]]:
        tool_calls = self._raw.get("toolCalls")
        return [ToolCall.from_dict(item) for item in tool_calls] if tool_calls else None

    def to_dict(self) -> Dict[str, Any]:
        return self._raw
