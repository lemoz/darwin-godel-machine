"""
AgentLoader: Handles loading agents with proper module resolution.
Abstracts away the complexity of Python path management and imports.
"""

import sys
import importlib.util
from pathlib import Path
from typing import Optional, Any, Type
import logging


class AgentLoader:
    """Manages agent loading with proper module resolution."""
    
    def __init__(self, project_root: Optional[Path] = None):
        """
        Initialize AgentLoader.
        
        Args:
            project_root: Root directory of the project. Defaults to current working directory.
        """
        self.project_root = project_root or Path.cwd()
        self.logger = logging.getLogger(__name__)
        
    def setup_environment(self, agent_dir: Path) -> None:
        """
        Set up Python environment for loading modular agents.
        
        Args:
            agent_dir: Directory containing the agent file
        """
        # Add project root to Python path
        if str(self.project_root) not in sys.path:
            sys.path.insert(0, str(self.project_root))
            self.logger.debug(f"Added project root to sys.path: {self.project_root}")
            
        # Add agent directory if it's from archive
        agent_parent = agent_dir.parent
        if "archive" in str(agent_parent) and str(agent_parent) not in sys.path:
            sys.path.insert(0, str(agent_parent))
            self.logger.debug(f"Added archive directory to sys.path: {agent_parent}")
            
    def load_from_archive(self, agent_path: Path) -> Type[Any]:
        """
        Load an agent from the archive with proper imports.
        
        Args:
            agent_path: Path to the agent.py file in the archive
            
        Returns:
            The Agent class from the loaded module
            
        Raises:
            ImportError: If the agent module cannot be loaded
            AttributeError: If the Agent class is not found in the module
        """
        self.setup_environment(agent_path.parent)
        
        try:
            # Create a unique module name to avoid conflicts
            module_name = f"archived_agent_{agent_path.parent.name}"
            
            # Load as module
            spec = importlib.util.spec_from_file_location(module_name, agent_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot create module spec for {agent_path}")
                
            module = importlib.util.module_from_spec(spec)
            
            # Add to sys.modules to allow relative imports
            sys.modules[module_name] = module
            
            # Execute the module
            spec.loader.exec_module(module)
            
            # Get the Agent class
            if not hasattr(module, 'Agent'):
                raise AttributeError(f"No Agent class found in {agent_path}")
                
            self.logger.info(f"Successfully loaded agent from {agent_path}")
            return module.Agent
            
        except Exception as e:
            self.logger.error(f"Failed to load agent from {agent_path}: {e}")
            raise
            
    def load_from_source(self) -> Type[Any]:
        """
        Load the main agent from source directory.
        
        Returns:
            The Agent class from the main agent module
            
        Raises:
            ImportError: If the agent module cannot be imported
        """
        try:
            # Ensure project root is in path
            self.setup_environment(self.project_root / "agent")
            
            # Import the agent
            from agent.agent import Agent
            
            self.logger.info("Successfully loaded agent from source")
            return Agent
            
        except Exception as e:
            self.logger.error(f"Failed to load agent from source: {e}")
            raise
            
    def cleanup_paths(self) -> None:
        """Clean up any paths added to sys.path during loading."""
        # Remove any archive paths we added
        paths_to_remove = [p for p in sys.path if "archive" in p and p != str(self.project_root)]
        for path in paths_to_remove:
            if path in sys.path:
                sys.path.remove(path)
                self.logger.debug(f"Removed from sys.path: {path}")