"""AWS Bedrock hook example built on top of the llm_hook_sdk package."""

from __future__ import annotations

import base64
import logging
import os
from typing import Any, Dict, List, Optional

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from llm_hook_sdk import (
    ChatResponse,
    ContentBlock,
    LLMHookBase,
    Message,
    MessageRole,
    StopReason,
    Tool,
    ToolCall,
)

LOGGER = logging.getLogger(__name__)


class AWSBedrockHook(LLMHookBase):
    """AWS Bedrock implementation using the Converse API."""

    # ── Configuration ──────────────────────────────────────────────────────────
    MODEL_ID    = "eu.anthropic.claude-sonnet-4-6"
    REGION      = "eu-central-1"
    TEMPERATURE = 0.0
    # ───────────────────────────────────────────────────────────────────────────

    def __init__(self):
        region = os.getenv("AWS_REGION", self.REGION)
        aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        aws_session_token = os.getenv("AWS_SESSION_TOKEN")

        boto_config = BotoConfig(
            region_name=region,
            read_timeout=7200,
        )

        client_args = {
            "service_name": "bedrock-runtime",
            "region_name": region,
            "config": boto_config,
        }
        if aws_access_key and aws_secret_key:
            client_args["aws_access_key_id"] = aws_access_key
            client_args["aws_secret_access_key"] = aws_secret_key
            if aws_session_token:
                client_args["aws_session_token"] = aws_session_token

        self.client = boto3.client(**client_args)

    def chat(
        self,
        messages: List[Message],
        tools: Optional[List[Tool]] = None,
    ) -> ChatResponse:
        """Send a chat request to AWS Bedrock using the Converse API."""
        converse_messages, system_prompts = self._build_converse_messages(messages)

        converse_params: Dict[str, Any] = {
            "modelId": self.MODEL_ID,
            "messages": converse_messages,
            "inferenceConfig": {
                "temperature": self.TEMPERATURE
            },
        }
        if system_prompts:
            converse_params["system"] = system_prompts
        if tools:
            converse_params["toolConfig"] = self._convert_tools(tools)

        try:
            response = self.client.converse(**converse_params)
        except ClientError as exc:
            raise Exception(f"AWS Bedrock Converse API error: {exc}") from exc

        return self._parse_response(response)

    def _build_converse_messages(
        self, messages: List[Message]
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Convert SDK messages into Bedrock Converse format.

        Returns a tuple of (converse_messages, system_prompts).
        """
        converse_messages: List[Dict[str, Any]] = []
        system_prompts: List[Dict[str, Any]] = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                for block in msg.content or []:
                    if block.get("type") == "text":
                        system_prompts.append({"text": block["text"]})

            elif msg.role == MessageRole.USER:
                converse_messages.append(
                    {
                        "role": "user",
                        "content": self._convert_content_blocks(msg.content or []),
                    }
                )

            elif msg.role == MessageRole.ASSISTANT:
                content = self._convert_content_blocks(msg.content or [])
                if msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        content.append(
                            {
                                "toolUse": {
                                    "toolUseId": tool_call.id,
                                    "name": tool_call.name,
                                    "input": tool_call.arguments,
                                }
                            }
                        )
                if content:
                    converse_messages.append({"role": "assistant", "content": content})

            elif msg.role == MessageRole.TOOL:
                content = []
                if msg.tool_results:
                    for tool_result in msg.tool_results:
                        tool_result_block: Dict[str, Any] = {
                            "toolUseId": tool_result.tool_call_id,
                            "content": self._convert_content_blocks(
                                tool_result.content or []
                            ),
                            "status": "error" if tool_result.error else "success",
                        }
                        content.append({"toolResult": tool_result_block})
                if content:
                    converse_messages.append({"role": "user", "content": content})

        return converse_messages, system_prompts

    def _convert_content_blocks(self, content_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert protocol content blocks into Bedrock Converse content blocks."""
        bedrock_content = []
        for block in content_blocks:
            block_type = block.get("type", "")
            if block_type == "text":
                bedrock_content.append({"text": block.get("text", "")})
            elif block_type == "image":
                fmt = self._mime_to_image_format(block.get("mimeType", ""))
                if fmt is not None:
                    bedrock_content.append({
                        "image": {
                            "format": fmt,
                            "source": {"bytes": base64.b64decode(block["data"])},
                        }
                    })
                else:
                    LOGGER.warning("Skipping image block with unsupported mimeType: %s", block.get("mimeType"))
            elif block_type == "structured":
                bedrock_content.append({"json": block.get("data", {})})
            elif block_type == "resource":
                data = block.get("data")
                mime_type = block.get("mimeType", "")
                uri = block.get("uri") or "resource"
                doc_format = self._mime_to_document_format(mime_type)
                if doc_format is not None:
                    bedrock_content.append({
                        "document": {
                            "format": doc_format,
                            "name": uri,
                            "source": {"bytes": base64.b64decode(data)},
                        }
                    })
                else:
                    LOGGER.warning("Skipping resource block with unsupported mimeType: %s", mime_type)
            else:
                LOGGER.warning(
                    "Skipping unsupported content block type: %s",
                    block_type or "unknown",
                )
        return bedrock_content

    def _mime_to_image_format(self, mime_type: str) -> Optional[str]:
        """Return the Bedrock image format string for a MIME type, or None if unsupported."""
        formats = {
            "image/png": "png",
            "image/jpeg": "jpeg",
            "image/gif": "gif",
            "image/webp": "webp",
        }
        return formats.get(mime_type)

    def _mime_to_document_format(self, mime_type: str) -> Optional[str]:
        """Return the Bedrock document format string for a MIME type, or None if unsupported."""
        formats = {
            "text/plain": "txt",
            "text/html": "html",
            "text/markdown": "md",
            "text/csv": "csv",
            "application/pdf": "pdf",
            "application/msword": "doc",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
            "application/vnd.ms-excel": "xls",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        }
        return formats.get(mime_type)

    def _convert_tools(self, tools: List[Tool]) -> Dict[str, Any]:
        """Convert SDK Tool objects into Bedrock toolConfig payloads."""
        bedrock_tools = []
        for tool in tools:
            tool_spec: Dict[str, Any] = {
                "toolSpec": {
                    "name": tool.name,
                    "description": tool.description,
                }
            }
            if tool.input_schema:
                tool_spec["toolSpec"]["inputSchema"] = {"json": tool.input_schema}
            bedrock_tools.append(tool_spec)

        return {"tools": bedrock_tools}

    def _parse_response(self, response: Dict[str, Any]) -> ChatResponse:
        """Parse a raw Bedrock Converse response into a ChatResponse."""
        content = []
        tool_calls = []

        if "output" in response and "message" in response["output"]:
            message_content = response["output"]["message"].get("content", [])
            for block in message_content:
                if "text" in block:
                    content.append({"type": "text", "text": block["text"]})
                elif "toolUse" in block:
                    tool_use = block["toolUse"]
                    tool_calls.append(
                        ToolCall(
                            id=tool_use.get("toolUseId", ""),
                            name=tool_use.get("name", ""),
                            arguments=tool_use.get("input", {}),
                        )
                    )
                else:
                    content.append(block)

        usage = response.get("usage", {})
        prompt_tokens = usage.get("inputTokens", 0)
        completion_tokens = usage.get("outputTokens", 0)
        stop_reason = response.get("stopReason")

        return ChatResponse(
            content=content,
            stop_reason=self._map_stop_reason(stop_reason),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            tool_calls=tool_calls if tool_calls else None,
        )

    def _map_stop_reason(self, aws_stop_reason: Optional[str]) -> StopReason:
        """Map the Bedrock stop reason into the SDK StopReason enum."""
        if not aws_stop_reason:
            return StopReason.COMPLETE

        mapping = {
            "end_turn": StopReason.COMPLETE,
            "max_tokens": StopReason.MAX_TOKENS,
            "tool_use": StopReason.TOOL_USE,
        }
        return mapping.get(aws_stop_reason, StopReason.OTHER)


if __name__ == "__main__":
    AWSBedrockHook().run()
