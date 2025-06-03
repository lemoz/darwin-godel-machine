"""
Agent Validator for DGM.

Validates that agents are compilable and retain their code-editing capabilities.
"""

import ast
import asyncio
import tempfile
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging

from agent import Agent, Task, AgentConfig

logger = logging.getLogger(__name__)


class AgentValidator:
    """Validates agent correctness and capabilities."""
    
    def __init__(self):
        """Initialize the agent validator."""
        self.validation_checks = [
            self._check_syntax,
            self._check_imports,
            self._check_required_methods,
            self._check_tool_integration,
            self._check_fm_interface
        ]
    
    async def validate_agent(
        self,
        agent_path: str,
        run_functional_tests: bool = True
    ) -> Dict[str, Any]:
        """
        Validate an agent's code and capabilities.
        
        Args:
            agent_path: Path to the agent's source code
            run_functional_tests: Whether to run functional tests
            
        Returns:
            Validation results
        """
        results = {
            'is_valid': True,
            'syntax_valid': False,
            'imports_valid': False,
            'methods_valid': False,
            'tools_valid': False,
            'fm_valid': False,
            'can_edit_code': False,
            'errors': []
        }
        
        # Run static checks
        for check in self.validation_checks:
            check_name = check.__name__.replace('_check_', '')
            try:
                check_result = await check(agent_path)
                results[f'{check_name}_valid'] = check_result['valid']
                if not check_result['valid']:
                    results['is_valid'] = False
                    results['errors'].extend(check_result.get('errors', []))
            except Exception as e:
                results[f'{check_name}_valid'] = False
                results['is_valid'] = False
                results['errors'].append(f"{check_name} check failed: {str(e)}")
        
        # Run functional tests if requested and static checks pass
        if run_functional_tests and results['is_valid']:
            functional_result = await self._check_functional_capabilities(agent_path)
            results['can_edit_code'] = functional_result['can_edit_code']
            if not functional_result['can_edit_code']:
                results['is_valid'] = False
                results['errors'].extend(functional_result.get('errors', []))
        
        return results
    
    async def _check_syntax(self, agent_path: str) -> Dict[str, Any]:
        """Check Python syntax validity."""
        errors = []
        
        try:
            # Check main agent.py file
            agent_file = Path(agent_path) / "agent" / "agent.py"
            if not agent_file.exists():
                return {
                    'valid': False,
                    'errors': ["agent/agent.py not found"]
                }
            
            with open(agent_file, 'r') as f:
                code = f.read()
            
            # Try to parse the code
            ast.parse(code)
            
            # Check all Python files in the agent directory
            for py_file in Path(agent_path).rglob("*.py"):
                try:
                    with open(py_file, 'r') as f:
                        ast.parse(f.read())
                except SyntaxError as e:
                    errors.append(f"Syntax error in {py_file}: {e}")
            
            return {
                'valid': len(errors) == 0,
                'errors': errors
            }
            
        except SyntaxError as e:
            return {
                'valid': False,
                'errors': [f"Syntax error in agent.py: {e}"]
            }
        except Exception as e:
            return {
                'valid': False,
                'errors': [f"Error checking syntax: {e}"]
            }
    
    async def _check_imports(self, agent_path: str) -> Dict[str, Any]:
        """Check that all imports can be resolved."""
        errors = []
        
        try:
            # Create a test script that imports the agent
            test_script = f"""
import sys
sys.path.insert(0, '{agent_path}')

try:
    from agent import Agent, Task, AgentConfig
    from agent.fm_interface import ApiHandler
    from agent.tools import BaseTool, BashTool
    print("All imports successful")
    exit(0)
except Exception as e:
    print(f"Import error: {{e}}")
    exit(1)
"""
            
            # Run the test script
            proc = await asyncio.create_subprocess_exec(
                'python', '-c', test_script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await proc.communicate()
            
            if proc.returncode != 0:
                error_msg = stdout.decode() + stderr.decode()
                errors.append(f"Import validation failed: {error_msg}")
            
            return {
                'valid': len(errors) == 0,
                'errors': errors
            }
            
        except Exception as e:
            return {
                'valid': False,
                'errors': [f"Error checking imports: {e}"]
            }
    
    async def _check_required_methods(self, agent_path: str) -> Dict[str, Any]:
        """Check that required methods are present."""
        errors = []
        
        try:
            agent_file = Path(agent_path) / "agent" / "agent.py"
            with open(agent_file, 'r') as f:
                code = f.read()
            
            tree = ast.parse(code)
            
            # Find Agent class
            agent_class = None
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == 'Agent':
                    agent_class = node
                    break
            
            if not agent_class:
                return {
                    'valid': False,
                    'errors': ["Agent class not found"]
                }
            
            # Check for required methods
            required_methods = ['__init__', 'solve_task', 'get_agent_info']
            found_methods = set()
            
            for node in agent_class.body:
                if isinstance(node, ast.FunctionDef):
                    found_methods.add(node.name)
            
            missing_methods = set(required_methods) - found_methods
            if missing_methods:
                errors.append(f"Missing required methods: {missing_methods}")
            
            return {
                'valid': len(errors) == 0,
                'errors': errors
            }
            
        except Exception as e:
            return {
                'valid': False,
                'errors': [f"Error checking methods: {e}"]
            }
    
    async def _check_tool_integration(self, agent_path: str) -> Dict[str, Any]:
        """Check that tools are properly integrated."""
        errors = []
        
        try:
            # Check for tool registry usage
            agent_file = Path(agent_path) / "agent" / "agent.py"
            with open(agent_file, 'r') as f:
                code = f.read()
            
            # Simple checks for tool integration
            if 'ToolRegistry' not in code:
                errors.append("ToolRegistry not found in agent code")
            
            if 'register_tool' not in code:
                errors.append("No tool registration found")
            
            # Check that BashTool is available
            if 'BashTool' not in code:
                errors.append("BashTool not found (required for code editing)")
            
            return {
                'valid': len(errors) == 0,
                'errors': errors
            }
            
        except Exception as e:
            return {
                'valid': False,
                'errors': [f"Error checking tools: {e}"]
            }
    
    async def _check_fm_interface(self, agent_path: str) -> Dict[str, Any]:
        """Check FM interface integration."""
        errors = []
        
        try:
            agent_file = Path(agent_path) / "agent" / "agent.py"
            with open(agent_file, 'r') as f:
                code = f.read()
            
            # Check for FM interface usage
            if 'api_handler' not in code.lower() and 'fm_handler' not in code.lower():
                errors.append("No FM interface handler found")
            
            if 'get_completion' not in code:
                errors.append("No FM completion calls found")
            
            return {
                'valid': len(errors) == 0,
                'errors': errors
            }
            
        except Exception as e:
            return {
                'valid': False,
                'errors': [f"Error checking FM interface: {e}"]
            }
    
    async def _check_functional_capabilities(
        self,
        agent_path: str
    ) -> Dict[str, Any]:
        """Check that the agent can perform basic code editing tasks."""
        errors = []
        can_edit_code = False
        
        try:
            # Create a simple code editing task
            test_task = Task(
                task_id="validation_test",
                description="Create a file called test.py with a function that returns 'Hello, World!'",
                metadata={'validation': True}
            )
            
            # Create a minimal agent config
            config = AgentConfig(
                agent_id="validation_agent",
                fm_provider="gemini",
                fm_config={
                    'model': 'gemini-2.0-flash-exp',
                    'api_key': os.getenv('GEMINI_API_KEY', 'test_key')
                },
                working_directory=tempfile.mkdtemp()
            )
            
            # Try to instantiate and run the agent
            # Note: This is a basic check - full functional testing
            # would require actual FM API access
            
            # For now, just check that the agent can be instantiated
            # without errors
            import sys
            sys.path.insert(0, agent_path)
            from agent import Agent
            
            agent = Agent(config)
            
            # Check that agent has editing capabilities
            agent_info = agent.get_agent_info()
            available_tools = agent_info.get('available_tools', [])
            
            if 'bash' in available_tools or 'edit' in available_tools:
                can_edit_code = True
            else:
                errors.append("Agent lacks code editing tools")
            
            return {
                'can_edit_code': can_edit_code,
                'errors': errors
            }
            
        except Exception as e:
            return {
                'can_edit_code': False,
                'errors': [f"Functional test failed: {e}"]
            }
    
    def validate_agent_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate agent configuration.
        
        Args:
            config: Agent configuration dictionary
            
        Returns:
            Validation results
        """
        errors = []
        
        # Check required fields
        required_fields = ['agent_id', 'fm_provider', 'fm_config']
        for field in required_fields:
            if field not in config:
                errors.append(f"Missing required field: {field}")
        
        # Check FM config
        if 'fm_config' in config:
            fm_config = config['fm_config']
            if 'model' not in fm_config:
                errors.append("FM config missing 'model' field")
            if 'api_key' not in fm_config:
                errors.append("FM config missing 'api_key' field")
        
        # Check FM provider
        if 'fm_provider' in config:
            valid_providers = ['gemini', 'anthropic', 'openai']
            if config['fm_provider'] not in valid_providers:
                errors.append(f"Invalid FM provider: {config['fm_provider']}")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }