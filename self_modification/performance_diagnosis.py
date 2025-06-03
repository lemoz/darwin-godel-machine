"""
Performance diagnosis module for analyzing agent performance.

This module provides functionality to diagnose performance issues in the agent's
execution, analyze code structure, and generate improvement suggestions.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
import ast
import asyncio


@dataclass
class DiagnosisReport:
    """Report containing performance diagnosis results."""
    overall_score: float
    benchmark_scores: Dict[str, float]
    improvement_suggestions: List[str] = field(default_factory=list)
    code_structure_issues: List[str] = field(default_factory=list)
    tool_usage_issues: List[str] = field(default_factory=list)
    error_handling_issues: List[str] = field(default_factory=list)
    prompt_engineering_issues: List[str] = field(default_factory=list)
    timeout_patterns: List[str] = field(default_factory=list)
    high_priority_areas: List[str] = field(default_factory=list)
    detailed_results: Optional[Dict[str, Any]] = None


class PerformanceDiagnosis:
    """
    Analyzes agent performance and identifies areas for improvement.
    
    This class provides methods to diagnose performance issues by analyzing
    benchmark results, code structure, and execution patterns.
    """
    
    def __init__(self):
        """Initialize the performance diagnoser."""
        self.min_acceptable_score = 0.7
        self.critical_score_threshold = 0.5
    
    async def diagnose_performance(
        self, 
        agent_path: str, 
        benchmark_results: Dict[str, Any]
    ) -> DiagnosisReport:
        """
        Perform comprehensive performance diagnosis.
        
        Args:
            agent_path: Path to the agent code
            benchmark_results: Results from benchmark evaluation
            
        Returns:
            DiagnosisReport: Comprehensive diagnosis report
        """
        report = DiagnosisReport(
            overall_score=benchmark_results.get('overall_score', 0.0),
            benchmark_scores=benchmark_results.get('benchmark_scores', {}),
            detailed_results=benchmark_results.get('detailed_results', {})
        )
        
        # Analyze different aspects
        await self._analyze_code_structure(agent_path, report)
        self._analyze_tool_usage(agent_path, report)
        self._analyze_benchmark_failures(benchmark_results, report)
        self._generate_improvement_suggestions(report)
        
        return report
    
    async def _analyze_code_structure(
        self, 
        agent_path: str, 
        report: DiagnosisReport
    ) -> None:
        """
        Analyze code structure for potential issues.
        
        Args:
            agent_path: Path to agent code
            report: Report to update with findings
        """
        path = Path(agent_path)
        
        # Analyze main agent file
        agent_file = path / "agent" / "agent.py"
        if agent_file.exists():
            content = agent_file.read_text()
            
            # Check for empty methods
            if "pass" in content and content.count("def ") > content.count("pass") - 1:
                report.code_structure_issues.append(
                    "Found empty method implementations"
                )
            
            # Check for proper error handling
            if "try:" not in content:
                report.error_handling_issues.append(
                    "No exception handling found in agent code"
                )
            
            # Check for tool imports
            if "from tools" not in content and "import tools" not in content:
                report.tool_usage_issues.append(
                    "No tool imports found - agent may not be using tools"
                )
            
            # Parse AST to check method complexity
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        # Check for overly simple methods
                        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                            report.code_structure_issues.append(
                                f"Empty method found: {node.name}"
                            )
            except Exception:
                report.code_structure_issues.append(
                    "Failed to parse agent code - possible syntax issues"
                )
    
    def _analyze_tool_usage(self, agent_path: str, report: DiagnosisReport) -> None:
        """
        Analyze tool usage patterns.
        
        Args:
            agent_path: Path to agent code
            report: Report to update with findings
        """
        path = Path(agent_path)
        
        # Check for tool implementations
        tools_dir = path / "agent" / "tools"
        if not tools_dir.exists() or not list(tools_dir.glob("*.py")):
            report.tool_usage_issues.append(
                "No tool implementations found"
            )
            return
        
        # Check tool registrations
        agent_file = path / "agent" / "agent.py"
        if agent_file.exists():
            content = agent_file.read_text()
            if "register_tool" not in content and "ToolRegistry" not in content:
                report.tool_usage_issues.append(
                    "No tool registration found in agent"
                )
    
    def _analyze_benchmark_failures(
        self, 
        benchmark_results: Dict[str, Any], 
        report: DiagnosisReport
    ) -> None:
        """
        Analyze patterns in benchmark failures.
        
        Args:
            benchmark_results: Results from benchmarks
            report: Report to update with findings
        """
        detailed_results = benchmark_results.get('detailed_results', {})
        
        for benchmark_name, results in detailed_results.items():
            if 'test_results' in results:
                timeout_count = 0
                error_types = {}
                
                for test in results['test_results']:
                    if not test.get('passed', True):
                        error = test.get('error', 'Unknown error')
                        if 'Timeout' in error:
                            timeout_count += 1
                        error_types[error] = error_types.get(error, 0) + 1
                
                if timeout_count > len(results['test_results']) * 0.3:
                    report.timeout_patterns.append(
                        f"{benchmark_name}: {timeout_count} timeouts detected"
                    )
                
                for error, count in error_types.items():
                    if count > 1:
                        report.error_handling_issues.append(
                            f"{benchmark_name}: Repeated error - {error} ({count} times)"
                        )
    
    def _generate_improvement_suggestions(self, report: DiagnosisReport) -> None:
        """
        Generate improvement suggestions based on diagnosis.
        
        Args:
            report: Report to update with suggestions
        """
        # Critical performance issues
        if report.overall_score < self.critical_score_threshold:
            report.improvement_suggestions.append(
                "Critical: Overall performance below 50% - major refactoring needed"
            )
            report.high_priority_areas.append("Core Algorithm Implementation")
        
        # Tool usage issues
        if report.tool_usage_issues:
            report.improvement_suggestions.append(
                "Implement proper tool integration for better task execution"
            )
            report.high_priority_areas.append("Tool Integration")
        
        # Error handling
        if report.error_handling_issues:
            report.improvement_suggestions.append(
                "Add comprehensive error handling and recovery mechanisms"
            )
            report.high_priority_areas.append("Error Handling")
        
        # Timeout issues
        if report.timeout_patterns:
            report.improvement_suggestions.append(
                "Optimize execution time - consider async operations or better algorithms"
            )
            report.high_priority_areas.append("Performance Optimization")
        
        # Code structure
        if report.code_structure_issues:
            report.improvement_suggestions.append(
                "Refactor code structure - implement missing methods and improve organization"
            )
        
        # Benchmark-specific suggestions
        for benchmark, score in report.benchmark_scores.items():
            if score < self.min_acceptable_score:
                report.improvement_suggestions.append(
                    f"Focus on improving {benchmark} performance (current: {score:.2f})"
                )