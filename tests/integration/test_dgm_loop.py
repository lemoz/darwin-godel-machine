"""
Integration tests for the full DGM loop.
"""

import unittest
import asyncio
from pathlib import Path
import tempfile
import json
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.test_utils import TestFixtures
from dgm_controller import DGMController
from archive.agent_archive import AgentArchive
from evaluation.benchmark_runner import BenchmarkRunner
from self_modification.performance_diagnosis import PerformanceDiagnosis
from self_modification.modification_proposal import ModificationProposer
from self_modification.implementation import ImplementationManager
from agent.fm_interface.api_handler import ApiHandler


class TestDGMLoop(unittest.TestCase):
    """Test the full DGM loop integration."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)
        
        # Create config
        self.config = {
            "dgm": {
                "max_generations": 2,
                "archive_size": 5,
                "parent_selection": {
                    "performance_weight": 0.7,
                    "novelty_weight": 0.3,
                    "archive_percentage": 0.2
                },
                "benchmarks": ["string_manipulation"]
            },
            "fm_interface": {
                "provider": "anthropic",
                "model": "claude-3-sonnet-20240229",
                "max_retries": 3
            },
            "logging": {
                "level": "INFO",
                "file": str(self.test_path / "dgm.log")
            }
        }
        
        # Create directories
        (self.test_path / "agents").mkdir(parents=True)
        (self.test_path / "benchmarks").mkdir(parents=True)
        (self.test_path / "logs").mkdir(parents=True)
        
        # Create a simple benchmark config
        benchmark_config = {
            "name": "string_manipulation",
            "type": "coding",
            "tasks": [
                {
                    "id": "reverse_string",
                    "description": "Reverse a string",
                    "input": "hello",
                    "expected_output": "olleh"
                }
            ],
            "timeout": 30,
            "scoring": {
                "method": "binary",
                "max_score": 1.0
            }
        }
        
        with open(self.test_path / "benchmarks" / "string_manipulation.yaml", "w") as f:
            import yaml
            yaml.dump(benchmark_config, f)
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.test_dir)
    
    @patch('agent.fm_interface.api_handler.FMInterface.generate_response')
    @patch('dgm.evaluation.benchmark_runner.BenchmarkRunner.run_agent_benchmark')
    async def test_full_dgm_generation_cycle(self, mock_run_benchmark, mock_generate):
        """Test a complete DGM generation cycle."""
        # Mock FM responses for self-modification
        mock_generate.side_effect = [
            # First call: performance diagnosis
            AsyncMock(return_value=json.dumps({
                "analysis": "Agent failed on string reversal",
                "weaknesses": ["Missing string manipulation logic"],
                "suggestions": ["Add string reversal function"]
            }))(),
            # Second call: modification proposal
            AsyncMock(return_value=json.dumps({
                "modifications": [
                    {
                        "type": "add_function",
                        "location": "agent.py",
                        "code": "def reverse_string(s): return s[::-1]",
                        "rationale": "Add string reversal capability"
                    }
                ]
            }))(),
            # Third call: implementation
            AsyncMock(return_value=json.dumps({
                "success": True,
                "changes": ["Added reverse_string function"]
            }))()
        ]
        
        # Mock benchmark results
        mock_run_benchmark.side_effect = [
            # Initial agent fails
            {
                "agent_id": "agent_0",
                "benchmark": "string_manipulation",
                "score": 0.0,
                "tasks": {
                    "reverse_string": {
                        "status": "failed",
                        "output": "hello",
                        "expected": "olleh"
                    }
                }
            },
            # Modified agent succeeds
            {
                "agent_id": "agent_1",
                "benchmark": "string_manipulation",
                "score": 1.0,
                "tasks": {
                    "reverse_string": {
                        "status": "passed",
                        "output": "olleh",
                        "expected": "olleh"
                    }
                }
            }
        ]
        
        # Create initial agent
        agent_path = self.test_path / "agents" / "agent_0"
        TestFixtures.create_mock_agent_code(agent_path)
        
        # Initialize DGM controller
        controller = DGMController(self.config, str(self.test_path))
        
        # Run one generation
        await controller.run_generation(generation=0)
        
        # Verify archive was updated
        archive = AgentArchive(str(self.test_path / "agents"))
        agents = archive.get_all_agents()
        self.assertEqual(len(agents), 2)  # Initial + modified
        
        # Verify performance improvement
        self.assertEqual(agents[0]["performance"]["score"], 0.0)
        self.assertEqual(agents[1]["performance"]["score"], 1.0)
        
        # Verify parent-child relationship
        self.assertEqual(agents[1]["parent_id"], "agent_0")
    
    @patch('agent.fm_interface.api_handler.FMInterface.generate_response')
    async def test_multi_generation_evolution(self, mock_generate):
        """Test multiple generations of evolution."""
        # Mock FM to always suggest improvements
        mock_generate.return_value = AsyncMock(return_value=json.dumps({
            "modifications": [{
                "type": "optimize",
                "location": "agent.py",
                "code": "# Optimized version",
                "rationale": "Performance improvement"
            }]
        }))
        
        # Create initial population
        for i in range(3):
            agent_path = self.test_path / "agents" / f"agent_{i}"
            TestFixtures.create_mock_agent_code(agent_path)
        
        controller = DGMController(self.config, str(self.test_path))
        
        # Mock benchmark to show gradual improvement
        with patch('dgm.evaluation.benchmark_runner.BenchmarkRunner.run_agent_benchmark') as mock_bench:
            scores = [0.3, 0.5, 0.7, 0.8, 0.9]
            mock_bench.side_effect = [
                {
                    "agent_id": f"agent_{i}",
                    "benchmark": "string_manipulation",
                    "score": scores[min(i, len(scores)-1)]
                }
                for i in range(10)  # Enough for multiple generations
            ]
            
            # Run multiple generations
            for gen in range(2):
                await controller.run_generation(generation=gen)
            
            # Verify population evolved
            archive = AgentArchive(str(self.test_path / "agents"))
            agents = archive.get_all_agents()
            
            # Should have more agents due to evolution
            self.assertGreater(len(agents), 3)
            
            # Average score should improve
            avg_score = sum(a["performance"]["score"] for a in agents) / len(agents)
            self.assertGreater(avg_score, 0.3)
    
    @patch('dgm.self_modification.implementation.ImplementationManager.apply_modifications')
    async def test_rollback_on_failure(self, mock_apply):
        """Test rollback when modifications fail."""
        # Make apply_modifications fail
        mock_apply.side_effect = Exception("Modification failed")
        
        # Create initial agent
        agent_path = self.test_path / "agents" / "agent_0"
        TestFixtures.create_mock_agent_code(agent_path)
        original_content = (agent_path / "agent.py").read_text()
        
        controller = DGMController(self.config, str(self.test_path))
        
        with patch('agent.fm_interface.api_handler.FMInterface.generate_response') as mock_fm:
            mock_fm.return_value = AsyncMock(return_value=json.dumps({
                "modifications": [{
                    "type": "break_everything",
                    "location": "agent.py",
                    "code": "raise Exception('Broken')",
                    "rationale": "Test failure"
                }]
            }))
            
            with patch('dgm.evaluation.benchmark_runner.BenchmarkRunner.run_agent_benchmark') as mock_bench:
                mock_bench.return_value = {
                    "agent_id": "agent_0",
                    "score": 0.5
                }
                
                # Run generation - should handle failure gracefully
                await controller.run_generation(generation=0)
                
                # Original agent should be unchanged
                current_content = (agent_path / "agent.py").read_text()
                self.assertEqual(original_content, current_content)
    
    async def test_archive_management(self):
        """Test archive size limits and cleanup."""
        # Set small archive size
        self.config["dgm"]["archive_size"] = 3
        
        controller = DGMController(self.config, str(self.test_path))
        archive = AgentArchive(str(self.test_path / "agents"))
        
        # Create more agents than archive size
        for i in range(5):
            agent_path = self.test_path / "agents" / f"agent_{i}"
            TestFixtures.create_mock_agent_code(agent_path)
            
            # Add to archive with varying scores
            result = TestFixtures.create_benchmark_results(
                agent_id=f"agent_{i}",
                score=i * 0.2  # 0.0, 0.2, 0.4, 0.6, 0.8
            )
            archive.add_agent(f"agent_{i}", result)
        
        # Archive should maintain size limit
        agents = archive.get_all_agents()
        self.assertLessEqual(len(agents), 3)
        
        # Should keep best performing agents
        scores = [a["performance"]["score"] for a in agents]
        self.assertIn(0.8, scores)  # Best score
        self.assertIn(0.6, scores)  # Second best
    
    async def test_parent_selection_integration(self):
        """Test parent selection with real archive data."""
        controller = DGMController(self.config, str(self.test_path))
        archive = AgentArchive(str(self.test_path / "agents"))
        
        # Create diverse population
        agent_data = [
            ("agent_0", 0.8, "class Agent: pass"),  # High performance
            ("agent_1", 0.6, "class Agent:\n    def __init__(self): pass"),  # Medium perf, different
            ("agent_2", 0.7, "class Agent: pass"),  # Similar to agent_0
            ("agent_3", 0.5, "import numpy\nclass Agent: pass"),  # Different imports
        ]
        
        for agent_id, score, code in agent_data:
            agent_path = self.test_path / "agents" / agent_id
            agent_path.mkdir(parents=True)
            (agent_path / "agent.py").write_text(code)
            
            result = TestFixtures.create_benchmark_results(
                agent_id=agent_id,
                score=score
            )
            archive.add_agent(agent_id, result)
        
        # Test parent selection multiple times
        parent_counts = {"agent_0": 0, "agent_1": 0, "agent_2": 0, "agent_3": 0}
        
        for _ in range(100):
            parent = archive.parent_selector.select_parent(archive.agents)
            parent_counts[parent["agent_id"]] += 1
        
        # High performance agents should be selected more often
        self.assertGreater(parent_counts["agent_0"], parent_counts["agent_3"])
        
        # But diversity should ensure all get selected sometimes
        for count in parent_counts.values():
            self.assertGreater(count, 0)


if __name__ == "__main__":
    # Run async tests
    unittest.main()