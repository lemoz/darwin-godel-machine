"""
OpenAI-compatible chat completions handler implementation.

This provider is intentionally generic: it works with OpenAI itself and with
providers that expose the OpenAI Chat Completions API, such as OpenRouter or
Moonshot/Kimi.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from openai import (
    APIStatusError as OpenAIAPIStatusError,
    AsyncOpenAI,
    AuthenticationError as OpenAIAuthError,
    OpenAIError,
    RateLimitError as OpenAIRateLimitError,
)

from ..api_handler import (
    ApiHandler,
    CompletionRequest,
    CompletionResponse,
    Message,
    MessageRole,
    ToolCall,
    ApiError,
    RateLimitError,
    AuthenticationError,
)

logger = logging.getLogger(__name__)


class OpenAICompatibleHandler(ApiHandler):
    """
    OpenAI Chat Completions-compatible implementation of the ApiHandler interface.

    Message layout contract
    -----------------------
    * SYSTEM, USER, and ASSISTANT messages map directly to OpenAI roles.
    * ASSISTANT messages that carry tool calls store them in
      ``message.metadata["tool_calls"]`` as ``{id, name, input}`` dictionaries.
    * TOOL messages should carry ``message.metadata["tool_use_id"]`` so they can
      become OpenAI ``role=tool`` turns. Missing tool ids fall back to user text
      so older conversations remain serializable.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = (
            config.get("base_url")
            or config.get("baseURL")
            or "https://api.openai.com/v1"
        )
        self.extra_headers = config.get("extra_headers")
        self.extra_body = config.get("extra_body")

        self.validate_config()
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            max_retries=5,
        )

    async def get_completion(self, request: CompletionRequest) -> CompletionResponse:
        """Get a completion from an OpenAI-compatible Chat Completions API."""
        try:
            messages = self.format_messages(request.messages)
            if request.system_prompt:
                messages = [
                    {"role": "system", "content": request.system_prompt},
                    *messages,
                ]

            temperature = (
                request.temperature if request.temperature is not None else self.temperature
            )
            max_tokens = (
                request.max_tokens if request.max_tokens is not None else self.max_tokens
            )

            api_params: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if request.tools:
                api_params["tools"] = self.format_tools(request.tools)
            if isinstance(self.extra_headers, dict) and self.extra_headers:
                api_params["extra_headers"] = self.extra_headers
            if isinstance(self.extra_body, dict) and self.extra_body:
                api_params["extra_body"] = self.extra_body

            logger.info(
                "Starting OpenAI-compatible API request "
                f"(timeout: {self.timeout}s, model: {self.model}, base_url: {self.base_url})"
            )
            start_time = time.time()
            try:
                response = await asyncio.wait_for(
                    self.client.chat.completions.create(**api_params),
                    timeout=float(self.timeout),
                )
            except asyncio.TimeoutError as exc:
                raise ApiError(
                    f"OpenAI-compatible request timed out after {self.timeout}s",
                    provider="openai_compatible",
                ) from exc
            elapsed_time = time.time() - start_time
            logger.info(
                "OpenAI-compatible API request completed successfully "
                f"in {elapsed_time:.2f}s"
            )
            return self.parse_response(response)

        except ApiError:
            raise
        except OpenAIAuthError as exc:
            raise AuthenticationError(
                f"OpenAI-compatible authentication failed: {str(exc)}",
                provider="openai_compatible",
            ) from exc
        except OpenAIRateLimitError as exc:
            raise RateLimitError(
                f"OpenAI-compatible rate limit exceeded: {str(exc)}",
                provider="openai_compatible",
            ) from exc
        except OpenAIAPIStatusError as exc:
            raise ApiError(
                f"OpenAI-compatible API status error: {str(exc)}",
                status_code=exc.status_code,
                provider="openai_compatible",
            ) from exc
        except OpenAIError as exc:
            raise ApiError(
                f"OpenAI-compatible API error: {str(exc)}",
                provider="openai_compatible",
            ) from exc
        except Exception as exc:
            error_str = str(exc).lower()
            if "rate" in error_str or "quota" in error_str:
                raise RateLimitError(
                    f"OpenAI-compatible rate limit exceeded: {str(exc)}",
                    provider="openai_compatible",
                ) from exc
            if "authentication" in error_str or "api key" in error_str:
                raise AuthenticationError(
                    f"OpenAI-compatible authentication failed: {str(exc)}",
                    provider="openai_compatible",
                ) from exc
            raise ApiError(
                f"OpenAI-compatible API error: {str(exc)}",
                provider="openai_compatible",
            ) from exc

    def format_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert internal messages to OpenAI Chat Completions format."""
        formatted: List[Dict[str, Any]] = []
        role_mapping = {
            MessageRole.SYSTEM: "system",
            MessageRole.USER: "user",
            MessageRole.ASSISTANT: "assistant",
        }

        for message in messages:
            if message.role == MessageRole.TOOL:
                tool_call_id = (
                    message.metadata.get("tool_use_id") if message.metadata else None
                )
                if tool_call_id:
                    formatted.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": message.content or "",
                        }
                    )
                else:
                    formatted.append(
                        {
                            "role": "user",
                            "content": f"Tool result:\n{message.content or ''}",
                        }
                    )
                continue

            formatted_message: Dict[str, Any] = {
                "role": role_mapping.get(message.role, "user"),
                "content": message.content or "",
            }

            tool_calls_meta: Optional[List[Dict[str, Any]]] = (
                message.metadata.get("tool_calls") if message.metadata else None
            )
            if message.role == MessageRole.ASSISTANT and tool_calls_meta:
                formatted_message["tool_calls"] = [
                    {
                        "id": tool_call["id"],
                        "type": "function",
                        "function": {
                            "name": tool_call["name"],
                            "arguments": json.dumps(tool_call["input"]),
                        },
                    }
                    for tool_call in tool_calls_meta
                ]
                if not formatted_message["content"]:
                    formatted_message["content"] = None

            formatted.append(formatted_message)

        return formatted

    def parse_response(self, response: Any) -> CompletionResponse:
        """Parse an OpenAI-compatible response into the standard format."""
        try:
            choices = self._get(response, "choices", [])
            if not choices:
                raise ApiError("OpenAI-compatible response did not include choices")

            choice = choices[0]
            message = self._get(choice, "message")
            content = self._get(message, "content") or ""
            tool_calls: List[ToolCall] = []

            for raw_tool_call in self._get(message, "tool_calls", []) or []:
                function = self._get(raw_tool_call, "function", {})
                raw_arguments = self._get(function, "arguments", "{}")
                parameters = self._parse_tool_arguments(raw_arguments)
                tool_calls.append(
                    ToolCall(
                        tool_name=self._get(function, "name", "unknown"),
                        parameters=parameters,
                        call_id=self._get(raw_tool_call, "id"),
                    )
                )

            if not content and not tool_calls:
                content = "No response generated"

            usage = None
            raw_usage = self._get(response, "usage")
            if raw_usage:
                usage = {
                    "prompt_tokens": int(self._get(raw_usage, "prompt_tokens", 0) or 0),
                    "completion_tokens": int(
                        self._get(raw_usage, "completion_tokens", 0) or 0
                    ),
                    "total_tokens": int(self._get(raw_usage, "total_tokens", 0) or 0),
                }

            return CompletionResponse(
                content=content,
                tool_calls=tool_calls,
                usage=usage,
                model=self._get(response, "model", self.model),
                finish_reason=self._get(choice, "finish_reason"),
            )

        except ApiError:
            raise
        except Exception as exc:
            raise ApiError(
                f"Failed to parse OpenAI-compatible response: {str(exc)}",
                provider="openai_compatible",
            ) from exc

    def format_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert standard tool definitions to OpenAI function-tool format."""
        formatted_tools = []
        for tool in tools:
            parameters = tool.get(
                "parameters",
                {"type": "object", "properties": {}, "required": []},
            )
            if "type" not in parameters:
                parameters = {"type": "object", **parameters}

            formatted_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.get("name", "unknown"),
                        "description": tool.get("description", ""),
                        "parameters": parameters,
                    },
                }
            )
        return formatted_tools

    def validate_config(self) -> bool:
        """Validate OpenAI-compatible configuration without stale model allowlists."""
        super().validate_config()
        if not isinstance(self.base_url, str) or not self.base_url.startswith(
            ("https://", "http://")
        ):
            raise ValueError(f"Invalid OpenAI-compatible base_url: {self.base_url}")
        return True

    @staticmethod
    def _get(value: Any, key: str, default: Any = None) -> Any:
        """Read either dict keys or object attributes from SDK/fake responses."""
        if isinstance(value, dict):
            return value.get(key, default)
        return getattr(value, key, default)

    @staticmethod
    def _parse_tool_arguments(raw_arguments: Any) -> Dict[str, Any]:
        if raw_arguments is None:
            return {}
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if not isinstance(raw_arguments, str):
            return {"arguments": raw_arguments}
        try:
            parsed = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError:
            return {"arguments": raw_arguments}
        if isinstance(parsed, dict):
            return parsed
        return {"arguments": parsed}
