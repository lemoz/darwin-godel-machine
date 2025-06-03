"""Configuration loader with environment variable support."""

import os
import yaml
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

class ConfigLoader:
    """Loads configuration from YAML files with environment variable substitution."""
    
    def __init__(self, config_path: str = "config/dgm_config.yaml"):
        """Initialize the config loader.
        
        Args:
            config_path: Path to the configuration file
        """
        self.config_path = Path(config_path)
        
        # Load .env file if it exists
        env_path = Path(".env")
        if env_path.exists():
            load_dotenv(env_path)
        else:
            # Try .env.example as fallback (for testing)
            env_example_path = Path(".env.example")
            if env_example_path.exists():
                load_dotenv(env_example_path)
    
    def load(self) -> Dict[str, Any]:
        """Load configuration with environment variable substitution.
        
        Returns:
            Dictionary containing the configuration
        """
        with open(self.config_path, 'r') as f:
            config_text = f.read()
        
        # Substitute environment variables
        config_text = self._substitute_env_vars(config_text)
        
        # Parse YAML
        config = yaml.safe_load(config_text)
        
        return config
    
    def _substitute_env_vars(self, text: str) -> str:
        """Substitute ${VAR_NAME} with environment variable values.
        
        Args:
            text: Configuration text with placeholders
            
        Returns:
            Text with substituted values
        """
        import re
        
        def replace_var(match):
            var_name = match.group(1)
            value = os.environ.get(var_name, f"${{{var_name}}}")
            return value
        
        # Replace ${VAR_NAME} patterns
        pattern = r'\$\{([^}]+)\}'
        return re.sub(pattern, replace_var, text)
    
    def get_fm_config(self, provider: str) -> Dict[str, Any]:
        """Get Foundation Model provider configuration.
        
        Args:
            provider: Provider name (e.g., 'gemini', 'anthropic')
            
        Returns:
            Provider configuration dictionary
        """
        config = self.load()
        fm_config = config.get('fm_providers', {}).get(provider, {})
        
        # Check if API key is properly set
        api_key = fm_config.get('api_key', '')
        if api_key.startswith('${') and api_key.endswith('}'):
            raise ValueError(f"API key for {provider} is not set. Please set {api_key[2:-1]} in your .env file")
        
        return fm_config
    
    def get_primary_provider(self) -> str:
        """Get the primary FM provider name.
        
        Returns:
            Primary provider name
        """
        config = self.load()
        return config.get('fm_providers', {}).get('primary', 'gemini')


# Global config loader instance
config_loader = ConfigLoader()