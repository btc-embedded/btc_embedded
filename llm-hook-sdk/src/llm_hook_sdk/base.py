"""Base hook implementation for stdin/stdout JSON transport."""

from __future__ import annotations

from abc import ABC, abstractmethod
import io
import json
import sys
import traceback
from typing import Any, Dict, List, Optional, TextIO

from .types import ChatResponse, Message, Tool


def _ensure_utf8_text_stream(stream: TextIO) -> TextIO:
    buffer = getattr(stream, "buffer", None)
    encoding = getattr(stream, "encoding", None)
    if buffer is None:
        return stream
    if isinstance(encoding, str) and encoding.lower().replace("_", "-") == "utf-8":
        return stream
    return io.TextIOWrapper(buffer, encoding="utf-8")


def _configure_stdio() -> None:
    sys.stdin = _ensure_utf8_text_stream(sys.stdin)
    sys.stdout = _ensure_utf8_text_stream(sys.stdout)


class LLMHookBase(ABC):
    """Base class for LLM hooks."""

    @abstractmethod
    def __init__(self):
        """Initialize the LLM client."""

    @abstractmethod
    def chat(
        self,
        messages: List[Message],
        tools: Optional[List[Tool]] = None,
    ) -> ChatResponse:
        """
        Send a chat request to your LLM provider.

        Args:
            messages: Conversation history
            tools: Available tools, when provided

        Returns:
            ChatResponse with content and optional tool_calls
        """

    def run(self) -> None:
        """Read JSON requests from stdin, process them, and write JSON responses."""
        _configure_stdio()
        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue

                try:
                    request = json.loads(line)
                    response = self._handle_request(request)
                    self._send_response(response)
                except json.JSONDecodeError as exc:
                    self._send_error(f"Invalid JSON: {exc}")
                except Exception as exc:
                    sys.stderr.write(f"ERROR: {traceback.format_exc()}\n")
                    sys.stderr.flush()
                    self._send_error(f"Error processing request: {exc}")
        except KeyboardInterrupt:
            pass

    def _handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle an incoming request and route to the correct method."""
        request_type = request.get("type")

        if request_type == "init":
            return {"status": "success", "data": {"initialized": True}}

        if request_type == "chat":
            messages_raw = request.get("messages") or []
            messages = [Message.from_dict(message) for message in messages_raw]

            tools_raw = request.get("tools")
            tools = [Tool.from_dict(tool) for tool in tools_raw] if tools_raw else None

            result = self.chat(messages, tools)
            return {"status": "success", "data": result.to_dict()}

        return {"status": "error", "message": f"Unknown request type: {request_type}"}

    def _send_response(self, response: Dict[str, Any]) -> None:
        """Send a JSON response to stdout."""
        print(json.dumps(response), flush=True)

    def _send_error(self, message: str) -> None:
        """Send an error response to stdout."""
        self._send_response({"status": "error", "message": message})
