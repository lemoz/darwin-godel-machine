"""
Test FM providers with a custom user query to verify real model responses.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.config_loader import config_loader
from agent.fm_interface.providers.gemini import GeminiHandler
from agent.fm_interface.providers.anthropic import AnthropicHandler
from agent.fm_interface.api_handler import (
    CompletionRequest, Message, MessageRole
)


async def test_custom_query(query: str):
    """Test both providers with a custom query."""
    print(f"\nTesting with your query: '{query}'\n")
    print("="*60)
    
    # Test Gemini
    print("\n🔷 GEMINI RESPONSE:")
    print("-"*40)
    try:
        config = config_loader.get_fm_config("gemini")
        handler = GeminiHandler(config)
        
        request = CompletionRequest(
            messages=[
                Message(
                    role=MessageRole.USER,
                    content=query
                )
            ],
            max_tokens=200,
            temperature=0.7
        )
        
        response = await handler.get_completion(request)
        print(response.content.strip())
        print(f"\n[Tokens used: {response.usage.get('total_tokens', 'N/A') if response.usage else 'N/A'}]")
        
    except Exception as e:
        print(f"Error: {e}")
    
    print("\n" + "="*60)
    
    # Test Anthropic
    print("\n🔶 ANTHROPIC (CLAUDE) RESPONSE:")
    print("-"*40)
    try:
        config = config_loader.get_fm_config("anthropic")
        handler = AnthropicHandler(config)
        
        request = CompletionRequest(
            messages=[
                Message(
                    role=MessageRole.USER,
                    content=query
                )
            ],
            max_tokens=200,
            temperature=0.7
        )
        
        response = await handler.get_completion(request)
        print(response.content.strip())
        print(f"\n[Tokens used: {response.usage.get('total_tokens', 'N/A') if response.usage else 'N/A'}]")
        
    except Exception as e:
        print(f"Error: {e}")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    # Get query from command line or use default
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = input("Enter your test query: ")
    
    asyncio.run(test_custom_query(query))