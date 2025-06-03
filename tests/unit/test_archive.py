"""
Unit tests for archive management components.
"""

import unittest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from archive.agent_archive import AgentArchive, ArchivedAgent
from archive.parent_selector import ParentSelector
from archive.novelty_calculator import NoveltyCalculator
from tests.test_utils import TestFixtures, cleanup_test_directory


class TestAgentArchive(unittest.TestCase):
    """Test cases for AgentArchive."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_archive_"))
        self.archive = AgentArchive(archive_path=str(self.temp_dir))
        
        # Create test agent directories
        self.agent1_path = self.temp_dir / "agent1"
        self.agent2_path = self.temp_dir / "agent2"
        TestFixtures.create_mock_agent_code(self.agent1_path)
        TestFixtures.create_mock_agent_code(self.agent2_path)
    
    def tearDown(self):
        """Clean up test fixtures."""
        cleanup_test_directory(self.temp_dir)
    
    def test_add_agent(self):
        """Test adding an agent to the archive."""
        agent = self.archive.add_agent(
            agent_path=str(self.agent1_path),
            parent_id=None,
            benchmark_scores={'test': 0.8}
        )
        
        self.assertIsInstance(agent, ArchivedAgent)
        self.assertIn(agent.agent_id, self.archive.agents)
        self.assertEqual(agent.performance_score, 0.8)
        self.assertEqual(agent.generation, 0)
        self.assertIsNone(agent.parent_id)
    
    def test_add_agent_with_parent(self):
        """Test adding an agent with a parent."""
        # Add parent
        parent = self.archive.add_agent(
            agent_path=str(self.agent1_path),
            benchmark_scores={'test': 0.7}
        )
        
        # Add child
        child = self.archive.add_agent(
            agent_path=str(self.agent2_path),
            parent_id=parent.agent_id,
            benchmark_scores={'test': 0.9}
        )
        
        self.assertEqual(child.parent_id, parent.agent_id)
        self.assertEqual(child.generation, 1)
        self.assertEqual(child.performance_score, 0.9)
    
    def test_get_top_agents(self):
        """Test retrieving top performing agents."""
        # Add multiple agents
        scores = [0.5, 0.8, 0.3, 0.9, 0.7]
        agents = []
        
        for i, score in enumerate(scores):
            agent_path = self.temp_dir / f"agent_{i}"
            TestFixtures.create_mock_agent_code(agent_path)
            agent = self.archive.add_agent(
                agent_path=str(agent_path),
                benchmark_scores={'test': score}
            )
            agents.append(agent)
        
        # Get top 3
        top_agents = self.archive.get_top_agents(n=3)
        
        self.assertEqual(len(top_agents), 3)
        self.assertEqual(top_agents[0].performance_score, 0.9)
        self.assertEqual(top_agents[1].performance_score, 0.8)
        self.assertEqual(top_agents[2].performance_score, 0.7)
    
    def test_get_agent_lineage(self):
        """Test retrieving agent lineage."""
        # Create lineage: grandparent -> parent -> child
        grandparent = self.archive.add_agent(
            agent_path=str(self.agent1_path),
            benchmark_scores={'test': 0.5}
        )
        
        parent_path = self.temp_dir / "parent"
        TestFixtures.create_mock_agent_code(parent_path)
        parent = self.archive.add_agent(
            agent_path=str(parent_path),
            parent_id=grandparent.agent_id,
            benchmark_scores={'test': 0.7}
        )
        
        child = self.archive.add_agent(
            agent_path=str(self.agent2_path),
            parent_id=parent.agent_id,
            benchmark_scores={'test': 0.9}
        )
        
        lineage = self.archive.get_agent_lineage(child.agent_id)
        
        self.assertEqual(len(lineage), 3)
        self.assertEqual(lineage[0].agent_id, grandparent.agent_id)
        self.assertEqual(lineage[1].agent_id, parent.agent_id)
        self.assertEqual(lineage[2].agent_id, child.agent_id)
    
    def test_save_and_load_metadata(self):
        """Test saving and loading archive metadata."""
        # Add agents
        agent1 = self.archive.add_agent(
            agent_path=str(self.agent1_path),
            benchmark_scores={'test': 0.8}
        )
        
        agent2 = self.archive.add_agent(
            agent_path=str(self.agent2_path),
            parent_id=agent1.agent_id,
            benchmark_scores={'test': 0.9}
        )
        
        # Save metadata
        self.archive.save_metadata()
        
        # Create new archive instance and load
        new_archive = AgentArchive(archive_path=str(self.temp_dir))
        
        self.assertEqual(len(new_archive.agents), 2)
        self.assertIn(agent1.agent_id, new_archive.agents)
        self.assertIn(agent2.agent_id, new_archive.agents)


class TestParentSelector(unittest.TestCase):
    """Test cases for ParentSelector."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_selector_"))
        self.archive = AgentArchive(archive_path=str(self.temp_dir))
        self.selector = ParentSelector(
            archive=self.archive,
            performance_weight=0.7,
            novelty_weight=0.3
        )
        
        # Add test agents
        self.agents = []
        for i in range(5):
            agent_path = self.temp_dir / f"agent_{i}"
            TestFixtures.create_mock_agent_code(agent_path)
            agent = self.archive.add_agent(
                agent_path=str(agent_path),
                benchmark_scores={'test': 0.1 + i * 0.2}
            )
            self.agents.append(agent)
    
    def tearDown(self):
        """Clean up test fixtures."""
        cleanup_test_directory(self.temp_dir)
    
    def test_select_parent(self):
        """Test parent selection."""
        # Select parent multiple times
        selections = []
        for _ in range(100):
            parent = self.selector.select_parent()
            if parent:
                selections.append(parent.agent_id)
        
        # Higher scoring agents should be selected more often
        self.assertGreater(len(selections), 0)
        
        # Count selections
        selection_counts = {}
        for agent_id in selections:
            selection_counts[agent_id] = selection_counts.get(agent_id, 0) + 1
        
        # Verify that higher scoring agents are selected more
        for i in range(len(self.agents) - 1):
            agent1 = self.agents[i]
            agent2 = self.agents[i + 1]
            if agent1.agent_id in selection_counts and agent2.agent_id in selection_counts:
                # Agent2 has higher score, should be selected more
                self.assertLessEqual(
                    selection_counts.get(agent1.agent_id, 0),
                    selection_counts.get(agent2.agent_id, 0) * 2  # Allow some randomness
                )
    
    def test_select_parent_with_exclusion(self):
        """Test parent selection with exclusion list."""
        # Exclude top 2 agents
        exclude_ids = [self.agents[-1].agent_id, self.agents[-2].agent_id]
        
        parent = self.selector.select_parent(exclude_ids=exclude_ids)
        
        self.assertIsNotNone(parent)
        self.assertNotIn(parent.agent_id, exclude_ids)
    
    def test_select_parent_with_min_score(self):
        """Test parent selection with minimum score threshold."""
        parent = self.selector.select_parent(min_score=0.5)
        
        self.assertIsNotNone(parent)
        self.assertGreaterEqual(parent.performance_score, 0.5)


class TestNoveltyCalculator(unittest.TestCase):
    """Test cases for NoveltyCalculator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_novelty_"))
        self.calculator = NoveltyCalculator()
        
        # Create test agents with different code
        self.agent1_path = self.temp_dir / "agent1"
        self.agent2_path = self.temp_dir / "agent2"
        TestFixtures.create_mock_agent_code(self.agent1_path)
        TestFixtures.create_mock_agent_code(self.agent2_path)
        
        # Modify agent2 code slightly
        agent2_file = self.agent2_path / "agent" / "agent.py"
        content = agent2_file.read_text()
        modified_content = content.replace("test agent", "modified test agent")
        modified_content += "\n\ndef new_method(self):\n    pass\n"
        agent2_file.write_text(modified_content)
    
    def tearDown(self):
        """Clean up test fixtures."""
        cleanup_test_directory(self.temp_dir)
    
    def test_calculate_novelty_identical(self):
        """Test novelty calculation for identical agents."""
        agent1 = ArchivedAgent(
            agent_id="agent1",
            code_path=str(self.agent1_path),
            timestamp=datetime.now(),
            parent_id=None,
            generation=0,
            performance_score=0.8,
            benchmark_scores={'test': 0.8},
            metadata={}
        )
        
        agent2 = ArchivedAgent(
            agent_id="agent2",
            code_path=str(self.agent1_path),  # Same path, identical code
            timestamp=datetime.now(),
            parent_id=None,
            generation=0,
            performance_score=0.8,
            benchmark_scores={'test': 0.8},
            metadata={}
        )
        
        novelty = self.calculator.calculate_novelty(agent1, [agent2])
        
        # Identical agents should have very low novelty
        self.assertLess(novelty, 0.1)
    
    def test_calculate_novelty_different(self):
        """Test novelty calculation for different agents."""
        agent1 = ArchivedAgent(
            agent_id="agent1",
            code_path=str(self.agent1_path),
            timestamp=datetime.now(),
            parent_id=None,
            generation=0,
            performance_score=0.8,
            benchmark_scores={'test': 0.8},
            metadata={}
        )
        
        agent2 = ArchivedAgent(
            agent_id="agent2",
            code_path=str(self.agent2_path),  # Different code
            timestamp=datetime.now(),
            parent_id=None,
            generation=0,
            performance_score=0.5,
            benchmark_scores={'test': 0.5},
            metadata={}
        )
        
        novelty = self.calculator.calculate_novelty(agent1, [agent2])
        
        # Different agents should have higher novelty
        self.assertGreater(novelty, 0.3)
    
    def test_calculate_novelty_multiple_agents(self):
        """Test novelty calculation against multiple agents."""
        target_agent = ArchivedAgent(
            agent_id="target",
            code_path=str(self.agent1_path),
            timestamp=datetime.now(),
            parent_id=None,
            generation=0,
            performance_score=0.8,
            benchmark_scores={'test': 0.8},
            metadata={}
        )
        
        compare_agents = []
        for i in range(3):
            agent = ArchivedAgent(
                agent_id=f"compare_{i}",
                code_path=str(self.agent1_path) if i < 2 else str(self.agent2_path),
                timestamp=datetime.now(),
                parent_id=None,
                generation=0,
                performance_score=0.5 + i * 0.1,
                benchmark_scores={'test': 0.5 + i * 0.1},
                metadata={}
            )
            compare_agents.append(agent)
        
        novelty = self.calculator.calculate_novelty(target_agent, compare_agents)
        
        # Should be between 0 and 1
        self.assertGreaterEqual(novelty, 0.0)
        self.assertLessEqual(novelty, 1.0)


if __name__ == '__main__':
    unittest.main()