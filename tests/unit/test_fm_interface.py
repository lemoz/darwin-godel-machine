"""
Unit tests for FM interface components.
"""

import unittest
import asyncio
from pathlib import Path
import tempfile
import json
from unittest.mock import patch, AsyncMock, MagicMock
import os

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.fm_interface.api_handler import (
    ApiHandler, Message, MessageRole, CompletionRequest,
    CompletionResponse, ToolCall
)
from agent.fm_interface.providers.anthropic import AnthropicHandler
from agent.fm_interface.providers.gemini import GeminiHandler
from agent.fm_interface.message_formatter import MessageFormatter


class TestApiHandler(unittest.TestCase):
    """Test FM interface functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.config = {
            "provider": "anthropic",
            "model": "claude-3-sonnet-20240229",
            "max_retries": 3,
            "timeout": 30,
            "temperature": 0.7
        }
    
    # Note: ApiHandler is abstract and can't be instantiated directly
    # These tests would need a concrete implementation or mock
    
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test_key"})
    def test_anthropic_handler_initialization(self):
        """Test Anthropic handler initialization."""
        handler = AnthropicHandler(self.config)
        self.assertEqual(handler.model, "claude-3-sonnet-20240229")
        self.assertEqual(handler.temperature, 0.7)
        
    @patch.dict(os.environ, {"GOOGLE_API_KEY": "test_key"})
    def test_gemini_handler_initialization(self):
        """Test Gemini handler initialization."""
        config = self.config.copy()
        config["provider"] = "gemini"
        config["model"] = "gemini-pro"
        config["api_key"] = "test_key"  # Add api_key to config
        handler = GeminiHandler(config)
        self.assertEqual(handler.model, "gemini-pro")
        self.assertEqual(handler.temperature, 0.7)
    
    def test_api_handler_abstract_methods(self):
        """Test that ApiHandler is abstract."""
        with self.assertRaises(TypeError):
            ApiHandler(self.config)
    
    @patch('agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion')
    async def test_anthropic_completion_success(self, mock_completion):
        """Test successful completion with Anthropic handler."""
        from agent.fm_interface.api_handler import CompletionResponse, ToolCall
        
        mock_completion.return_value = CompletionResponse(
            content="Generated response",
            tool_calls=[],
            usage={"prompt_tokens": 10, "completion_tokens": 20}
        )
        
        handler = AnthropicHandler(self.config)
        messages = [Message(MessageRole.USER, "Test prompt")]
        request = CompletionRequest(messages=messages)
        
        response = await handler.get_completion(request)
        
        self.assertEqual(response.content, "Generated response")
        mock_completion.assert_called_once()
    
    
    
    
    def test_message_formatter(self):
        """Test message formatter functionality."""
        formatter = MessageFormatter()
        
        # Test system message formatting
        system_msg = formatter.format_system_message(
            base_instructions="You are a helpful AI assistant.",
            available_tools=[{"name": "test_tool", "description": "A test tool"}]
        )
        self.assertIsInstance(system_msg, Message)
        self.assertEqual(system_msg.role, MessageRole.SYSTEM)
        self.assertIn("You are a helpful AI assistant.", system_msg.content)
        self.assertIn("Available Tools", system_msg.content)
    
    def test_task_message_formatting(self):
        """Test task message formatting."""
        formatter = MessageFormatter()
        
        # Test task message
        task_msg = formatter.format_task_message(
            task_description="Write a function that adds two numbers",
            constraints=["Must handle edge cases", "Include type hints"]
        )
        self.assertIsInstance(task_msg, Message)
        self.assertEqual(task_msg.role, MessageRole.USER)
        self.assertIn("Write a function", task_msg.content)
        self.assertIn("Must handle edge cases", task_msg.content)
        
    def test_conversation_history(self):
        """Test conversation history creation."""
        formatter = MessageFormatter()
        
        messages = [
            Message(role=MessageRole.SYSTEM, content="System message"),
            Message(role=MessageRole.USER, content="User message"),
            Message(role=MessageRole.ASSISTANT, content="Assistant response")
        ]
        
        # Test without token limit
        history = formatter.create_conversation_history(messages)
        self.assertEqual(len(history), 3)
        
        # Test with token limit (very small to force truncation)
        history = formatter.create_conversation_history(messages, max_tokens=10)
        self.assertLessEqual(len(history), 3)
    
    
    
    
    
    def test_config_validation(self):
        """Test configuration validation."""
        # Test with concrete handler - missing API key
        handler = AnthropicHandler({"model": "claude-3"})
        with self.assertRaises(ValueError):
            handler.validate_config()
    


class TestProviderSpecific(unittest.TestCase):
    """Test provider-specific functionality."""
    
    @patch('anthropic.Anthropic')
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test_key"})
    async def test_anthropic_generate(self, mock_client):
        """Test Anthropic provider generation."""
        # Mock response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Generated text")]
        mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
        
        provider = AnthropicHandler(self.config)
        messages = [Message(MessageRole.USER, "Test")]
        request = CompletionRequest(messages=messages)
        
        response = await provider.get_completion(request)
        
        self.assertEqual(response.content, "Generated text")
    
    @patch('google.generativeai.GenerativeModel')
    @patch.dict(os.environ, {"GOOGLE_API_KEY": "test_key"})
    async def test_gemini_generate(self, mock_model):
        """Test Gemini provider generation."""
        # Mock response
        mock_response = MagicMock()
        mock_response.text = "Generated text"
        mock_model.return_value.generate_content = AsyncMock(return_value=mock_response)
        
        config = {"provider": "gemini", "model": "gemini-pro", "api_key": "test_key"}
        provider = GeminiHandler(config)
        messages = [Message(MessageRole.USER, "Test")]
        request = CompletionRequest(messages=messages)
        
        response = await provider.get_completion(request)
        
        self.assertEqual(response.content, "Generated text")
    


if __name__ == "__main__":
    # Run async tests
    unittest.main()