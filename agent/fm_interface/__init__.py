"""
Foundation Model interface package.

This package provides the abstraction layer for interacting with different
Foundation Model providers, including message formatting and response parsing.
"""

from .api_handler import (
    ApiHandler, CompletionRequest, CompletionResponse, Message, MessageRole,
    ToolCall, ToolResult, ApiError, ValidationError, RateLimitError, AuthenticationError
)
from .message_formatter import MessageFormatter, ConversationContext, MessageContext

__all__ = [
    "ApiHandler", "CompletionRequest", "CompletionResponse", "Message", "MessageRole",
    "ToolCall", "ToolResult", "ApiError", "ValidationError", "RateLimitError", 
    "AuthenticationError", "MessageFormatter", "ConversationContext", "MessageContext"
]