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
import time

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
                
                # Find Agent class. Prefer an exact 'Agent' match, then names
                # ending in 'Agent' (e.g. ImprovedAgent), so helper classes
                # like AgentConfig are never mistaken for the agent itself.
                agent_classes = [cls for cls in classes if 'Agent' in cls.name]
                agent_classes.sort(
                    key=lambda c: (c.name != 'Agent', not c.name.endswith('Agent'))
                )
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

        Loads and inspects the agent file that was *actually passed* (not the
        live source tree) using ``importlib.util.spec_from_file_location`` with
        a unique module name per load so repeated calls don't collide.

        Checks:
        - File exists
        - Parses as valid Python (AST)
        - Defines a class named ``Agent`` (or containing "Agent")
        - That class has ``solve_task`` and ``__init__`` methods

        Args:
            agent_path: Path string passed to ``validate_agent``
            results: Results dictionary to update (mutated in place)

        Returns:
            bool: True if implementation is valid, False otherwise
        """
        main_file = results['agent_info'].get('main_file')
        agent_class_name = results['agent_info'].get('agent_class')

        if not main_file:
            results['errors'].append("No main agent file resolved; cannot validate implementation")
            return False
        if not agent_class_name:
            results['errors'].append("No class with 'Agent' in name found in file")
            return False

        file_path = Path(main_file)

        # --- Gate 1: file exists ---
        if not file_path.exists():
            results['errors'].append(f"Agent file does not exist: {main_file}")
            return False

        # --- Gate 2: parses as valid Python ---
        try:
            source = file_path.read_text(encoding='utf-8')
            tree = ast.parse(source)
        except SyntaxError as e:
            results['errors'].append(f"Agent file has syntax errors: {e}")
            return False
        except Exception as e:
            results['errors'].append(f"Failed to read agent file: {e}")
            return False

        # --- Gate 3: defines an Agent class with required methods (via AST) ---
        agent_classes = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and 'Agent' in node.name
        ]
        if not agent_classes:
            results['errors'].append("No class with 'Agent' in name found in file")
            return False

        # Same preference order as _validate_syntax: exact 'Agent', then
        # *Agent suffix, so AgentConfig-style helpers are never selected.
        agent_classes.sort(
            key=lambda c: (c.name != 'Agent', not c.name.endswith('Agent'))
        )
        target_class = agent_classes[0]
        defined_methods = {
            node.name
            for node in ast.walk(target_class)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        missing = []
        for method_name in self.required_methods:
            if method_name in defined_methods:
                results['checks_passed'].append(f"Has method: {method_name}")
            else:
                missing.append(method_name)
                results['errors'].append(f"Missing required method: {method_name}")

        if missing:
            return False

        # --- Gate 4: try to load the actual file via importlib ---
        # Use a unique module name to avoid collisions with cached modules.
        unique_name = f"_dgm_agent_validate_{id(file_path)}_{int(time.time() * 1e6)}"
        try:
            # Prefer agent_loader.load_from_path if the parallel fixer has
            # added it; fall back to importlib directly.
            agent_class = None
            if hasattr(self.agent_loader, 'load_from_path'):
                try:
                    agent_class = self.agent_loader.load_from_path(file_path)
                except Exception:
                    agent_class = None  # fall through to importlib

            if agent_class is None:
                spec = importlib.util.spec_from_file_location(unique_name, file_path)
                if spec is None or spec.loader is None:
                    results['warnings'].append(
                        "Cannot create module spec — skipping runtime load check"
                    )
                    results['checks_passed'].append("Agent class can be referenced (AST only)")
                    return True

                module = importlib.util.module_from_spec(spec)
                sys.modules[unique_name] = module
                try:
                    spec.loader.exec_module(module)  # type: ignore[union-attr]
                finally:
                    # Clean up so we don't pollute sys.modules indefinitely.
                    sys.modules.pop(unique_name, None)

                agent_class = getattr(module, agent_class_name, None)
                if agent_class is None:
                    # Try any class with 'Agent' in the name.
                    for attr_name in dir(module):
                        if 'Agent' in attr_name:
                            agent_class = getattr(module, attr_name)
                            break

            if agent_class is None:
                results['errors'].append(
                    f"Class '{agent_class_name}' not found after loading {main_file}"
                )
                return False

            # Verify methods are present at the class level.
            for method_name in self.required_methods:
                if not hasattr(agent_class, method_name):
                    results['errors'].append(
                        f"Loaded class missing required method: {method_name}"
                    )
                    return False

            # Check solve_task signature.
            if hasattr(agent_class, 'solve_task'):
                sig = inspect.signature(agent_class.solve_task)
                params = list(sig.parameters.keys())
                if 'task' not in params:
                    results['warnings'].append(
                        "solve_task should have 'task' parameter"
                    )

            results['checks_passed'].append("Agent class loaded and verified successfully")
            return True

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