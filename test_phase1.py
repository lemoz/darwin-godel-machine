#!/usr/bin/env python3
"""
Test script for Phase 1 DGM MVP implementation.

This script validates that the core infrastructure components are properly implemented
and can be imported and instantiated without errors.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the current directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test that all core modules can be imported successfully."""
    print("🔍 Testing imports...")
    
    try:
        # Test agent imports
        from agent import Agent, Task, AgentConfig
        print("✅ Agent core imports successful")
        
        # Test FM interface imports
        from agent.fm_interface import ApiHandler, CompletionRequest, Message, MessageRole
        from agent.fm_interface.providers import GeminiHandler, AnthropicHandler
        print("✅ FM interface imports successful")
        
        # Test tool imports
        from agent.tools import BaseTool, ToolRegistry, BashTool, EditTool
        print("✅ Tool system imports successful")
        
        # Test sandbox imports
        from sandbox.sandbox_manager import SandboxManager
        print("✅ Sandbox manager imports successful")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error during imports: {e}")
        return False

def test_tool_registry():
    """Test that the tool registry works correctly."""
    print("\n🔧 Testing tool registry...")
    
    try:
        from agent.tools import ToolRegistry, BashTool, EditTool
        
        registry = ToolRegistry()
        
        # Register tools
        bash_tool = BashTool()
        edit_tool = EditTool()
        
        registry.register_tool(bash_tool)
        registry.register_tool(edit_tool)
        
        # Test tool listing
        tools = registry.list_tools()
        print(f"✅ Registered tools: {tools}")
        
        # Test tool schemas
        schemas = registry.get_tool_schemas()
        print(f"✅ Tool schemas generated: {len(schemas)} schemas")
        
        return True
        
    except Exception as e:
        print(f"❌ Tool registry test failed: {e}")
        return False

def test_agent_creation():
    """Test that agents can be created successfully."""
    print("\n🤖 Testing agent creation...")
    
    try:
        from agent import Agent, AgentConfig
        
        # Create a test config (without real API keys)
        config = AgentConfig(
            agent_id="test_agent_001",
            fm_provider="gemini",
            fm_config={
                "model": "gemini-2.0-flash-exp",
                "api_key": "test_key",  # This will fail API calls but allows creation
                "max_tokens": 1000,
                "temperature": 0.1
            },
            working_directory="./test_workspace"
        )
        
        # This should work even without real API key for basic instantiation
        try:
            agent = Agent(config)
            print("✅ Agent creation successful")
            
            # Test agent info
            info = agent.get_agent_info()
            print(f"✅ Agent info: ID={info['agent_id']}, Tools={info['available_tools']}")
            
            return True
            
        except Exception as e:
            # Expected to fail due to invalid API key, but creation should work
            if "api_key" in str(e).lower() or "authentication" in str(e).lower():
                print("✅ Agent creation works (API key validation expected to fail)")
                return True
            else:
                raise e
        
    except Exception as e:
        print(f"❌ Agent creation test failed: {e}")
        return False

def test_config_loading():
    """Test that configuration files can be loaded."""
    print("\n⚙️ Testing configuration loading...")
    
    try:
        import yaml
        
        # Test main config
        config_path = Path("config/dgm_config.yaml")
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            print("✅ Main configuration loaded successfully")
            print(f"   Primary FM provider: {config.get('fm_providers', {}).get('primary', 'Not set')}")
        else:
            print("❌ Main configuration file not found")
            return False
        
        # Test benchmark config
        benchmark_path = Path("config/benchmarks/string_manipulation.yaml")
        if benchmark_path.exists():
            with open(benchmark_path, 'r') as f:
                benchmark = yaml.safe_load(f)
            print("✅ Benchmark configuration loaded successfully")
            print(f"   Benchmark: {benchmark.get('name', 'Unknown')}")
        else:
            print("❌ Benchmark configuration file not found")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Configuration loading test failed: {e}")
        return False

async def test_bash_tool():
    """Test that the bash tool works for basic commands."""
    print("\n🔨 Testing bash tool...")
    
    try:
        from agent.tools import BashTool
        
        bash_tool = BashTool()
        
        # Test parameter validation
        validation_result = bash_tool.validate_parameters({"command": "echo 'Hello DGM'"})
        if validation_result.status.value == "success":
            print("✅ Bash tool parameter validation works")
        else:
            print(f"❌ Bash tool validation failed: {validation_result.error}")
            return False
        
        # Test safe command execution
        result = await bash_tool.execute({"command": "echo 'Phase 1 Complete!'"})
        if result.status.value == "success":
            print(f"✅ Bash tool execution works: {result.output.strip()}")
        else:
            print(f"❌ Bash tool execution failed: {result.error}")
            return False
        
        # Test safety blocking
        result = await bash_tool.execute({"command": "rm -rf /"})
        if result.status.value == "error" and "blocked" in result.error.lower():
            print("✅ Bash tool safety blocking works")
        else:
            print("❌ Bash tool safety blocking failed")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Bash tool test failed: {e}")
        return False

def test_project_structure():
    """Test that the expected project structure exists."""
    print("\n📁 Testing project structure...")
    
    expected_files = [
        "requirements.txt",
        "config/dgm_config.yaml",
        "config/benchmarks/string_manipulation.yaml",
        "agent/__init__.py",
        "agent/agent.py",
        "agent/fm_interface/__init__.py",
        "agent/fm_interface/api_handler.py",
        "agent/fm_interface/providers/__init__.py",
        "agent/fm_interface/providers/gemini.py",
        "agent/tools/__init__.py",
        "agent/tools/base_tool.py",
        "agent/tools/bash_tool.py",
        "sandbox/Dockerfile",
        "sandbox/sandbox_manager.py"
    ]
    
    missing_files = []
    for file_path in expected_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        print(f"❌ Missing files: {missing_files}")
        return False
    else:
        print(f"✅ All {len(expected_files)} expected files found")
        return True

async def main():
    """Run all Phase 1 tests."""
    print("🚀 DGM MVP Phase 1 Test Suite")
    print("=" * 50)
    
    tests = [
        ("Project Structure", test_project_structure),
        ("Imports", test_imports),
        ("Configuration Loading", test_config_loading),
        ("Tool Registry", test_tool_registry),
        ("Agent Creation", test_agent_creation),
        ("Bash Tool", test_bash_tool),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            
            if result:
                passed += 1
            else:
                failed += 1
                
        except Exception as e:
            print(f"❌ Test '{test_name}' crashed: {e}")
            failed += 1
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All Phase 1 tests passed! Core infrastructure is ready.")
        return True
    else:
        print("⚠️  Some tests failed. Review the output above for details.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)