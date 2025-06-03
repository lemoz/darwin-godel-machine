"""
Unit tests for self-modification components.
"""

import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from self_modification.performance_diagnosis import PerformanceDiagnosis, DiagnosisReport
from self_modification.modification_proposal import ModificationProposer, ModificationProposal, CodeChange
from self_modification.implementation import ImplementationManager
from tests.test_utils import TestFixtures, AsyncTestRunner, cleanup_test_directory


class TestPerformanceDiagnoser(unittest.TestCase):
    """Test cases for PerformanceDiagnoser."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_diagnosis_"))
        self.diagnoser = PerformanceDiagnosis()
        
        # Create test agent
        self.agent_path = self.temp_dir / "test_agent"
        TestFixtures.create_mock_agent_code(self.agent_path)
    
    def tearDown(self):
        """Clean up test fixtures."""
        cleanup_test_directory(self.temp_dir)
    
    def test_diagnose_performance_basic(self):
        """Test basic performance diagnosis."""
        benchmark_results = {
            'overall_score': 0.6,
            'benchmark_scores': {
                'test_benchmark': 0.6,
                'string_manipulation': 0.5
            },
            'detailed_results': {
                'test_benchmark': {
                    'test_results': [
                        {'passed': True, 'error': None},
                        {'passed': False, 'error': 'Timeout'}
                    ]
                }
            }
        }
        
        report = AsyncTestRunner.run(
            self.diagnoser.diagnose_performance(
                str(self.agent_path),
                benchmark_results
            )
        )
        
        self.assertIsInstance(report, DiagnosisReport)
        self.assertEqual(report.overall_score, 0.6)
        self.assertEqual(len(report.benchmark_scores), 2)
        self.assertGreater(len(report.improvement_suggestions), 0)
    
    def test_analyze_code_structure_issues(self):
        """Test detection of code structure issues."""
        # Create agent with empty methods
        agent_file = self.agent_path / "agent" / "agent.py"
        content = agent_file.read_text()
        
        # Add empty method
        content += "\n\ndef empty_method(self):\n    pass\n"
        agent_file.write_text(content)
        
        report = DiagnosisReport(
            overall_score=0.5,
            benchmark_scores={}
        )
        
        AsyncTestRunner.run(
            self.diagnoser._analyze_code_structure(str(self.agent_path), report)
        )
        
        self.assertGreater(len(report.code_structure_issues), 0)
        self.assertTrue(any('empty' in issue.lower() for issue in report.code_structure_issues))
    
    def test_analyze_tool_usage(self):
        """Test analysis of tool usage patterns."""
        report = DiagnosisReport(
            overall_score=0.5,
            benchmark_scores={}
        )
        
        self.diagnoser._analyze_tool_usage(str(self.agent_path), report)
        
        # Mock agent has limited tool usage
        self.assertGreater(len(report.tool_usage_issues), 0)
    
    def test_generate_improvement_suggestions(self):
        """Test generation of improvement suggestions."""
        report = DiagnosisReport(
            overall_score=0.3,
            benchmark_scores={'test': 0.3},
            tool_usage_issues=['No tool execution found'],
            error_handling_issues=['No exception handling found'],
            timeout_patterns=['Many timeouts']
        )
        
        self.diagnoser._generate_improvement_suggestions(report)
        
        self.assertGreater(len(report.improvement_suggestions), 0)
        self.assertGreater(len(report.high_priority_areas), 0)
        self.assertIn('Tool Integration', report.high_priority_areas)
        self.assertIn('Error Handling', report.high_priority_areas)


class TestModificationProposer(unittest.TestCase):
    """Test cases for ModificationProposer."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_proposer_"))
        self.proposer = ModificationProposer()
        
        # Create test agent
        self.agent_path = self.temp_dir / "test_agent"
        TestFixtures.create_mock_agent_code(self.agent_path)
    
    def tearDown(self):
        """Clean up test fixtures."""
        cleanup_test_directory(self.temp_dir)
    
    def test_generate_proposal_basic(self):
        """Test basic proposal generation."""
        diagnosis = DiagnosisReport(
            overall_score=0.5,
            benchmark_scores={'test': 0.5},
            tool_usage_issues=['Limited tool usage'],
            error_handling_issues=['No error handling']
        )
        
        proposal = AsyncTestRunner.run(
            self.proposer.generate_proposal(
                diagnosis,
                str(self.agent_path)
            )
        )
        
        self.assertIsInstance(proposal, ModificationProposal)
        self.assertGreater(len(proposal.code_changes), 0)
        self.assertGreater(len(proposal.implementation_steps), 0)
        self.assertGreater(len(proposal.expected_improvements), 0)
    
    def test_prioritize_improvements(self):
        """Test improvement prioritization."""
        diagnosis = DiagnosisReport(
            overall_score=0.3,
            benchmark_scores={'test': 0.3},
            tool_usage_issues=['Critical issue'],
            error_handling_issues=['Important issue'],
            prompt_engineering_issues=['Minor issue']
        )
        
        priorities = self.proposer._prioritize_improvements(
            diagnosis,
            target_improvements=['custom_improvement']
        )
        
        # Custom improvements should come first
        self.assertEqual(priorities[0], 'custom_improvement')
        # Then critical issues
        self.assertIn('tool_integration', priorities)
        self.assertIn('error_handling', priorities)
        # Limited to top 4
        self.assertLessEqual(len(priorities), 4)
    
    def test_generate_code_changes(self):
        """Test code change generation."""
        changes = AsyncTestRunner.run(
            self.proposer._generate_code_changes(
                'tool_integration',
                DiagnosisReport(0.5, {}),
                str(self.agent_path),
                priority=1
            )
        )
        
        self.assertGreater(len(changes), 0)
        
        # Check that changes have proper structure
        for change in changes:
            self.assertIsInstance(change, CodeChange)
            self.assertEqual(change.priority, 1)
            self.assertIsNotNone(change.description)
            self.assertIn(change.change_type, ['add', 'modify', 'delete'])
    
    def test_estimate_improvements(self):
        """Test improvement estimation."""
        proposal = ModificationProposal(
            proposal_id='test',
            diagnosis_summary='Test diagnosis',
            code_changes=[
                CodeChange(
                    file_path='agent/agent.py',
                    change_type='add',
                    description='Add tool integration',
                    priority=1
                ),
                CodeChange(
                    file_path='agent/agent.py',
                    change_type='modify',
                    description='Improve error handling',
                    priority=2
                )
            ]
        )
        
        diagnosis = DiagnosisReport(
            overall_score=0.5,
            benchmark_scores={'test': 0.5}
        )
        
        improvements = self.proposer._estimate_improvements(proposal, diagnosis)
        
        self.assertGreater(len(improvements), 0)
        self.assertTrue(any('tool' in imp.lower() for imp in improvements))
        self.assertTrue(any('error' in imp.lower() for imp in improvements))


class TestModificationImplementer(unittest.TestCase):
    """Test cases for ModificationImplementer."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_implementer_"))
        self.implementer = ImplementationManager()
        
        # Create test agent
        self.agent_path = self.temp_dir / "test_agent"
        TestFixtures.create_mock_agent_code(self.agent_path)
    
    def tearDown(self):
        """Clean up test fixtures."""
        cleanup_test_directory(self.temp_dir)
    
    def test_implement_proposal_dry_run(self):
        """Test dry run implementation."""
        proposal = ModificationProposal(
            proposal_id='test',
            diagnosis_summary='Test',
            code_changes=[
                CodeChange(
                    file_path='agent/agent.py',
                    change_type='add',
                    location='imports',
                    new_code='import new_module',
                    description='Add import',
                    priority=1
                )
            ]
        )
        
        result = AsyncTestRunner.run(
            self.implementer.implement_proposal(
                proposal,
                str(self.agent_path),
                dry_run=True
            )
        )
        
        self.assertTrue(result['success'])
        self.assertIsNone(result['backup_path'])  # No backup in dry run
        self.assertEqual(len(result['changes_applied']), 1)
    
    def test_implement_proposal_with_backup(self):
        """Test implementation with backup."""
        proposal = ModificationProposal(
            proposal_id='test',
            diagnosis_summary='Test',
            code_changes=[
                CodeChange(
                    file_path='agent/agent.py',
                    change_type='add',
                    location='imports',
                    new_code='# Test comment',
                    description='Add comment',
                    priority=1
                )
            ]
        )
        
        result = AsyncTestRunner.run(
            self.implementer.implement_proposal(
                proposal,
                str(self.agent_path),
                dry_run=False
            )
        )
        
        self.assertTrue(result['success'])
        self.assertIsNotNone(result['backup_path'])
        self.assertTrue(Path(result['backup_path']).exists())
        
        # Verify change was applied
        agent_file = self.agent_path / "agent" / "agent.py"
        content = agent_file.read_text()
        self.assertIn('# Test comment', content)
    
    def test_apply_modification(self):
        """Test applying a modification change."""
        agent_file = self.agent_path / "agent" / "agent.py"
        original_content = agent_file.read_text()
        
        change = CodeChange(
            file_path='agent/agent.py',
            change_type='modify',
            old_code='I am a test agent',
            new_code='I am a modified test agent',
            description='Modify system prompt',
            priority=1
        )
        
        success = AsyncTestRunner.run(
            self.implementer._apply_code_change(
                change,
                str(self.agent_path),
                dry_run=False
            )
        )
        
        self.assertTrue(success)
        
        # Verify modification
        content = agent_file.read_text()
        self.assertIn('modified test agent', content)
        self.assertNotIn('I am a test agent', content)
    
    def test_rollback_changes(self):
        """Test rollback functionality."""
        # Create backup
        self.implementer.backup_dir = self.implementer._create_backup(str(self.agent_path))
        
        # Make a change
        agent_file = self.agent_path / "agent" / "agent.py"
        agent_file.write_text("# Corrupted file")
        
        # Rollback
        self.implementer._rollback_changes(str(self.agent_path))
        
        # Verify rollback
        content = agent_file.read_text()
        self.assertNotEqual(content, "# Corrupted file")
        self.assertIn('class Agent', content)  # Original content restored
    
    def test_verify_modifications(self):
        """Test modification verification."""
        # Valid modifications
        result = AsyncTestRunner.run(
            self.implementer._verify_modifications(str(self.agent_path))
        )
        
        self.assertTrue(result['valid'])
        self.assertEqual(len(result['errors']), 0)
        
        # Introduce syntax error
        agent_file = self.agent_path / "agent" / "agent.py"
        content = agent_file.read_text()
        content += "\n\nthis is invalid syntax"
        agent_file.write_text(content)
        
        result = AsyncTestRunner.run(
            self.implementer._verify_modifications(str(self.agent_path))
        )
        
        self.assertFalse(result['valid'])
        self.assertGreater(len(result['errors']), 0)


if __name__ == '__main__':
    unittest.main()