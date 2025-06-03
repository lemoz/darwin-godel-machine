"""
DGM Agent package.

This package contains the core agent implementation for the Darwin Gödel Machine,
including Foundation Model interfaces, tools, and the main agent logic.
"""

from .agent import Agent, Task, AgentConfig

__version__ = "0.1.0"
__all__ = ["Agent", "Task", "AgentConfig"]