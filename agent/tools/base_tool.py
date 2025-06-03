"""
Base tool interface for the DGM agent system.

This module defines the abstract base class that all tools must implement,
providing a consistent interface for tool execution and parameter validation.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import json


class ToolExecutionStatus(Enum):
    """Status of tool execution."""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    INVALID_PARAMS = "invalid_params"


@dataclass
class ToolResult:
    """Result of tool execution."""
    status: ToolExecutionStatus
    output: str
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    execution_time: Optional[float] = None


@dataclass
class ToolParameter:
    """Definition of a tool parameter."""
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    enum_values: Optional[List[Any]] = None


class BaseTool(ABC):
    """
    Abstract base class for all DGM agent tools.
    
    All tools must inherit from this class and implement the required methods.
    This ensures a consistent interface for tool discovery, validation, and execution.
    """
    
    def __init__(self):
        """Initialize the tool."""
        self._name = self.get_name()
        self._description = self.get_description()
        self._parameters = self.get_parameters()
        self._timeout = self.get_timeout()
    
    @abstractmethod
    def get_name(self) -> str:
        """
        Get the name of this tool.
        
        Returns:
            str: Tool name (used for tool calling)
        """
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """
        Get a description of what this tool does.
        
        Returns:
            str: Human-readable description
        """
        pass
    
    @abstractmethod
    def get_parameters(self) -> List[ToolParameter]:
        """
        Get the parameters this tool accepts.
        
        Returns:
            List of ToolParameter objects describing expected parameters
        """
        pass
    
    @abstractmethod
    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """
        Execute the tool with the given parameters.
        
        Args:
            parameters: Dictionary of parameter values
            
        Returns:
            ToolResult: Result of the execution
        """
        pass
    
    def get_timeout(self) -> int:
        """
        Get the default timeout for this tool in seconds.
        
        Returns:
            int: Timeout in seconds (default: 30)
        """
        return 30
    
    def validate_parameters(self, parameters: Dict[str, Any]) -> ToolResult:
        """
        Validate the provided parameters against the tool's schema.
        
        Args:
            parameters: Dictionary of parameter values to validate
            
        Returns:
            ToolResult: Success result if valid, error result if invalid
        """
        try:
            # Check for required parameters
            for param in self._parameters:
                if param.required and param.name not in parameters:
                    return ToolResult(
                        status=ToolExecutionStatus.INVALID_PARAMS,
                        output="",
                        error=f"Required parameter '{param.name}' is missing"
                    )
            
            # Check parameter types and values
            for param_name, param_value in parameters.items():
                param_def = self._get_parameter_definition(param_name)
                if param_def:
                    validation_error = self._validate_parameter_value(param_def, param_value)
                    if validation_error:
                        return ToolResult(
                            status=ToolExecutionStatus.INVALID_PARAMS,
                            output="",
                            error=validation_error
                        )
            
            return ToolResult(
                status=ToolExecutionStatus.SUCCESS,
                output="Parameters are valid"
            )
            
        except Exception as e:
            return ToolResult(
                status=ToolExecutionStatus.ERROR,
                output="",
                error=f"Parameter validation failed: {str(e)}"
            )
    
    def get_tool_schema(self) -> Dict[str, Any]:
        """
        Get the JSON schema representation of this tool.
        
        This is used by Foundation Models to understand how to call the tool.
        
        Returns:
            Dict: JSON schema for the tool
        """
        properties = {}
        required = []
        
        for param in self._parameters:
            param_schema = {
                "type": param.type,
                "description": param.description
            }
            
            if param.enum_values:
                param_schema["enum"] = param.enum_values
            
            if param.default is not None:
                param_schema["default"] = param.default
            
            properties[param.name] = param_schema
            
            if param.required:
                required.append(param.name)
        
        return {
            "name": self._name,
            "description": self._description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }
    
    def _get_parameter_definition(self, param_name: str) -> Optional[ToolParameter]:
        """
        Get the parameter definition for a given parameter name.
        
        Args:
            param_name: Name of the parameter
            
        Returns:
            ToolParameter or None if not found
        """
        for param in self._parameters:
            if param.name == param_name:
                return param
        return None
    
    def _validate_parameter_value(self, param_def: ToolParameter, value: Any) -> Optional[str]:
        """
        Validate a parameter value against its definition.
        
        Args:
            param_def: Parameter definition
            value: Value to validate
            
        Returns:
            Error message if invalid, None if valid
        """
        # Type validation (basic)
        expected_type = param_def.type
        
        if expected_type == "string" and not isinstance(value, str):
            return f"Parameter '{param_def.name}' must be a string, got {type(value).__name__}"
        elif expected_type == "integer" and not isinstance(value, int):
            return f"Parameter '{param_def.name}' must be an integer, got {type(value).__name__}"
        elif expected_type == "number" and not isinstance(value, (int, float)):
            return f"Parameter '{param_def.name}' must be a number, got {type(value).__name__}"
        elif expected_type == "boolean" and not isinstance(value, bool):
            return f"Parameter '{param_def.name}' must be a boolean, got {type(value).__name__}"
        elif expected_type == "array" and not isinstance(value, list):
            return f"Parameter '{param_def.name}' must be an array, got {type(value).__name__}"
        elif expected_type == "object" and not isinstance(value, dict):
            return f"Parameter '{param_def.name}' must be an object, got {type(value).__name__}"
        
        # Enum validation
        if param_def.enum_values and value not in param_def.enum_values:
            return f"Parameter '{param_def.name}' must be one of {param_def.enum_values}, got {value}"
        
        return None
    
    def __str__(self) -> str:
        """String representation of the tool."""
        return f"{self._name}: {self._description}"
    
    def __repr__(self) -> str:
        """Detailed string representation of the tool."""
        return f"<{self.__class__.__name__}(name='{self._name}', parameters={len(self._parameters)})>"


class ToolRegistry:
    """
    Registry for managing available tools.
    
    Provides a central place to register, discover, and retrieve tools
    for use by the DGM agent.
    """
    
    def __init__(self):
        """Initialize the tool registry."""
        self._tools: Dict[str, BaseTool] = {}
    
    def register_tool(self, tool: BaseTool) -> None:
        """
        Register a tool in the registry.
        
        Args:
            tool: Tool instance to register
        """
        self._tools[tool.get_name()] = tool
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """
        Get a tool by name.
        
        Args:
            name: Name of the tool
            
        Returns:
            BaseTool instance or None if not found
        """
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        """
        Get a list of all registered tool names.
        
        Returns:
            List of tool names
        """
        return list(self._tools.keys())
    
    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        Get JSON schemas for all registered tools.
        
        Returns:
            List of tool schemas for Foundation Model consumption
        """
        return [tool.get_tool_schema() for tool in self._tools.values()]
    
    async def execute_tool(self, name: str, parameters: Dict[str, Any]) -> ToolResult:
        """
        Execute a tool by name with the given parameters.
        
        Args:
            name: Name of the tool to execute
            parameters: Parameters to pass to the tool
            
        Returns:
            ToolResult: Result of the execution
        """
        tool = self.get_tool(name)
        if not tool:
            return ToolResult(
                status=ToolExecutionStatus.ERROR,
                output="",
                error=f"Tool '{name}' not found in registry"
            )
        
        # Validate parameters first
        validation_result = tool.validate_parameters(parameters)
        if validation_result.status != ToolExecutionStatus.SUCCESS:
            return validation_result
        
        # Execute the tool
        try:
            return await tool.execute(parameters)
        except Exception as e:
            return ToolResult(
                status=ToolExecutionStatus.ERROR,
                output="",
                error=f"Tool execution failed: {str(e)}"
            )