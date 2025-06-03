"""
Agent Archive Management for DGM.

Manages the collection of all discovered agents, their metadata,
performance scores, and lineage information.
"""

import json
import os
import shutil
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class ArchivedAgent:
    """Represents an agent stored in the archive."""
    
    agent_id: str
    parent_id: Optional[str]
    generation: int
    source_path: str  # Path to agent's code
    created_at: str
    benchmark_scores: Dict[str, float]
    average_score: float
    is_valid: bool
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ArchivedAgent':
        """Create from dictionary."""
        return cls(**data)


class AgentArchive:
    """Manages the archive of all discovered agents."""
    
    def __init__(self, archive_dir: str = "./archive/agents"):
        """
        Initialize the agent archive.
        
        Args:
            archive_dir: Directory to store archived agents
        """
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.archive_dir / "archive_metadata.json"
        self.agents: Dict[str, ArchivedAgent] = {}
        self._load_archive()
    
    def _load_archive(self) -> None:
        """Load existing archive from disk."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r') as f:
                    data = json.load(f)
                    for agent_id, agent_data in data.get('agents', {}).items():
                        self.agents[agent_id] = ArchivedAgent.from_dict(agent_data)
                logger.info(f"Loaded {len(self.agents)} agents from archive")
            except Exception as e:
                logger.error(f"Failed to load archive: {e}")
                self.agents = {}
    
    def _save_archive(self) -> None:
        """Save archive metadata to disk."""
        try:
            data = {
                'agents': {
                    agent_id: agent.to_dict() 
                    for agent_id, agent in self.agents.items()
                },
                'last_updated': datetime.now().isoformat()
            }
            with open(self.metadata_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("Archive metadata saved")
        except Exception as e:
            logger.error(f"Failed to save archive: {e}")
    
    def add_agent(
        self,
        agent_path: str,
        parent_id: Optional[str] = None,
        benchmark_scores: Optional[Dict[str, float]] = None,
        is_valid: bool = True,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ArchivedAgent:
        """
        Add a new agent to the archive.
        
        Args:
            agent_path: Path to the agent's source code directory
            parent_id: ID of the parent agent (if any)
            benchmark_scores: Scores on various benchmarks
            is_valid: Whether the agent passed validation
            metadata: Additional metadata
            
        Returns:
            The archived agent
        """
        agent_id = str(uuid.uuid4())
        
        # Determine generation
        generation = 0
        if parent_id and parent_id in self.agents:
            generation = self.agents[parent_id].generation + 1
        
        # Copy agent code to archive
        agent_archive_path = self.archive_dir / agent_id
        if os.path.exists(agent_path):
            if os.path.isfile(agent_path):
                # If it's a single file, create directory and copy file
                agent_archive_path.mkdir(parents=True, exist_ok=True)
                shutil.copy2(agent_path, agent_archive_path / os.path.basename(agent_path))
            else:
                # If it's a directory, copy the whole directory
                shutil.copytree(agent_path, agent_archive_path)
        
        # Calculate average score
        scores = benchmark_scores or {}
        average_score = sum(scores.values()) / len(scores) if scores else 0.0
        
        # Create archived agent
        agent = ArchivedAgent(
            agent_id=agent_id,
            parent_id=parent_id,
            generation=generation,
            source_path=str(agent_archive_path),
            created_at=datetime.now().isoformat(),
            benchmark_scores=scores,
            average_score=average_score,
            is_valid=is_valid,
            metadata=metadata or {}
        )
        
        self.agents[agent_id] = agent
        self._save_archive()
        
        logger.info(f"Added agent {agent_id} to archive (gen {generation}, score: {average_score:.2f})")
        return agent
    
    def get_agent(self, agent_id: str) -> Optional[ArchivedAgent]:
        """Get an agent by ID."""
        return self.agents.get(agent_id)
    
    def get_all_agents(self) -> List[ArchivedAgent]:
        """Get all agents in the archive."""
        return list(self.agents.values())
    
    def get_valid_agents(self) -> List[ArchivedAgent]:
        """Get all valid agents."""
        return [agent for agent in self.agents.values() if agent.is_valid]
    
    def get_top_agents(self, n: int = 10) -> List[ArchivedAgent]:
        """Get top N agents by average score."""
        valid_agents = self.get_valid_agents()
        return sorted(valid_agents, key=lambda a: a.average_score, reverse=True)[:n]
    
    def get_agent_children(self, agent_id: str) -> List[ArchivedAgent]:
        """Get all children of a specific agent."""
        return [
            agent for agent in self.agents.values()
            if agent.parent_id == agent_id
        ]
    
    def get_agent_lineage(self, agent_id: str) -> List[ArchivedAgent]:
        """Get the full lineage of an agent (ancestors)."""
        lineage = []
        current_id = agent_id
        
        while current_id:
            agent = self.get_agent(current_id)
            if not agent:
                break
            lineage.append(agent)
            current_id = agent.parent_id
        
        return list(reversed(lineage))
    
    def get_archive_statistics(self) -> Dict[str, Any]:
        """Get statistics about the archive."""
        valid_agents = self.get_valid_agents()
        all_scores = [a.average_score for a in valid_agents]
        
        return {
            'total_agents': len(self.agents),
            'valid_agents': len(valid_agents),
            'average_score': sum(all_scores) / len(all_scores) if all_scores else 0,
            'best_score': max(all_scores) if all_scores else 0,
            'worst_score': min(all_scores) if all_scores else 0,
            'max_generation': max((a.generation for a in self.agents.values()), default=0)
        }