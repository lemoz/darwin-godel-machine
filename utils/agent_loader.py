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
            
    def load_from_path(self, agent_file: Path) -> Type[Any]:
        """
        Load an Agent class from an arbitrary agent.py file path.

        Agents are packages (agent.py with relative imports into sibling
        subpackages like fm_interface/ and tools/), so the file is loaded as
        a submodule of a synthetic package whose __path__ is the file's
        directory. Relative imports then resolve against that copy of the
        package — the repo agent, archive copies, and workspace copies all
        load the same way without sys.path tricks. Self-contained
        single-file agents load identically (they just never trigger a
        relative import). The synthetic package name is derived from the
        absolute path, so different agent copies never collide in
        sys.modules.

        Args:
            agent_file: Path to an agent.py file.

        Returns:
            The Agent class from the loaded module.

        Raises:
            ImportError: If the module cannot be loaded.
            AttributeError: If no Agent class is found in the module.
        """
        import hashlib
        import types

        agent_file = Path(agent_file).resolve()
        agent_dir = agent_file.parent
        try:
            digest = hashlib.md5(str(agent_file).encode()).hexdigest()[:12]
            pkg_name = f"dgm_agent_pkg_{digest}"

            # Synthetic parent package anchoring relative imports to this
            # agent copy's own directory.
            if pkg_name not in sys.modules:
                pkg = types.ModuleType(pkg_name)
                pkg.__path__ = [str(agent_dir)]
                pkg.__package__ = pkg_name
                sys.modules[pkg_name] = pkg

            mod_name = f"{pkg_name}.{agent_file.stem}"
            spec = importlib.util.spec_from_file_location(mod_name, agent_file)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot create module spec for {agent_file}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)

            agent_class = self._find_agent_class(module, mod_name)
            if agent_class is None:
                raise AttributeError(f"No Agent class found in {agent_file}")
            self.logger.info(f"Successfully loaded agent from {agent_file}")
            return agent_class
        except Exception as e:
            self.logger.error(f"Failed to load agent from {agent_file}: {e}")
            raise

    @staticmethod
    def _find_agent_class(module: Any, mod_name: str) -> Optional[Type[Any]]:
        """
        Pick the agent class from a loaded module.

        Prefers a class named exactly 'Agent', then classes defined in this
        module whose names end with 'Agent' (a self-modified agent may have
        renamed itself, e.g. ImprovedAgent). Helper classes like AgentConfig
        are never selected.
        """
        candidate = getattr(module, 'Agent', None)
        if isinstance(candidate, type):
            return candidate
        local_classes = [
            obj for name, obj in vars(module).items()
            if isinstance(obj, type) and getattr(obj, '__module__', None) == mod_name
        ]
        for cls in local_classes:
            if cls.__name__.endswith('Agent'):
                return cls
        for cls in local_classes:
            if 'Agent' in cls.__name__ and not cls.__name__.endswith('Config'):
                return cls
        return None

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