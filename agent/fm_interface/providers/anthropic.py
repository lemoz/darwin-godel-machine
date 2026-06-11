"""
Anthropic API handler implementation.

This module provides the concrete implementation for Anthropic's Claude models,
handling the specific API format and response parsing required for Claude.
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Any, Optional, Tuple
from anthropic import AsyncAnthropic, AuthenticationError as AnthropicAuthError
from anthropic.types import Message as AnthropicMessage, MessageParam
from anthropic.types import ContentBlock, TextBlock, ToolUseBlock

from ..api_handler import (
    ApiHandler, CompletionRequest, CompletionResponse, Message, MessageRole,
    ToolCall, ApiError, RateLimitError, AuthenticationError
)

logger = logging.getLogger(__name__)

# Known deprecated model family prefixes — emit a warning, not an error.
_DEPRECATED_PREFIXES = ("claude-3-", "claude-2", "claude-instant")


class AnthropicHandler(ApiHandler):
    """
    Anthropic-specific implementation of the ApiHandler interface.

    Handles the specifics of Anthropic's Claude API, including message formatting,
    tool calling, and response parsing.

    Message layout contract
    -----------------------
    * SYSTEM-role messages are extracted and passed as the top-level ``system``
      parameter; they are never emitted into the ``messages`` array.
    * ASSISTANT messages that carry tool calls store the tool-call blocks in
      ``message.metadata["tool_calls"]`` as a list of dicts with keys
      ``{id, name, input}``.  ``format_messages`` reconstructs them as
      ``{"type": "tool_use", ...}`` blocks inside the assistant content array.
    * TOOL-role messages carry ``message.metadata["tool_use_id"]``.  Consecutive
      TOOL messages are merged into a single user message containing multiple
      ``tool_result`` blocks so that roles always alternate.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Anthropic handler.

        Args:
            config: Configuration dictionary containing Anthropic-specific settings
        """
        super().__init__(config)

        # Initialize the Anthropic client with timeout configuration
        self.client = AsyncAnthropic(
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=5,
        )

        # Validate configuration
        self.validate_config()

    async def get_completion(self, request: CompletionRequest) -> CompletionResponse:
        """
        Get a completion from Anthropic Claude.

        Args:
            request: Standardized completion request

        Returns:
            CompletionResponse: Standardized response
        """
        try:
            # Extract system text and non-system messages separately.
            system_text, non_system_messages = self._extract_system(request.messages)

            # Format non-system messages for Anthropic.
            messages = self.format_messages(non_system_messages)

            # Fix (c): treat 0.0 as a valid temperature (not falsy).
            temperature = (
                request.temperature if request.temperature is not None else self.temperature
            )
            max_tokens = (
                request.max_tokens if request.max_tokens is not None else self.max_tokens
            )

            # Build the API request.
            api_params: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }

            # Merge system text: prefer explicit request.system_prompt, then extracted.
            merged_system = request.system_prompt or system_text
            if merged_system:
                api_params["system"] = merged_system

            # Add tools if provided.
            if request.tools:
                api_params["tools"] = self.format_tools(request.tools)

            logger.info(
                f"Starting Anthropic API request (timeout: {self.timeout}s, model: {self.model})"
            )
            start_time = time.time()

            try:
                response = await self.client.messages.create(**api_params)
                elapsed_time = time.time() - start_time
                logger.info(
                    f"Anthropic API request completed successfully in {elapsed_time:.2f}s"
                )
            except Exception as api_exception:
                elapsed_time = time.time() - start_time
                logger.warning(
                    f"Anthropic API request failed after {elapsed_time:.2f}s: "
                    f"{str(api_exception)}"
                )
                raise

            return self.parse_response(response)

        except AnthropicAuthError as e:
            raise AuthenticationError(
                f"Anthropic authentication failed: {str(e)}",
                provider="anthropic",
            )
        except Exception as e:
            error_str = str(e).lower()
            if "rate" in error_str or "quota" in error_str:
                raise RateLimitError(
                    f"Anthropic rate limit exceeded: {str(e)}",
                    provider="anthropic",
                )
            else:
                raise ApiError(
                    f"Anthropic API error: {str(e)}",
                    provider="anthropic",
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_system(
        self, messages: List[Message]
    ) -> Tuple[Optional[str], List[Message]]:
        """
        Split SYSTEM messages from the rest.

        Returns (system_text_or_None, remaining_messages).  Multiple SYSTEM
        messages are joined with double newlines.
        """
        system_parts: List[str] = []
        rest: List[Message] = []
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                if msg.content:
                    system_parts.append(msg.content)
            else:
                rest.append(msg)
        system_text = "\n\n".join(system_parts) if system_parts else None
        return system_text, rest

    def format_messages(self, messages: List[Message]) -> List[MessageParam]:
        """
        Convert internal (non-SYSTEM) messages to Anthropic's wire format.

        Rules:
        * ASSISTANT messages with ``metadata["tool_calls"]`` get a structured
          content array containing text blocks (if any) followed by tool_use
          blocks.
        * Consecutive TOOL-role messages are batched into **one** user message
          with multiple ``tool_result`` content blocks.
        * Consecutive user-role messages are merged into a single user message
          so that roles strictly alternate user/assistant.

        Args:
            messages: List of non-SYSTEM messages in standard internal format.

        Returns:
            List of MessageParam dicts ready for the Anthropic API.
        """
        # --- Pass 1: build a raw list that may contain consecutive user msgs ---
        raw: List[Dict[str, Any]] = []
        pending_tool_results: List[Dict[str, Any]] = []

        def flush_tool_results() -> None:
            """Emit batched tool results as a single user message."""
            if pending_tool_results:
                raw.append({
                    "role": "user",
                    "content": list(pending_tool_results),
                })
                pending_tool_results.clear()

        for message in messages:
            if message.role == MessageRole.TOOL:
                # Accumulate tool results to merge them into one user message.
                tool_use_id = (
                    message.metadata.get("tool_use_id") if message.metadata else None
                )
                if tool_use_id:
                    pending_tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": message.content or "",
                    })
                else:
                    # No id — fall back to plain text appended as a text block.
                    pending_tool_results.append({
                        "type": "text",
                        "text": message.content or "",
                    })
                continue

            # Any non-TOOL message: flush pending tool results first.
            flush_tool_results()

            if message.role == MessageRole.ASSISTANT:
                # Build structured content for assistant messages.
                content_blocks: List[Dict[str, Any]] = []

                # Optional leading text block.
                text = message.content.strip() if message.content else ""
                if text:
                    content_blocks.append({"type": "text", "text": text})

                # Tool-use blocks from metadata.
                tool_calls_meta: Optional[List[Dict[str, Any]]] = (
                    message.metadata.get("tool_calls") if message.metadata else None
                )
                if tool_calls_meta:
                    for tc in tool_calls_meta:
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": tc["input"],
                        })

                if not content_blocks:
                    # Anthropic requires non-empty content for assistant turns.
                    content_blocks.append({"type": "text", "text": "..."})

                raw.append({"role": "assistant", "content": content_blocks})

            else:
                # USER role (and any unexpected role defaults to user).
                content = message.content.strip() if message.content else ""
                if content:
                    raw.append({"role": "user", "content": content})

        # Flush any trailing tool results.
        flush_tool_results()

        # --- Pass 2: merge consecutive same-role messages ---
        # The Anthropic API requires strict role alternation.  Consecutive user
        # messages are merged by combining their content into a single list of
        # blocks.  Consecutive assistant messages (unusual) are also merged.
        def _to_blocks(content: Any) -> List[Dict[str, Any]]:
            """Normalise content to a list of blocks."""
            if isinstance(content, list):
                return content
            if isinstance(content, str):
                return [{"type": "text", "text": content}]
            return []

        formatted: List[Dict[str, Any]] = []
        for msg in raw:
            if formatted and formatted[-1]["role"] == msg["role"]:
                # Merge into the previous message.
                prev = formatted[-1]
                prev["content"] = _to_blocks(prev["content"]) + _to_blocks(msg["content"])
            else:
                formatted.append(dict(msg))  # shallow copy to avoid mutating raw

        return formatted

    def parse_response(self, response: AnthropicMessage) -> CompletionResponse:
        """
        Parse Anthropic response into standard format.

        Args:
            response: Raw Anthropic response

        Returns:
            CompletionResponse: Standardized response
        """
        try:
            content_parts: List[str] = []
            tool_calls: List[ToolCall] = []

            for block in response.content:
                if isinstance(block, TextBlock):
                    content_parts.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    tool_calls.append(ToolCall(
                        tool_name=block.name,
                        parameters=block.input,
                        call_id=block.id,
                    ))

            content = "\n".join(content_parts).strip()
            if not content:
                content = "No response generated"

            usage = None
            if hasattr(response, "usage") and response.usage:
                usage = {
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": (
                        response.usage.input_tokens + response.usage.output_tokens
                    ),
                }

            return CompletionResponse(
                content=content,
                tool_calls=tool_calls,
                usage=usage,
                model=response.model,
                finish_reason=response.stop_reason,
            )

        except Exception as e:
            raise ApiError(
                f"Failed to parse Anthropic response: {str(e)}",
                provider="anthropic",
            )

    def format_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert standard tool definitions to Anthropic format.

        Args:
            tools: List of tool definitions in standard format

        Returns:
            List of tools in Anthropic format
        """
        formatted_tools = []

        for tool in tools:
            formatted_tool = {
                "name": tool.get("name", "unknown"),
                "description": tool.get("description", ""),
                "input_schema": tool.get(
                    "parameters",
                    {"type": "object", "properties": {}, "required": []},
                ),
            }

            if "type" not in formatted_tool["input_schema"]:
                formatted_tool["input_schema"]["type"] = "object"

            formatted_tools.append(formatted_tool)

        return formatted_tools

    def validate_config(self) -> bool:
        """
        Validate Anthropic-specific configuration.

        Fix (d): prefix check only; emit a warning for known-deprecated families
        instead of maintaining a stale allowlist.

        Returns:
            bool: True if configuration is valid
        """
        super().validate_config()

        if not self.model.startswith("claude-"):
            raise ValueError(f"Invalid Anthropic model name: {self.model}")

        if any(self.model.startswith(dep) for dep in _DEPRECATED_PREFIXES):
            logger.warning(
                f"Model '{self.model}' matches a known-deprecated Anthropic family "
                f"({', '.join(_DEPRECATED_PREFIXES)}). Consider upgrading to a current model."
            )

        return True