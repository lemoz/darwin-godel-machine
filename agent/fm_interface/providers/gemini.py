"""
Gemini API handler implementation.

This module provides the concrete implementation for Google's Gemini models,
handling the specific API format and response parsing required for Gemini.
"""

import asyncio
import json
import re
from typing import Dict, List, Any, Optional
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from ..api_handler import (
    ApiHandler, CompletionRequest, CompletionResponse, Message, MessageRole,
    ToolCall, ApiError, RateLimitError, AuthenticationError
)


class GeminiHandler(ApiHandler):
    """
    Gemini-specific implementation of the ApiHandler interface.
    
    Handles the specifics of Google's Gemini API, including message formatting,
    tool calling, and response parsing.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Gemini handler.
        
        Args:
            config: Configuration dictionary containing Gemini-specific settings
        """
        super().__init__(config)
        
        # Configure the Gemini client
        genai.configure(api_key=self.api_key)
        
        # Initialize the model
        self.client = genai.GenerativeModel(
            model_name=self.model,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=self.max_tokens,
                temperature=self.temperature,
                candidate_count=1,
            ),
            safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
        )
        
        self.validate_config()
    
    async def get_completion(self, request: CompletionRequest) -> CompletionResponse:
        """
        Get a completion from Gemini.
        
        Args:
            request: Standardized completion request
            
        Returns:
            CompletionResponse: Standardized response
        """
        try:
            # Format messages for Gemini
            formatted_messages = self.format_messages(request.messages)
            
            # Build the prompt from messages
            prompt_parts = []
            for msg in formatted_messages:
                if msg["role"] == "user":
                    prompt_parts.append(f"User: {msg['content']}")
                elif msg["role"] == "assistant":
                    prompt_parts.append(f"Assistant: {msg['content']}")
                elif msg["role"] == "system":
                    prompt_parts.append(f"System: {msg['content']}")
            
            prompt = "\n\n".join(prompt_parts)
            
            # Add system prompt if provided
            if request.system_prompt:
                prompt = f"System: {request.system_prompt}\n\n{prompt}"
            
            # Add tool information to prompt if tools are provided
            if request.tools:
                tool_descriptions = self._format_tools_for_prompt(request.tools)
                prompt = f"{prompt}\n\n{tool_descriptions}"
            
            # Generate content
            response = await asyncio.to_thread(
                self.client.generate_content, 
                prompt
            )
            
            # Parse the response
            return self.parse_response(response)
            
        except Exception as e:
            if "quota" in str(e).lower() or "rate" in str(e).lower():
                raise RateLimitError(f"Gemini rate limit exceeded: {str(e)}", provider="gemini")
            elif "authentication" in str(e).lower() or "api_key" in str(e).lower():
                raise AuthenticationError(f"Gemini authentication failed: {str(e)}", provider="gemini")
            else:
                raise ApiError(f"Gemini API error: {str(e)}", provider="gemini")
    
    def format_messages(self, messages: List[Message]) -> List[Dict[str, str]]:
        """
        Convert internal message format to Gemini format.
        
        Args:
            messages: List of messages in standard internal format
            
        Returns:
            List of dictionaries in Gemini format
        """
        formatted = []
        
        for message in messages:
            # Map our roles to Gemini roles
            role_mapping = {
                MessageRole.SYSTEM: "system",
                MessageRole.USER: "user", 
                MessageRole.ASSISTANT: "assistant",
                MessageRole.TOOL: "user"  # Tool results are treated as user messages in Gemini
            }
            
            formatted.append({
                "role": role_mapping.get(message.role, "user"),
                "content": message.content
            })
        
        return formatted
    
    def parse_response(self, response: Any) -> CompletionResponse:
        """
        Parse Gemini response into standard format.
        
        Args:
            response: Raw Gemini response
            
        Returns:
            CompletionResponse: Standardized response
        """
        try:
            # Extract text content - handle both simple and multi-part responses
            content = ""
            try:
                # Try simple text accessor first
                content = response.text if response.text else ""
            except Exception:
                # Fall back to multi-part response handling
                if hasattr(response, 'candidates') and response.candidates:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                        # Concatenate all text parts
                        text_parts = []
                        for part in candidate.content.parts:
                            if hasattr(part, 'text'):
                                text_parts.append(part.text)
                        content = "\n".join(text_parts)
            
            # Parse tool calls from content using XML-like format
            tool_calls = self._extract_tool_calls(content)
            
            # Extract usage information if available
            usage = None
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = {
                    "prompt_tokens": getattr(response.usage_metadata, 'prompt_token_count', 0),
                    "completion_tokens": getattr(response.usage_metadata, 'candidates_token_count', 0),
                    "total_tokens": getattr(response.usage_metadata, 'total_token_count', 0)
                }
            
            return CompletionResponse(
                content=content,
                tool_calls=tool_calls,
                usage=usage,
                model=self.model,
                finish_reason=getattr(response, 'finish_reason', None)
            )
            
        except Exception as e:
            raise ApiError(f"Failed to parse Gemini response: {str(e)}", provider="gemini")
    
    def format_tools(self, tools: List[Dict[str, Any]]) -> Any:
        """
        Convert standard tool definitions to Gemini format.
        Note: Gemini doesn't have native tool calling, so we include tool descriptions in the prompt.
        
        Args:
            tools: List of tool definitions in standard format
            
        Returns:
            String description of tools for inclusion in prompt
        """
        return self._format_tools_for_prompt(tools)
    
    def _format_tools_for_prompt(self, tools: List[Dict[str, Any]]) -> str:
        """
        Format tool definitions for inclusion in the prompt.
        
        Args:
            tools: List of tool definitions
            
        Returns:
            String description of available tools
        """
        if not tools:
            return ""
        
        tool_descriptions = ["Available tools:"]
        
        for tool in tools:
            name = tool.get("name", "unknown")
            description = tool.get("description", "No description")
            parameters = tool.get("parameters", {})
            
            tool_desc = f"\n<{name}>\nDescription: {description}"
            
            if parameters and "properties" in parameters:
                tool_desc += "\nParameters:"
                for param_name, param_info in parameters["properties"].items():
                    param_type = param_info.get("type", "string")
                    param_desc = param_info.get("description", "")
                    required = param_name in parameters.get("required", [])
                    req_marker = " (required)" if required else " (optional)"
                    tool_desc += f"\n  - {param_name} ({param_type}){req_marker}: {param_desc}"
            
            tool_desc += f"\n</{name}>"
            tool_descriptions.append(tool_desc)
        
        tool_descriptions.append("\nTo use a tool, format your response with XML-like tags:")
        tool_descriptions.append("<%tool_name%>\n<%parameter_name%>value</%parameter_name%>\n</%tool_name%>")
        
        return "\n".join(tool_descriptions)
    
    def _extract_tool_calls(self, content: str) -> List[ToolCall]:
        """
        Extract tool calls from the response content using XML-like parsing.
        
        Args:
            content: Response content that may contain tool calls
            
        Returns:
            List of ToolCall objects
        """
        tool_calls = []
        
        # Pattern to match tool calls: <tool_name>..parameters..</tool_name>
        tool_pattern = r'<(\w+)>(.*?)</\1>'
        tool_matches = re.findall(tool_pattern, content, re.DOTALL)
        
        for tool_name, tool_content in tool_matches:
            # Skip if this looks like a parameter rather than a tool
            if not tool_content.strip():
                continue
            
            # Extract parameters from tool content
            param_pattern = r'<(\w+)>(.*?)</\1>'
            param_matches = re.findall(param_pattern, tool_content, re.DOTALL)
            
            if param_matches:  # This is likely a tool call
                parameters = {}
                for param_name, param_value in param_matches:
                    parameters[param_name] = param_value.strip()
                
                tool_calls.append(ToolCall(
                    tool_name=tool_name,
                    parameters=parameters
                ))
        
        return tool_calls
    
    def validate_config(self) -> bool:
        """
        Validate Gemini-specific configuration.
        
        Returns:
            bool: True if configuration is valid
        """
        super().validate_config()
        
        # Validate model name
        if not self.model.startswith(("gemini-", "models/gemini-")):
            raise ValueError(f"Invalid Gemini model name: {self.model}")
        
        return True