"""
Agent archive management for maintaining a population of agent variants.
"""

import os
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import hashlib


@dataclass
class ArchiveEntry:
    """Represents an entry in the agent archive."""
    agent_id: str
    agent_path: str
    parent_id: Optional[str]
    generation: int
    fitness_score: float
    novelty_score: float
    benchmark_results: Dict[str, Any]
    modifications: List[str]
    timestamp: str
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ArchiveEntry':
        """Create from dictionary."""
        return cls(**data)


class AgentArchive:
    """
    Manages a population archive of agent variants.
    
    The archive stores agent code, performance metrics, and genealogy
    to support population-based evolution.
    """
    
    def __init__(self, archive_dir: str, max_size: int = 100):
        """
        Initialize the agent archive.
        
        Args:
            archive_dir: Directory to store archive
            max_size: Maximum number of agents to keep
        """
        self.archive_dir = Path(archive_dir)
        self.max_size = max_size
        self.entries: Dict[str, ArchiveEntry] = {}
        
        # Create archive directory
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        
        # Load existing archive
        self._load_archive()
    
    def _load_archive(self):
        """Load archive from disk."""
        index_path = self.archive_dir / "index.json"
        if index_path.exists():
            with open(index_path, 'r') as f:
                data = json.load(f)
                for entry_data in data.get('entries', []):
                    entry = ArchiveEntry.from_dict(entry_data)
                    self.entries[entry.agent_id] = entry
    
    def _save_archive(self):
        """Save archive index to disk."""
        index_path = self.archive_dir / "index.json"
        data = {
            'entries': [entry.to_dict() for entry in self.entries.values()],
            'last_updated': datetime.now().isoformat()
        }
        with open(index_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _generate_agent_id(self, agent_path: str) -> str:
        """Generate unique ID for an agent."""
        # Use hash of agent code + timestamp
        with open(agent_path, 'r') as f:
            content = f.read()
        
        hash_input = f"{content}{datetime.now().isoformat()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    
    def add_agent(
        self,
        agent_path: str,
        parent_id: Optional[str],
        fitness_score: float,
        novelty_score: float,
        benchmark_results: Dict[str, Any],
        modifications: List[str],
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add an agent to the archive.
        
        Args:
            agent_path: Path to agent code
            parent_id: ID of parent agent (if any)
            fitness_score: Agent's fitness score
            novelty_score: Agent's novelty score
            benchmark_results: Results from benchmarks
            modifications: List of modifications made
            metadata: Additional metadata
            
        Returns:
            Agent ID
        """
        # Generate agent ID
        agent_id = self._generate_agent_id(agent_path)
        
        # Determine generation
        generation = 0
        if parent_id and parent_id in self.entries:
            generation = self.entries[parent_id].generation + 1
        
        # Copy agent to archive
        agent_archive_path = self.archive_dir / f"agent_{agent_id}.py"
        shutil.copy2(agent_path, agent_archive_path)
        
        # Create archive entry
        entry = ArchiveEntry(
            agent_id=agent_id,
            agent_path=str(agent_archive_path),
            parent_id=parent_id,
            generation=generation,
            fitness_score=fitness_score,
            novelty_score=novelty_score,
            benchmark_results=benchmark_results,
            modifications=modifications,
            timestamp=datetime.now().isoformat(),
            metadata=metadata or {}
        )
        
        self.entries[agent_id] = entry
        
        # Maintain size limit
        self._enforce_size_limit()
        
        # Save archive
        self._save_archive()
        
        return agent_id
    
    def _enforce_size_limit(self):
        """Remove oldest/worst agents if over size limit."""
        if len(self.entries) <= self.max_size:
            return
        
        # Sort by combined score (fitness + novelty)
        sorted_entries = sorted(
            self.entries.values(),
            key=lambda e: e.fitness_score + e.novelty_score,
            reverse=True
        )
        
        # Keep top agents
        to_keep = sorted_entries[:self.max_size]
        kept_ids = {e.agent_id for e in to_keep}
        
        # Remove others
        for agent_id in list(self.entries.keys()):
            if agent_id not in kept_ids:
                # Remove agent file
                agent_path = Path(self.entries[agent_id].agent_path)
                if agent_path.exists():
                    agent_path.unlink()
                
                # Remove from entries
                del self.entries[agent_id]
    
    def get_agent(self, agent_id: str) -> Optional[ArchiveEntry]:
        """Get an agent entry by ID."""
        return self.entries.get(agent_id)
    
    def get_all_agents(self) -> List[ArchiveEntry]:
        """Get all agents in the archive."""
        return list(self.entries.values())
    
    def get_top_agents(self, n: int = 10) -> List[ArchiveEntry]:
        """Get top N agents by combined score."""
        sorted_entries = sorted(
            self.entries.values(),
            key=lambda e: e.fitness_score + e.novelty_score,
            reverse=True
        )
        return sorted_entries[:n]
    
    def get_lineage(self, agent_id: str) -> List[ArchiveEntry]:
        """Get the lineage of an agent (ancestors)."""
        lineage = []
        current_id = agent_id
        
        while current_id:
            if current_id not in self.entries:
                break
            
            entry = self.entries[current_id]
            lineage.append(entry)
            current_id = entry.parent_id
        
        return lineage
    
    def get_descendants(self, agent_id: str) -> List[ArchiveEntry]:
        """Get all descendants of an agent."""
        descendants = []
        
        for entry in self.entries.values():
            if entry.parent_id == agent_id:
                descendants.append(entry)
                # Recursively get descendants
                descendants.extend(self.get_descendants(entry.agent_id))
        
        return descendants
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get archive statistics."""
        if not self.entries:
            return {
                'total_agents': 0,
                'generations': 0,
                'avg_fitness': 0.0,
                'avg_novelty': 0.0,
                'best_fitness': 0.0,
                'best_novelty': 0.0
            }
        
        fitness_scores = [e.fitness_score for e in self.entries.values()]
        novelty_scores = [e.novelty_score for e in self.entries.values()]
        generations = [e.generation for e in self.entries.values()]
        
        return {
            'total_agents': len(self.entries),
            'generations': max(generations) + 1,
            'avg_fitness': sum(fitness_scores) / len(fitness_scores),
            'avg_novelty': sum(novelty_scores) / len(novelty_scores),
            'best_fitness': max(fitness_scores),
            'best_novelty': max(novelty_scores)
        }