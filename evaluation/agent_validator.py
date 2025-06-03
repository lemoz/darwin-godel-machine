"""
Agent validator for verifying agent implementations.

This module provides functionality to validate that agents meet
the required interface and implementation standards.
"""

from typing import Dict, List, Any, Optional
from pathlib import Path
import ast
import inspect
import importlib.util
import sys

from utils.agent_loader import AgentLoader


class AgentValidator:
    """
    Validates agent implementations against DGM requirements.
    
    This class checks that agents implement required methods,
    follow the expected structure, and can be properly instantiated.
    """
    
    def __init__(self):
        """Initialize the agent validator."""
        self.required_methods = [
            'solve_task',
            '__init__'
        ]
        self.required_attributes = [
            'fm_interface',
            'tools'
        ]
        self.validation_results = []
        self.agent_loader = AgentLoader()
    
    async def validate_agent(self, agent_path: str) -> Dict[str, Any]:
        """
        Validate an agent implementation.
        
        Args:
            agent_path: Path to the agent module or directory
            
        Returns:
            Dict containing validation results
        """
        results = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'checks_passed': [],
            'agent_info': {}
        }
        
        try:
            # Check file structure
            structure_valid = self._validate_structure(agent_path, results)
            if not structure_valid:
                results['valid'] = False
                return results
            
            # Check syntax
            syntax_valid = self._validate_syntax(agent_path, results)
            if not syntax_valid:
                results['valid'] = False
                return results
            
            # Check implementation
            impl_valid = await self._validate_implementation(agent_path, results)
            if not impl_valid:
                results['valid'] = False
            
            # Check dependencies
            self._validate_dependencies(agent_path, results)
            
        except Exception as e:
            results['valid'] = False
            results['errors'].append(f"Validation failed: {str(e)}")
        
        return results
    
    def _validate_structure(self, agent_path: str, results: Dict[str, Any]) -> bool:
        """
        Validate agent file structure.
        
        Args:
            agent_path: Path to agent
            results: Results dictionary to update
            
        Returns:
            bool: True if structure is valid
        """
        path = Path(agent_path)
        
        if path.is_file():
            # Single file agent
            if path.suffix != '.py':
                results['errors'].append("Agent file must be a Python file (.py)")
                return False
            results['checks_passed'].append("Valid Python file")
            results['agent_info']['type'] = 'single_file'
            results['agent_info']['main_file'] = str(path)
        else:
            # Directory-based agent
            agent_dir = path / "agent"
            if not agent_dir.exists():
                results['errors'].append("Agent directory must contain 'agent' subdirectory")
                return False
            
            agent_file = agent_dir / "agent.py"
            if not agent_file.exists():
                results['errors'].append("Agent directory must contain agent/agent.py")
                return False
            
            results['checks_passed'].append("Valid directory structure")
            results['agent_info']['type'] = 'directory'
            results['agent_info']['main_file'] = str(agent_file)
        
        return True
    
    def _validate_syntax(self, agent_path: str, results: Dict[str, Any]) -> bool:
        """
        Validate Python syntax.
        
        Args:
            agent_path: Path to agent
            results: Results dictionary to update
            
        Returns:
            bool: True if syntax is valid
        """
        main_file = results['agent_info'].get('main_file')
        if not main_file:
            results['errors'].append("No main file found")
            return False
        
        try:
            with open(main_file, 'r') as f:
                content = f.read()
            
            # Parse AST
            tree = ast.parse(content)
            results['checks_passed'].append("Valid Python syntax")
            
            # Extract class information
            classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            if not classes:
                results['warnings'].append("No class definitions found")
            else:
                results['agent_info']['classes'] = [cls.name for cls in classes]
                
                # Find Agent class
                agent_classes = [cls for cls in classes if 'Agent' in cls.name]
                if agent_classes:
                    results['agent_info']['agent_class'] = agent_classes[0].name
                else:
                    results['warnings'].append("No class with 'Agent' in name found")
            
            return True
            
        except SyntaxError as e:
            results['errors'].append(f"Syntax error: {str(e)}")
            return False
        except Exception as e:
            results['errors'].append(f"Failed to parse file: {str(e)}")
            return False
    
    async def _validate_implementation(self, agent_path: str, results: Dict[str, Any]) -> bool:
        """
        Validate agent implementation details.
        
        Args:
            agent_path: Path to agent
            results: Results dictionary to update
            
        Returns:
            bool: True if implementation is valid
        """
        main_file = results['agent_info'].get('main_file')
        agent_class_name = results['agent_info'].get('agent_class')
        
        if not main_file or not agent_class_name:
            results['warnings'].append("Cannot validate implementation without agent class")
            return True  # Not a failure, just can't validate
        
        try:
            # Use AgentLoader to properly load the agent
            agent_path = Path(main_file)
            
            # Determine if this is from archive or source
            if 'archive' in str(agent_path):
                # Loading from archive
                agent_class = self.agent_loader.load_from_archive(agent_path)
            else:
                # Loading from source
                agent_class = self.agent_loader.load_from_source()
            
            if not agent_class:
                results['errors'].append(f"Failed to load agent class")
                return False
            
            # Check required methods
            for method_name in self.required_methods:
                if not hasattr(agent_class, method_name):
                    results['errors'].append(f"Missing required method: {method_name}")
                else:
                    results['checks_passed'].append(f"Has method: {method_name}")
            
            # Check method signatures
            if hasattr(agent_class, 'solve_task'):
                sig = inspect.signature(agent_class.solve_task)
                params = list(sig.parameters.keys())
                if 'task' not in params:
                    results['warnings'].append("solve_task should have 'task' parameter")
            
            # Try to instantiate (with mock dependencies)
            try:
                # This would need proper mocking in production
                results['checks_passed'].append("Agent class can be referenced")
            except Exception as e:
                results['warnings'].append(f"Cannot instantiate agent: {str(e)}")
            
            return len([e for e in results['errors'] if 'Missing required method' in e]) == 0
            
        except Exception as e:
            results['errors'].append(f"Implementation validation failed: {str(e)}")
            return False
    
    def _validate_dependencies(self, agent_path: str, results: Dict[str, Any]) -> None:
        """
        Check agent dependencies.
        
        Args:
            agent_path: Path to agent
            results: Results dictionary to update
        """
        main_file = results['agent_info'].get('main_file')
        if not main_file:
            return
        
        try:
            with open(main_file, 'r') as f:
                content = f.read()
            
            # Check for common imports
            expected_imports = [
                ('fm_interface', 'Foundation Model interface'),
                ('tools', 'Tool system'),
                ('asyncio', 'Async support')
            ]
            
            for module, description in expected_imports:
                if f"import {module}" in content or f"from {module}" in content:
                    results['checks_passed'].append(f"Uses {description}")
                else:
                    results['warnings'].append(f"Does not import {module} ({description})")
            
        except Exception as e:
            results['warnings'].append(f"Failed to check dependencies: {str(e)}")
    
    def get_validation_summary(self, results: Dict[str, Any]) -> str:
        """
        Generate a human-readable validation summary.
        
        Args:
            results: Validation results
            
        Returns:
            str: Summary text
        """
        lines = ["Agent Validation Summary", "=" * 50]
        
        if results['valid']:
            lines.append("✓ Agent is valid")
        else:
            lines.append("✗ Agent validation failed")
        
        if results['agent_info']:
            lines.append(f"\nAgent Type: {results['agent_info'].get('type', 'unknown')}")
            if 'agent_class' in results['agent_info']:
                lines.append(f"Agent Class: {results['agent_info']['agent_class']}")
        
        if results['checks_passed']:
            lines.append(f"\n✓ Passed {len(results['checks_passed'])} checks:")
            for check in results['checks_passed']:
                lines.append(f"  - {check}")
        
        if results['errors']:
            lines.append(f"\n✗ {len(results['errors'])} errors found:")
            for error in results['errors']:
                lines.append(f"  - {error}")
        
        if results['warnings']:
            lines.append(f"\n⚠ {len(results['warnings'])} warnings:")
            for warning in results['warnings']:
                lines.append(f"  - {warning}")
        
        return "\n".join(lines)