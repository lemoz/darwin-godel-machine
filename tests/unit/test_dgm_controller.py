"""
Unit tests for DGM controller.
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


class TestDGMController(unittest.TestCase):
    """Test DGM controller functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)
        
        # Create config
        self.config = {
            "dgm": {
                "max_generations": 10,
                "archive_size": 20,
                "parent_selection": {
                    "performance_weight": 0.7,
                    "novelty_weight": 0.3,
                    "archive_percentage": 0.2
                },
                "benchmarks": ["test_benchmark"]
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
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.test_dir)
    
    def test_controller_initialization(self):
        """Test DGM controller initialization."""
        controller = DGMController(self.config, str(self.test_path))
        
        self.assertEqual(controller.config, self.config)
        self.assertEqual(controller.workspace, str(self.test_path))
        self.assertIsNotNone(controller.archive)
        self.assertIsNotNone(controller.benchmark_runner)
        self.assertIsNotNone(controller.fm_interface)
        self.assertIsNotNone(controller.logger)
    
    def test_initial_agent_creation(self):
        """Test creation of initial agent when none exists."""
        controller = DGMController(self.config, str(self.test_path))
        
        # Should create agent_0
        agent_id = controller.get_or_create_initial_agent()
        self.assertEqual(agent_id, "agent_0")
        self.assertTrue((self.test_path / "agents" / "agent_0").exists())
        
        # Should reuse existing agent
        agent_id2 = controller.get_or_create_initial_agent()
        self.assertEqual(agent_id2, "agent_0")
    
    @patch('dgm.dgm_controller.BenchmarkRunner.run_agent_benchmark')
    @patch('dgm.dgm_controller.PerformanceDiagnosis.analyze_performance')
    @patch('dgm.dgm_controller.ModificationProposer.propose_modifications')
    @patch('dgm.dgm_controller.ImplementationManager.apply_modifications')
    async def test_run_generation_success(self, mock_apply, mock_propose, 
                                        mock_analyze, mock_benchmark):
        """Test successful generation run."""
        # Mock benchmark results
        mock_benchmark.return_value = {
            "agent_id": "agent_0",
            "benchmark": "test_benchmark",
            "score": 0.5
        }
        
        # Mock diagnosis
        mock_analyze.return_value = {
            "weaknesses": ["Missing optimization"],
            "suggestions": ["Add caching"]
        }
        
        # Mock proposal
        mock_propose.return_value = [{
            "type": "add_function",
            "location": "agent.py",
            "code": "def cache(): pass",
            "rationale": "Add caching"
        }]
        
        # Mock implementation
        mock_apply.return_value = {
            "success": True,
            "new_agent_path": str(self.test_path / "agents" / "agent_1")
        }
        
        # Create initial agent
        agent_path = self.test_path / "agents" / "agent_0"
        TestFixtures.create_mock_agent_code(agent_path)
        
        controller = DGMController(self.config, str(self.test_path))
        
        # Run generation
        await controller.run_generation(generation=0)
        
        # Verify all components were called
        mock_benchmark.assert_called()
        mock_analyze.assert_called()
        mock_propose.assert_called()
        mock_apply.assert_called()
        
        # Verify new agent was created
        self.assertTrue((self.test_path / "agents" / "agent_1").exists())
    
    @patch('dgm.dgm_controller.BenchmarkRunner.run_agent_benchmark')
    async def test_run_generation_benchmark_failure(self, mock_benchmark):
        """Test generation handling benchmark failure."""
        # Mock benchmark failure
        mock_benchmark.side_effect = Exception("Benchmark failed")
        
        # Create initial agent
        agent_path = self.test_path / "agents" / "agent_0"
        TestFixtures.create_mock_agent_code(agent_path)
        
        controller = DGMController(self.config, str(self.test_path))
        
        # Should handle failure gracefully
        await controller.run_generation(generation=0)
        
        # No new agent should be created
        self.assertFalse((self.test_path / "agents" / "agent_1").exists())
    
    @patch('dgm.dgm_controller.BenchmarkRunner.run_agent_benchmark')
    @patch('dgm.dgm_controller.PerformanceDiagnosis.analyze_performance')
    @patch('dgm.dgm_controller.ModificationProposer.propose_modifications')
    @patch('dgm.dgm_controller.ImplementationManager.apply_modifications')
    async def test_modification_failure_handling(self, mock_apply, mock_propose,
                                               mock_analyze, mock_benchmark):
        """Test handling of modification failures."""
        # Mock successful benchmark
        mock_benchmark.return_value = {
            "agent_id": "agent_0",
            "score": 0.5
        }
        
        # Mock successful diagnosis and proposal
        mock_analyze.return_value = {"weaknesses": ["test"]}
        mock_propose.return_value = [{"type": "test"}]
        
        # Mock implementation failure
        mock_apply.side_effect = Exception("Implementation failed")
        
        # Create initial agent
        agent_path = self.test_path / "agents" / "agent_0"
        TestFixtures.create_mock_agent_code(agent_path)
        
        controller = DGMController(self.config, str(self.test_path))
        
        # Should handle failure gracefully
        await controller.run_generation(generation=0)
        
        # Original agent should still exist
        self.assertTrue(agent_path.exists())
    
    @patch('dgm.dgm_controller.BenchmarkRunner.run_agent_benchmark')
    async def test_run_multiple_generations(self, mock_benchmark):
        """Test running multiple generations."""
        # Mock improving benchmark scores
        scores = [0.3, 0.5, 0.7, 0.8, 0.9]
        mock_benchmark.side_effect = [
            {"agent_id": f"agent_{i}", "score": scores[min(i, len(scores)-1)]}
            for i in range(10)
        ]
        
        # Create initial agents
        for i in range(3):
            agent_path = self.test_path / "agents" / f"agent_{i}"
            TestFixtures.create_mock_agent_code(agent_path)
        
        controller = DGMController(self.config, str(self.test_path))
        
        # Mock self-modification to always succeed
        with patch.object(controller, 'evolve_agent') as mock_evolve:
            mock_evolve.side_effect = [
                f"agent_{i+3}" for i in range(10)
            ]
            
            # Run multiple generations
            results = await controller.run(num_generations=3)
            
            # Should have results for each generation
            self.assertEqual(len(results), 3)
            
            # Scores should improve over generations
            for i in range(1, len(results)):
                prev_avg = sum(r["score"] for r in results[i-1]) / len(results[i-1])
                curr_avg = sum(r["score"] for r in results[i]) / len(results[i])
                self.assertGreaterEqual(curr_avg, prev_avg)
    
    def test_config_validation(self):
        """Test configuration validation."""
        # Missing required fields
        invalid_config = {"dgm": {}}
        
        with self.assertRaises(ValueError):
            controller = DGMController(invalid_config, str(self.test_path))
        
        # Invalid values
        invalid_config = {
            "dgm": {
                "max_generations": -1,  # Invalid
                "archive_size": 20,
                "benchmarks": []
            }
        }
        
        with self.assertRaises(ValueError):
            controller = DGMController(invalid_config, str(self.test_path))
    
    async def test_logging_functionality(self):
        """Test logging functionality."""
        controller = DGMController(self.config, str(self.test_path))
        
        # Log some messages
        controller.logger.info("Test info message")
        controller.logger.error("Test error message")
        
        # Check log file exists
        log_file = Path(self.config["logging"]["file"])
        self.assertTrue(log_file.exists())
        
        # Check log contents
        log_contents = log_file.read_text()
        self.assertIn("Test info message", log_contents)
        self.assertIn("Test error message", log_contents)
    
    async def test_generation_limit(self):
        """Test max generations limit is respected."""
        self.config["dgm"]["max_generations"] = 2
        
        controller = DGMController(self.config, str(self.test_path))
        
        # Create initial agent
        agent_path = self.test_path / "agents" / "agent_0"
        TestFixtures.create_mock_agent_code(agent_path)
        
        with patch.object(controller, 'run_generation') as mock_run_gen:
            mock_run_gen.return_value = [{"agent_id": "agent_0", "score": 0.5}]
            
            # Run with more generations than max
            results = await controller.run(num_generations=5)
            
            # Should only run max_generations times
            self.assertEqual(mock_run_gen.call_count, 2)
            self.assertEqual(len(results), 2)
    
    async def test_checkpoint_saving(self):
        """Test checkpoint saving functionality."""
        controller = DGMController(self.config, str(self.test_path))
        
        # Create some agents
        for i in range(3):
            agent_path = self.test_path / "agents" / f"agent_{i}"
            TestFixtures.create_mock_agent_code(agent_path)
            
            # Add to archive
            result = TestFixtures.create_benchmark_results(
                agent_id=f"agent_{i}",
                score=i * 0.3
            )
            controller.archive.add_agent(f"agent_{i}", result)
        
        # Save checkpoint
        checkpoint_path = self.test_path / "checkpoint.json"
        controller.save_checkpoint(str(checkpoint_path), generation=5)
        
        # Verify checkpoint exists
        self.assertTrue(checkpoint_path.exists())
        
        # Load checkpoint
        with open(checkpoint_path) as f:
            checkpoint = json.load(f)
        
        self.assertEqual(checkpoint["generation"], 5)
        self.assertEqual(len(checkpoint["archive"]), 3)
        self.assertIn("timestamp", checkpoint)
    
    async def test_resume_from_checkpoint(self):
        """Test resuming from checkpoint."""
        # Create checkpoint
        checkpoint = {
            "generation": 3,
            "archive": [
                {
                    "agent_id": "agent_0",
                    "performance": {"score": 0.5},
                    "metadata": {}
                }
            ],
            "timestamp": datetime.now().isoformat()
        }
        
        checkpoint_path = self.test_path / "checkpoint.json"
        with open(checkpoint_path, 'w') as f:
            json.dump(checkpoint, f)
        
        controller = DGMController(self.config, str(self.test_path))
        
        # Load checkpoint
        start_gen = controller.load_checkpoint(str(checkpoint_path))
        
        self.assertEqual(start_gen, 3)
        self.assertEqual(len(controller.archive.agents), 1)
        self.assertEqual(controller.archive.agents[0]["agent_id"], "agent_0")


if __name__ == "__main__":
    # Run async tests
    unittest.main()