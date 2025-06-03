"""
Abstract base class for Foundation Model API handlers.

This module defines the interface that all FM provider implementations must follow,
enabling the DGM system to work with different Foundation Models interchangeably.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass
from enum import Enum


class MessageRole(Enum):
    """Standard roles for messages in conversations."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """Standard internal message format used across all providers."""
    role: MessageRole
    content: str
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ToolCall:
    """Represents a tool call request from the FM."""
    tool_name: str
    parameters: Dict[str, Any]
    call_id: Optional[str] = None


@dataclass
class ToolResult:
    """Represents the result of a tool execution."""
    call_id: Optional[str]
    result: str
    success: bool = True
    error: Optional[str] = None


@dataclass
class CompletionResponse:
    """Standard response format from FM providers."""
    content: str
    tool_calls: List[ToolCall]
    usage: Optional[Dict[str, int]] = None
    model: Optional[str] = None
    finish_reason: Optional[str] = None


@dataclass
class CompletionRequest:
    """Standard request format for FM providers."""
    messages: List[Message]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    tools: Optional[List[Dict[str, Any]]] = None
    system_prompt: Optional[str] = None


class ApiHandler(ABC):
    """
    Abstract base class for Foundation Model API handlers.
    
    All FM provider implementations must inherit from this class and implement
    the required methods. This ensures a consistent interface across different
    providers while allowing provider-specific optimizations.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the API handler with provider-specific configuration.
        
        Args:
            config: Dictionary containing provider configuration including
                   API keys, model names, timeouts, etc.
        """
        self.config = config
        self.model = config.get("model")
        self.api_key = config.get("api_key")
        self.timeout = config.get("timeout", 60)
        self.max_tokens = config.get("max_tokens", 8192)
        self.temperature = config.get("temperature", 0.1)
    
    @abstractmethod
    async def get_completion(self, request: CompletionRequest) -> CompletionResponse:
        """
        Get a completion from the Foundation Model.
        
        Args:
            request: Standardized completion request
            
        Returns:
            CompletionResponse: Standardized response containing the completion
            
        Raises:
            ApiError: When the API call fails
            ValidationError: When the request is invalid
        """
        pass
    
    @abstractmethod
    def format_messages(self, messages: List[Message]) -> Any:
        """
        Convert internal message format to provider-specific format.
        
        Args:
            messages: List of messages in standard internal format
            
        Returns:
            Provider-specific message format
        """
        pass
    
    @abstractmethod
    def parse_response(self, response: Any) -> CompletionResponse:
        """
        Parse provider-specific response into standard format.
        
        Args:
            response: Raw response from the provider's API
            
        Returns:
            CompletionResponse: Standardized response format
        """
        pass
    
    @abstractmethod
    def format_tools(self, tools: List[Dict[str, Any]]) -> Any:
        """
        Convert standard tool definitions to provider-specific format.
        
        Args:
            tools: List of tool definitions in standard format
            
        Returns:
            Provider-specific tool format
        """
        pass
    
    def validate_config(self) -> bool:
        """
        Validate that the handler is properly configured.
        
        Returns:
            bool: True if configuration is valid
            
        Raises:
            ValueError: If required configuration is missing
        """
        if not self.api_key:
            raise ValueError("API key is required")
        if not self.model:
            raise ValueError("Model name is required")
        return True
    
    def get_provider_name(self) -> str:
        """
        Get the name of this provider.
        
        Returns:
            str: Provider name (e.g., "gemini", "anthropic", "openai")
        """
        return self.__class__.__name__.lower().replace("handler", "")


class ApiError(Exception):
    """Raised when an API call fails."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, 
                 provider: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.provider = provider


class ValidationError(Exception):
    """Raised when request validation fails."""
    pass


class RateLimitError(ApiError):
    """Raised when rate limits are exceeded."""
    pass


class AuthenticationError(ApiError):
    """Raised when authentication fails."""
    pass