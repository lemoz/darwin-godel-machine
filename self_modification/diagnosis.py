"""
Performance Diagnosis Module for DGM.

Analyzes agent performance on benchmarks to identify areas for improvement.
"""

import json
import ast
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class DiagnosisReport:
    """Report containing performance analysis and identified issues."""
    
    overall_score: float
    benchmark_scores: Dict[str, float]
    
    # Identified issues
    code_structure_issues: List[str] = field(default_factory=list)
    tool_usage_issues: List[str] = field(default_factory=list)
    prompt_engineering_issues: List[str] = field(default_factory=list)
    error_handling_issues: List[str] = field(default_factory=list)
    
    # Performance patterns
    failed_test_patterns: List[str] = field(default_factory=list)
    timeout_patterns: List[str] = field(default_factory=list)
    
    # Improvement opportunities
    improvement_suggestions: List[str] = field(default_factory=list)
    high_priority_areas: List[str] = field(default_factory=list)
    
    # Code analysis
    complexity_metrics: Dict[str, Any] = field(default_factory=dict)
    unused_features: List[str] = field(default_factory=list)


class PerformanceDiagnoser:
    """Diagnoses agent performance and identifies improvement areas."""
    
    def __init__(self):
        """Initialize the performance diagnoser."""
        self.code_patterns = {
            'error_handling': [
                r'try:.*except:.*pass',  # Empty exception handlers
                r'except\s+Exception\s*:',  # Overly broad exceptions
                r'except\s*:',  # Bare except
            ],
            'tool_usage': [
                r'tool_registry\.register_tool',  # Tool registration
                r'execute_tool\(',  # Tool execution
                r'\.run\(',  # Tool run calls
            ],
            'prompt_engineering': [
                r'system_prompt',  # System prompt definition
                r'format_prompt',  # Prompt formatting
                r'get_completion',  # FM calls
            ],
            'code_organization': [
                r'class\s+\w+:',  # Class definitions
                r'def\s+\w+\(',  # Function definitions
                r'import\s+',  # Import statements
            ]
        }
    
    async def diagnose_performance(
        self,
        agent_path: str,
        benchmark_results: Dict[str, Any],
        verbose: bool = False
    ) -> DiagnosisReport:
        """
        Diagnose agent performance based on benchmark results and code analysis.
        
        Args:
            agent_path: Path to agent source code
            benchmark_results: Results from benchmark evaluation
            verbose: Whether to log detailed analysis
            
        Returns:
            Comprehensive diagnosis report
        """
        # Initialize report
        report = DiagnosisReport(
            overall_score=benchmark_results.get('overall_score', 0.0),
            benchmark_scores=benchmark_results.get('benchmark_scores', {})
        )
        
        # Analyze benchmark failures
        self._analyze_benchmark_failures(benchmark_results, report)
        
        # Analyze code structure
        await self._analyze_code_structure(agent_path, report)
        
        # Analyze tool usage patterns
        self._analyze_tool_usage(agent_path, report)
        
        # Analyze prompt engineering
        self._analyze_prompt_engineering(agent_path, report)
        
        # Calculate complexity metrics
        self._calculate_complexity_metrics(agent_path, report)
        
        # Generate improvement suggestions
        self._generate_improvement_suggestions(report)
        
        if verbose:
            self._log_diagnosis_summary(report)
        
        return report
    
    def _analyze_benchmark_failures(
        self,
        benchmark_results: Dict[str, Any],
        report: DiagnosisReport
    ):
        """Analyze patterns in benchmark failures."""
        for benchmark_name, results in benchmark_results.get('detailed_results', {}).items():
            score = report.benchmark_scores.get(benchmark_name, 0.0)
            
            if score < 0.5:  # Poor performance
                # Analyze failure patterns
                failed_tests = [
                    test for test in results.get('test_results', [])
                    if not test.get('passed', False)
                ]
                
                # Look for timeout patterns
                timeout_tests = [
                    test for test in failed_tests
                    if 'timeout' in test.get('error', '').lower()
                ]
                
                if len(timeout_tests) > len(failed_tests) * 0.3:
                    report.timeout_patterns.append(
                        f"{benchmark_name}: {len(timeout_tests)}/{len(failed_tests)} tests timed out"
                    )
                
                # Look for common error patterns
                error_types = {}
                for test in failed_tests:
                    error = test.get('error', 'Unknown error')
                    error_type = self._classify_error(error)
                    error_types[error_type] = error_types.get(error_type, 0) + 1
                
                for error_type, count in error_types.items():
                    if count > 1:
                        report.failed_test_patterns.append(
                            f"{benchmark_name}: {error_type} ({count} occurrences)"
                        )
    
    async def _analyze_code_structure(
        self,
        agent_path: str,
        report: DiagnosisReport
    ):
        """Analyze agent code structure for issues."""
        agent_file = Path(agent_path) / "agent" / "agent.py"
        
        if not agent_file.exists():
            report.code_structure_issues.append("Agent main file not found")
            return
        
        try:
            with open(agent_file, 'r') as f:
                code = f.read()
            
            # Parse AST
            tree = ast.parse(code)
            
            # Check for missing or poorly structured methods
            agent_class = None
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == 'Agent':
                    agent_class = node
                    break
            
            if not agent_class:
                report.code_structure_issues.append("Agent class not found")
                return
            
            # Check method implementations
            method_names = set()
            empty_methods = []
            
            for node in agent_class.body:
                if isinstance(node, ast.FunctionDef):
                    method_names.add(node.name)
                    
                    # Check for empty or trivial implementations
                    if len(node.body) == 1:
                        if isinstance(node.body[0], ast.Pass):
                            empty_methods.append(node.name)
                        elif isinstance(node.body[0], ast.Return) and node.body[0].value is None:
                            empty_methods.append(node.name)
            
            if empty_methods:
                report.code_structure_issues.append(
                    f"Empty method implementations: {', '.join(empty_methods)}"
                )
            
            # Check for missing error handling
            has_try_except = any(
                isinstance(node, ast.Try) 
                for node in ast.walk(tree)
            )
            
            if not has_try_except:
                report.error_handling_issues.append(
                    "No exception handling found in agent code"
                )
            
        except Exception as e:
            report.code_structure_issues.append(f"Error analyzing code: {str(e)}")
    
    def _analyze_tool_usage(
        self,
        agent_path: str,
        report: DiagnosisReport
    ):
        """Analyze tool usage patterns in agent code."""
        agent_file = Path(agent_path) / "agent" / "agent.py"
        
        if not agent_file.exists():
            return
        
        try:
            with open(agent_file, 'r') as f:
                code = f.read()
            
            # Check tool registration
            tool_registrations = re.findall(
                self.code_patterns['tool_usage'][0], 
                code
            )
            
            if len(tool_registrations) < 2:
                report.tool_usage_issues.append(
                    "Limited tool registration found - agent may lack necessary tools"
                )
            
            # Check tool execution patterns
            tool_executions = re.findall(
                self.code_patterns['tool_usage'][1], 
                code
            )
            
            if len(tool_executions) == 0:
                report.tool_usage_issues.append(
                    "No tool execution calls found - agent may not be using tools effectively"
                )
            
            # Check for bash/edit tool usage (critical for code editing)
            has_bash_tool = 'BashTool' in code or 'bash_tool' in code
            has_edit_tool = 'EditTool' in code or 'edit_tool' in code
            
            if not has_bash_tool and not has_edit_tool:
                report.tool_usage_issues.append(
                    "No code editing tools found - agent cannot modify code"
                )
            
        except Exception as e:
            logger.error(f"Error analyzing tool usage: {e}")
    
    def _analyze_prompt_engineering(
        self,
        agent_path: str,
        report: DiagnosisReport
    ):
        """Analyze prompt engineering patterns."""
        agent_file = Path(agent_path) / "agent" / "agent.py"
        
        if not agent_file.exists():
            return
        
        try:
            with open(agent_file, 'r') as f:
                code = f.read()
            
            # Check for system prompts
            has_system_prompt = bool(re.search(
                self.code_patterns['prompt_engineering'][0], 
                code
            ))
            
            if not has_system_prompt:
                report.prompt_engineering_issues.append(
                    "No system prompt configuration found"
                )
            
            # Check prompt formatting
            prompt_formats = re.findall(
                self.code_patterns['prompt_engineering'][1], 
                code
            )
            
            if len(prompt_formats) == 0:
                report.prompt_engineering_issues.append(
                    "No prompt formatting logic found"
                )
            
            # Check FM completion patterns
            fm_calls = re.findall(
                self.code_patterns['prompt_engineering'][2], 
                code
            )
            
            if len(fm_calls) == 0:
                report.prompt_engineering_issues.append(
                    "No FM completion calls found"
                )
            
        except Exception as e:
            logger.error(f"Error analyzing prompt engineering: {e}")
    
    def _calculate_complexity_metrics(
        self,
        agent_path: str,
        report: DiagnosisReport
    ):
        """Calculate code complexity metrics."""
        try:
            # Count total lines of code
            total_lines = 0
            total_functions = 0
            total_classes = 0
            
            for py_file in Path(agent_path).rglob("*.py"):
                with open(py_file, 'r') as f:
                    lines = f.readlines()
                    total_lines += len(lines)
                
                # Simple AST analysis
                with open(py_file, 'r') as f:
                    try:
                        tree = ast.parse(f.read())
                        for node in ast.walk(tree):
                            if isinstance(node, ast.FunctionDef):
                                total_functions += 1
                            elif isinstance(node, ast.ClassDef):
                                total_classes += 1
                    except:
                        pass
            
            report.complexity_metrics = {
                'total_lines': total_lines,
                'total_functions': total_functions,
                'total_classes': total_classes,
                'avg_lines_per_function': total_lines / max(1, total_functions)
            }
            
        except Exception as e:
            logger.error(f"Error calculating complexity metrics: {e}")
    
    def _generate_improvement_suggestions(self, report: DiagnosisReport):
        """Generate specific improvement suggestions based on diagnosis."""
        # Priority 1: Critical functionality issues
        if report.tool_usage_issues:
            report.high_priority_areas.append("Tool Integration")
            report.improvement_suggestions.append(
                "Enhance tool usage: Ensure bash/edit tools are properly integrated for code modification capabilities"
            )
        
        # Priority 2: Error handling
        if report.error_handling_issues:
            report.high_priority_areas.append("Error Handling")
            report.improvement_suggestions.append(
                "Implement comprehensive error handling with specific exception types and recovery strategies"
            )
        
        # Priority 3: Performance issues
        if report.timeout_patterns:
            report.high_priority_areas.append("Performance Optimization")
            report.improvement_suggestions.append(
                "Optimize execution speed: Add timeouts, implement caching, or streamline algorithms"
            )
        
        # Priority 4: Prompt engineering
        if report.prompt_engineering_issues:
            report.improvement_suggestions.append(
                "Improve prompt engineering: Add task-specific prompts, better context formatting"
            )
        
        # Priority 5: Code structure
        if report.code_structure_issues:
            report.improvement_suggestions.append(
                "Refactor code structure: Implement missing methods, improve organization"
            )
        
        # Benchmark-specific suggestions
        for benchmark, score in report.benchmark_scores.items():
            if score < 0.3:
                report.improvement_suggestions.append(
                    f"Focus on {benchmark}: Analyze failure patterns and implement targeted improvements"
                )
    
    def _classify_error(self, error: str) -> str:
        """Classify error type from error message."""
        error_lower = error.lower()
        
        if 'timeout' in error_lower:
            return "Timeout"
        elif 'syntax' in error_lower:
            return "Syntax Error"
        elif 'import' in error_lower:
            return "Import Error"
        elif 'attribute' in error_lower:
            return "Attribute Error"
        elif 'type' in error_lower:
            return "Type Error"
        elif 'value' in error_lower:
            return "Value Error"
        elif 'index' in error_lower:
            return "Index Error"
        else:
            return "Other Error"
    
    def _log_diagnosis_summary(self, report: DiagnosisReport):
        """Log a summary of the diagnosis."""
        logger.info("\n=== Performance Diagnosis Summary ===")
        logger.info(f"Overall Score: {report.overall_score:.3f}")
        logger.info(f"High Priority Areas: {', '.join(report.high_priority_areas)}")
        
        if report.improvement_suggestions:
            logger.info("\nTop Suggestions:")
            for i, suggestion in enumerate(report.improvement_suggestions[:3]):
                logger.info(f"  {i+1}. {suggestion}")