"""
Test to verify API keys belong to the user by making a unique request.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.config_loader import config_loader
from agent.fm_interface.providers.gemini import GeminiHandler
from agent.fm_interface.providers.anthropic import AnthropicHandler
from agent.fm_interface.api_handler import (
    CompletionRequest, Message, MessageRole
)


async def test_unique_request():
    """Make a unique request to verify API ownership."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    unique_phrase = f"DGM_TEST_{timestamp}_CDOSSMAN"
    
    print(f"\nMaking unique API request with phrase: {unique_phrase}")
    print("Check your API console for this exact phrase in the logs!\n")
    
    # Test Gemini
    try:
        config = config_loader.get_fm_config("gemini")
        handler = GeminiHandler(config)
        
        request = CompletionRequest(
            messages=[
                Message(
                    role=MessageRole.USER,
                    content=f"Please repeat exactly: {unique_phrase}"
                )
            ],
            max_tokens=100,
            temperature=0
        )
        
        print("Testing Gemini...")
        response = await handler.get_completion(request)
        print(f"✓ Gemini response: {response.content.strip()}")
        print(f"  Tokens used: {response.usage.get('total_tokens', 'N/A') if response.usage else 'N/A'}")
        
    except Exception as e:
        print(f"✗ Gemini error: {e}")
    
    print()
    
    # Test Anthropic
    try:
        config = config_loader.get_fm_config("anthropic")
        handler = AnthropicHandler(config)
        
        request = CompletionRequest(
            messages=[
                Message(
                    role=MessageRole.USER,
                    content=f"Please repeat exactly: {unique_phrase}"
                )
            ],
            max_tokens=100,
            temperature=0
        )
        
        print("Testing Anthropic...")
        response = await handler.get_completion(request)
        print(f"✓ Anthropic response: {response.content.strip()}")
        print(f"  Tokens used: {response.usage.get('total_tokens', 'N/A') if response.usage else 'N/A'}")
        
    except Exception as e:
        print(f"✗ Anthropic error: {e}")
    
    print(f"\n🔍 NOW CHECK YOUR API CONSOLES:")
    print(f"   - Google AI Studio: https://aistudio.google.com/")
    print(f"   - Anthropic Console: https://console.anthropic.com/")
    print(f"   Look for requests containing: {unique_phrase}")
    print(f"   This will confirm these are YOUR API keys being used.")


if __name__ == "__main__":
    asyncio.run(test_unique_request())