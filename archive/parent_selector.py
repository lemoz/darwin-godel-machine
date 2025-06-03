"""
Parent selection strategies for evolutionary agent improvement.
"""

import random
from typing import List, Optional, Tuple
from abc import ABC, abstractmethod

from .archive_manager import ArchiveEntry, AgentArchive


class SelectionStrategy(ABC):
    """Abstract base class for selection strategies."""
    
    @abstractmethod
    def select(self, archive: AgentArchive, n_parents: int = 1) -> List[ArchiveEntry]:
        """Select parents from the archive."""
        pass


class FitnessProportionalSelection(SelectionStrategy):
    """Select parents proportional to their fitness scores."""
    
    def select(self, archive: AgentArchive, n_parents: int = 1) -> List[ArchiveEntry]:
        """Select parents using fitness proportional selection."""
        agents = archive.get_all_agents()
        if not agents:
            return []
        
        # Calculate fitness sum
        fitness_sum = sum(max(0.01, a.fitness_score) for a in agents)  # Min 0.01 to avoid zero
        
        # Calculate selection probabilities
        probabilities = [max(0.01, a.fitness_score) / fitness_sum for a in agents]
        
        # Select parents
        selected = random.choices(agents, weights=probabilities, k=n_parents)
        return selected


class TournamentSelection(SelectionStrategy):
    """Select parents using tournament selection."""
    
    def __init__(self, tournament_size: int = 3):
        self.tournament_size = tournament_size
    
    def select(self, archive: AgentArchive, n_parents: int = 1) -> List[ArchiveEntry]:
        """Select parents using tournament selection."""
        agents = archive.get_all_agents()
        if not agents:
            return []
        
        selected = []
        for _ in range(n_parents):
            # Run tournament
            tournament = random.sample(agents, min(self.tournament_size, len(agents)))
            winner = max(tournament, key=lambda a: a.fitness_score)
            selected.append(winner)
        
        return selected


class EliteSelection(SelectionStrategy):
    """Always select the top performing agents."""
    
    def select(self, archive: AgentArchive, n_parents: int = 1) -> List[ArchiveEntry]:
        """Select top agents by fitness."""
        return archive.get_top_agents(n_parents)


class NoveltySelection(SelectionStrategy):
    """Select parents based on novelty scores."""
    
    def select(self, archive: AgentArchive, n_parents: int = 1) -> List[ArchiveEntry]:
        """Select parents with highest novelty scores."""
        agents = archive.get_all_agents()
        if not agents:
            return []
        
        # Sort by novelty score
        sorted_agents = sorted(agents, key=lambda a: a.novelty_score, reverse=True)
        return sorted_agents[:n_parents]


class HybridSelection(SelectionStrategy):
    """Combine fitness and novelty for selection."""
    
    def __init__(self, fitness_weight: float = 0.7, novelty_weight: float = 0.3):
        self.fitness_weight = fitness_weight
        self.novelty_weight = novelty_weight
    
    def select(self, archive: AgentArchive, n_parents: int = 1) -> List[ArchiveEntry]:
        """Select parents using combined fitness and novelty scores."""
        agents = archive.get_all_agents()
        if not agents:
            return []
        
        # Calculate combined scores
        for agent in agents:
            # For now, use average_score as fitness and 0 for novelty
            # TODO: Implement proper novelty calculation
            agent._combined_score = (
                self.fitness_weight * agent.average_score +
                self.novelty_weight * 0  # Novelty not yet implemented
            )
        
        # Sort by combined score
        sorted_agents = sorted(agents, key=lambda a: a._combined_score, reverse=True)
        
        # Clean up temporary attribute
        for agent in agents:
            delattr(agent, '_combined_score')
        
        return sorted_agents[:n_parents]


class ParentSelector:
    """
    Manages parent selection for agent evolution.
    
    Supports multiple selection strategies to choose parent agents
    from the archive for creating new variants.
    """
    
    def __init__(self, strategy: Optional[SelectionStrategy] = None):
        """
        Initialize parent selector.
        
        Args:
            strategy: Selection strategy to use (default: TournamentSelection)
        """
        self.strategy = strategy or TournamentSelection()
    
    def select_parents(
        self,
        archive: AgentArchive,
        n_parents: int = 1
    ) -> List[ArchiveEntry]:
        """
        Select parent agents from the archive.
        
        Args:
            archive: Agent archive to select from
            n_parents: Number of parents to select
            
        Returns:
            List of selected parent entries
        """
        return self.strategy.select(archive, n_parents)
    
    def select_parent_pair(
        self,
        archive: AgentArchive
    ) -> Tuple[Optional[ArchiveEntry], Optional[ArchiveEntry]]:
        """
        Select a pair of parents for crossover.
        
        Args:
            archive: Agent archive to select from
            
        Returns:
            Tuple of two parent entries
        """
        parents = self.select_parents(archive, n_parents=2)
        
        if len(parents) == 0:
            return None, None
        elif len(parents) == 1:
            return parents[0], None
        else:
            return parents[0], parents[1]
    
    def set_strategy(self, strategy: SelectionStrategy):
        """Change the selection strategy."""
        self.strategy = strategy
    
    @staticmethod
    def get_available_strategies() -> dict:
        """Get available selection strategies."""
        return {
            'fitness_proportional': FitnessProportionalSelection,
            'tournament': TournamentSelection,
            'elite': EliteSelection,
            'novelty': NoveltySelection,
            'hybrid': HybridSelection
        }