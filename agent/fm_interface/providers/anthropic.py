"""
Anthropic API handler implementation.

This module provides the concrete implementation for Anthropic's Claude models,
handling the specific API format and response parsing required for Claude.
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Any, Optional
from anthropic import AsyncAnthropic, AuthenticationError as AnthropicAuthError
from anthropic.types import Message as AnthropicMessage, MessageParam
from anthropic.types import ContentBlock, TextBlock, ToolUseBlock

from ..api_handler import (
    ApiHandler, CompletionRequest, CompletionResponse, Message, MessageRole,
    ToolCall, ApiError, RateLimitError, AuthenticationError
)

logger = logging.getLogger(__name__)


class AnthropicHandler(ApiHandler):
    """
    Anthropic-specific implementation of the ApiHandler interface.
    
    Handles the specifics of Anthropic's Claude API, including message formatting,
    tool calling, and response parsing.
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
            max_retries=5  # Increased from 3 to 5 for better resilience
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
            # Format messages for Anthropic
            messages = self.format_messages(request.messages)
            
            # Build the API request
            api_params = {
                "model": self.model,
                "messages": messages,
                "max_tokens": request.max_tokens or self.max_tokens,
                "temperature": request.temperature or self.temperature,
            }
            
            # Add system prompt if provided
            if request.system_prompt:
                api_params["system"] = request.system_prompt
            
            # Add tools if provided
            if request.tools:
                api_params["tools"] = self.format_tools(request.tools)
            
            # Make the API call with detailed logging
            logger.info(f"Starting Anthropic API request (timeout: {self.timeout}s, model: {self.model})")
            start_time = time.time()
            
            try:
                response = await self.client.messages.create(**api_params)
                elapsed_time = time.time() - start_time
                logger.info(f"Anthropic API request completed successfully in {elapsed_time:.2f}s")
            except Exception as api_exception:
                elapsed_time = time.time() - start_time
                logger.warning(f"Anthropic API request failed after {elapsed_time:.2f}s: {str(api_exception)}")
                # Don't re-raise here - let the outer exception handler deal with retries
                raise
            
            # Parse and return the response
            return self.parse_response(response)
            
        except AnthropicAuthError as e:
            raise AuthenticationError(
                f"Anthropic authentication failed: {str(e)}", 
                provider="anthropic"
            )
        except Exception as e:
            error_str = str(e).lower()
            if "rate" in error_str or "quota" in error_str:
                raise RateLimitError(
                    f"Anthropic rate limit exceeded: {str(e)}", 
                    provider="anthropic"
                )
            else:
                raise ApiError(
                    f"Anthropic API error: {str(e)}", 
                    provider="anthropic"
                )
    
    def format_messages(self, messages: List[Message]) -> List[MessageParam]:
        """
        Convert internal message format to Anthropic format.
        
        Args:
            messages: List of messages in standard internal format
            
        Returns:
            List of messages in Anthropic format
        """
        formatted = []
        
        for message in messages:
            # Map our roles to Anthropic roles
            role_mapping = {
                MessageRole.SYSTEM: "user",  # System messages are handled separately in Anthropic
                MessageRole.USER: "user",
                MessageRole.ASSISTANT: "assistant",
                MessageRole.TOOL: "user"  # Tool results are user messages with tool_use_id
            }
            
            role = role_mapping.get(message.role, "user")
            
            # Handle tool result messages specially
            if message.role == MessageRole.TOOL and message.metadata:
                tool_use_id = message.metadata.get("tool_use_id")
                if tool_use_id:
                    formatted.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": message.content
                        }]
                    })
                    continue
            
            # Regular text messages - ensure content is not empty
            content = message.content.strip() if message.content else ""
            if content or role == "assistant":  # Allow empty content for assistant messages
                formatted.append({
                    "role": role,
                    "content": content or "..."  # Use placeholder for empty content
                })
        
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
            # Extract content and tool calls
            content_parts = []
            tool_calls = []
            
            for block in response.content:
                if isinstance(block, TextBlock):
                    content_parts.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    tool_calls.append(ToolCall(
                        tool_name=block.name,
                        parameters=block.input,
                        call_id=block.id
                    ))
            
            # Join text content and clean it
            content = "\n".join(content_parts).strip()
            
            # Ensure content is not empty
            if not content:
                content = "No response generated"
            
            # Extract usage information
            usage = None
            if hasattr(response, 'usage') and response.usage:
                usage = {
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens
                }
            
            return CompletionResponse(
                content=content,
                tool_calls=tool_calls,
                usage=usage,
                model=response.model,
                finish_reason=response.stop_reason
            )
            
        except Exception as e:
            raise ApiError(
                f"Failed to parse Anthropic response: {str(e)}", 
                provider="anthropic"
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
            # Anthropic expects a specific tool format
            formatted_tool = {
                "name": tool.get("name", "unknown"),
                "description": tool.get("description", ""),
                "input_schema": tool.get("parameters", {
                    "type": "object",
                    "properties": {},
                    "required": []
                })
            }
            
            # Ensure the input schema has the correct structure
            if "type" not in formatted_tool["input_schema"]:
                formatted_tool["input_schema"]["type"] = "object"
            
            formatted_tools.append(formatted_tool)
        
        return formatted_tools
    
    def validate_config(self) -> bool:
        """
        Validate Anthropic-specific configuration.
        
        Returns:
            bool: True if configuration is valid
        """
        super().validate_config()
        
        # Validate model name
        valid_models = [
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
            "claude-3-5-sonnet-20241022",
            "claude-3-7-sonnet",  # Claude 3.7 Sonnet
            "claude-sonnet-4-20250514",  # Claude 4 Sonnet
            "claude-opus-4-20250514",    # Claude 4 Opus
            "claude-2.1",
            "claude-2.0",
            "claude-instant-1.2"
        ]
        
        if not any(self.model.startswith(prefix) for prefix in ["claude-"]):
            raise ValueError(f"Invalid Anthropic model name: {self.model}")
        
        return True