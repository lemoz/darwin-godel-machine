"""
Test script to verify Foundation Model API connections.

This script tests that API keys are properly configured and that we can 
successfully communicate with both Gemini and Anthropic APIs.
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
    CompletionRequest, Message, MessageRole, ApiError, AuthenticationError
)


async def test_provider(provider_name: str, handler_class):
    """Test a specific FM provider connection."""
    print(f"\n{'='*50}")
    print(f"Testing {provider_name.upper()} Connection")
    print('='*50)
    
    try:
        # Load configuration
        config = config_loader.get_fm_config(provider_name)
        print(f"✓ Configuration loaded successfully")
        print(f"  Model: {config.get('model')}")
        print(f"  Max tokens: {config.get('max_tokens')}")
        print(f"  Temperature: {config.get('temperature')}")
        
        # Check API key
        api_key = config.get('api_key', '')
        if api_key.startswith('${') or api_key == 'your-' + provider_name + '-api-key-here':
            print(f"✗ API key not set - please set {provider_name.upper()}_API_KEY in .env file")
            return False
        else:
            print(f"✓ API key found (length: {len(api_key)})")
        
        # Initialize handler
        handler = handler_class(config)
        print(f"✓ Handler initialized successfully")
        
        # Create test request
        request = CompletionRequest(
            messages=[
                Message(
                    role=MessageRole.USER,
                    content="Please respond with exactly: 'Hello from " + provider_name.capitalize() + "!'"
                )
            ],
            max_tokens=50,
            temperature=0
        )
        
        print(f"⏳ Sending test request...")
        
        # Test completion
        response = await handler.get_completion(request)
        
        print(f"✓ Response received successfully!")
        print(f"  Content: {response.content.strip()}")
        print(f"  Model: {response.model}")
        if response.usage:
            print(f"  Tokens used: {response.usage.get('total_tokens', 'N/A')}")
        
        return True
        
    except AuthenticationError as e:
        print(f"✗ Authentication failed: {e}")
        print(f"  Please check your API key in the .env file")
        return False
    except ApiError as e:
        print(f"✗ API error: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {type(e).__name__}: {e}")
        return False


async def main():
    """Run connection tests for all configured providers."""
    print("Darwin Gödel Machine - FM Provider Connection Test")
    print("="*50)
    
    # Check if .env file exists
    env_path = Path(".env")
    if not env_path.exists():
        print("⚠️  Warning: .env file not found!")
        print("   Creating .env from .env.example...")
        
        env_example = Path(".env.example")
        if env_example.exists():
            env_path.write_text(env_example.read_text())
            print("   ✓ Created .env file - please add your API keys")
        else:
            print("   ✗ .env.example not found - cannot create .env")
    
    # Test providers
    providers = [
        ("gemini", GeminiHandler),
        ("anthropic", AnthropicHandler)
    ]
    
    results = {}
    for provider_name, handler_class in providers:
        success = await test_provider(provider_name, handler_class)
        results[provider_name] = success
    
    # Summary
    print(f"\n{'='*50}")
    print("SUMMARY")
    print('='*50)
    
    all_success = True
    for provider, success in results.items():
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{provider.capitalize():10} {status}")
        if not success:
            all_success = False
    
    if all_success:
        print("\n✓ All providers are properly configured!")
        print("  You can now proceed with Phase 4.2 - Benchmark Dataset Integration")
    else:
        print("\n⚠️  Some providers failed - please check your API keys in .env")
        print("  You can still proceed with working providers")
    
    # Check primary provider
    print(f"\nPrimary provider: {config_loader.get_primary_provider()}")
    if results.get(config_loader.get_primary_provider(), False):
        print("✓ Primary provider is working correctly")
    else:
        print("✗ Primary provider is not working - please fix before proceeding")


if __name__ == "__main__":
    asyncio.run(main())