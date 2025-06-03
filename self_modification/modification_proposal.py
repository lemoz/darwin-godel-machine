"""
Modification proposal module for generating agent improvement proposals.

This module provides functionality to generate proposals for modifying the agent
code based on performance diagnosis results.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
import uuid
import asyncio


@dataclass
class CodeChange:
    """Represents a specific code change to be made."""
    file_path: str
    change_type: str  # 'add', 'modify', 'delete'
    description: str
    priority: int
    location: Optional[str] = None  # e.g., 'imports', 'class_methods', etc.
    old_code: Optional[str] = None
    new_code: Optional[str] = None
    line_number: Optional[int] = None
    
    def __str__(self) -> str:
        return f"{self.change_type.upper()}: {self.description} (Priority: {self.priority})"


@dataclass
class ModificationProposal:
    """Proposal for modifying agent code to improve performance."""
    proposal_id: str
    diagnosis_summary: str
    code_changes: List[CodeChange] = field(default_factory=list)
    implementation_steps: List[str] = field(default_factory=list)
    expected_improvements: List[str] = field(default_factory=list)
    risk_assessment: Optional[str] = None
    estimated_complexity: Optional[str] = None  # 'low', 'medium', 'high'
    
    def __str__(self) -> str:
        return f"Proposal {self.proposal_id}: {len(self.code_changes)} changes"


class ModificationProposer:
    """
    Generates modification proposals based on performance diagnosis.
    
    This class analyzes diagnosis reports and creates concrete proposals
    for code modifications to improve agent performance.
    """
    
    def __init__(self):
        """Initialize the modification proposer."""
        self.max_changes_per_proposal = 5
        self.improvement_strategies = {
            'tool_integration': self._propose_tool_integration,
            'error_handling': self._propose_error_handling,
            'performance_optimization': self._propose_performance_optimization,
            'code_structure': self._propose_code_structure_improvements
        }
    
    async def generate_proposal(
        self,
        diagnosis: 'DiagnosisReport',
        agent_path: str,
        target_improvements: Optional[List[str]] = None
    ) -> ModificationProposal:
        """
        Generate a modification proposal based on diagnosis.
        
        Args:
            diagnosis: Performance diagnosis report
            agent_path: Path to agent code
            target_improvements: Specific improvements to target
            
        Returns:
            ModificationProposal: Concrete proposal for modifications
        """
        proposal = ModificationProposal(
            proposal_id=str(uuid.uuid4())[:8],
            diagnosis_summary=self._summarize_diagnosis(diagnosis)
        )
        
        # Determine which improvements to prioritize
        priorities = self._prioritize_improvements(diagnosis, target_improvements)
        
        # Generate code changes for each priority area
        for priority_num, improvement_type in enumerate(priorities[:self.max_changes_per_proposal], 1):
            if improvement_type in self.improvement_strategies:
                changes = await self._generate_code_changes(
                    improvement_type,
                    diagnosis,
                    agent_path,
                    priority_num
                )
                proposal.code_changes.extend(changes)
        
        # Generate implementation steps
        proposal.implementation_steps = self._generate_implementation_steps(proposal)
        
        # Estimate improvements
        proposal.expected_improvements = self._estimate_improvements(proposal, diagnosis)
        
        # Assess risk and complexity
        proposal.risk_assessment = self._assess_risk(proposal)
        proposal.estimated_complexity = self._estimate_complexity(proposal)
        
        return proposal
    
    def _summarize_diagnosis(self, diagnosis: 'DiagnosisReport') -> str:
        """Create a summary of the diagnosis."""
        issues = []
        if diagnosis.tool_usage_issues:
            issues.append(f"{len(diagnosis.tool_usage_issues)} tool usage issues")
        if diagnosis.error_handling_issues:
            issues.append(f"{len(diagnosis.error_handling_issues)} error handling issues")
        if diagnosis.timeout_patterns:
            issues.append(f"{len(diagnosis.timeout_patterns)} timeout patterns")
        
        return f"Performance score: {diagnosis.overall_score:.2f}. Issues: {', '.join(issues)}"
    
    def _prioritize_improvements(
        self,
        diagnosis: 'DiagnosisReport',
        target_improvements: Optional[List[str]] = None
    ) -> List[str]:
        """
        Prioritize which improvements to implement.
        
        Args:
            diagnosis: Performance diagnosis
            target_improvements: Specific requested improvements
            
        Returns:
            List of improvement types in priority order
        """
        priorities = []
        
        # Add targeted improvements first
        if target_improvements:
            priorities.extend(target_improvements)
        
        # Add critical improvements based on diagnosis
        if diagnosis.overall_score <= 0.5:  # Include score of exactly 0.5
            if diagnosis.tool_usage_issues:
                priorities.append('tool_integration')
            if diagnosis.error_handling_issues:
                priorities.append('error_handling')
        
        # Add performance improvements if timeouts detected
        if diagnosis.timeout_patterns:
            priorities.append('performance_optimization')
        
        # Add code structure improvements
        if diagnosis.code_structure_issues:
            priorities.append('code_structure')
        
        # Remove duplicates while preserving order
        seen = set()
        unique_priorities = []
        for item in priorities:
            if item not in seen:
                seen.add(item)
                unique_priorities.append(item)
        
        return unique_priorities[:4]  # Limit to top 4 priorities
    
    async def _generate_code_changes(
        self,
        improvement_type: str,
        diagnosis: 'DiagnosisReport',
        agent_path: str,
        priority: int
    ) -> List[CodeChange]:
        """
        Generate specific code changes for an improvement type.
        
        Args:
            improvement_type: Type of improvement
            diagnosis: Performance diagnosis
            agent_path: Path to agent code
            priority: Priority level for changes
            
        Returns:
            List of code changes
        """
        strategy_func = self.improvement_strategies.get(improvement_type)
        if strategy_func:
            return await strategy_func(diagnosis, agent_path, priority)
        return []
    
    async def _propose_tool_integration(
        self,
        diagnosis: 'DiagnosisReport',
        agent_path: str,
        priority: int
    ) -> List[CodeChange]:
        """Propose changes for tool integration."""
        changes = []
        
        # Add tool imports
        changes.append(CodeChange(
            file_path='agent/agent.py',
            change_type='add',
            location='imports',
            new_code='from tools import ToolRegistry, BashTool, EditTool',
            description='Add tool imports',
            priority=priority
        ))
        
        # Add tool initialization
        changes.append(CodeChange(
            file_path='agent/agent.py',
            change_type='add',
            location='__init__',
            new_code='''        # Initialize tools
        self.tool_registry = ToolRegistry()
        self.tool_registry.register_tool(BashTool())
        self.tool_registry.register_tool(EditTool())''',
            description='Initialize tool registry in agent',
            priority=priority
        ))
        
        return changes
    
    async def _propose_error_handling(
        self,
        diagnosis: 'DiagnosisReport',
        agent_path: str,
        priority: int
    ) -> List[CodeChange]:
        """Propose changes for error handling."""
        changes = []
        
        # Add error handling to execute_task
        changes.append(CodeChange(
            file_path='agent/agent.py',
            change_type='modify',
            location='execute_task',
            description='Add comprehensive error handling to task execution',
            priority=priority
        ))
        
        return changes
    
    async def _propose_performance_optimization(
        self,
        diagnosis: 'DiagnosisReport',
        agent_path: str,
        priority: int
    ) -> List[CodeChange]:
        """Propose changes for performance optimization."""
        changes = []
        
        # Add async support
        changes.append(CodeChange(
            file_path='agent/agent.py',
            change_type='modify',
            description='Convert methods to async for better performance',
            priority=priority
        ))
        
        return changes
    
    async def _propose_code_structure_improvements(
        self,
        diagnosis: 'DiagnosisReport',
        agent_path: str,
        priority: int
    ) -> List[CodeChange]:
        """Propose code structure improvements."""
        changes = []
        
        # Implement empty methods
        for issue in diagnosis.code_structure_issues:
            if 'empty' in issue.lower():
                changes.append(CodeChange(
                    file_path='agent/agent.py',
                    change_type='modify',
                    description=f'Implement {issue}',
                    priority=priority
                ))
        
        return changes
    
    def _generate_implementation_steps(self, proposal: ModificationProposal) -> List[str]:
        """Generate step-by-step implementation instructions."""
        steps = []
        
        # Group changes by file
        changes_by_file = {}
        for change in proposal.code_changes:
            if change.file_path not in changes_by_file:
                changes_by_file[change.file_path] = []
            changes_by_file[change.file_path].append(change)
        
        # Generate steps for each file
        for file_path, changes in changes_by_file.items():
            steps.append(f"Modify {file_path}:")
            for change in sorted(changes, key=lambda x: x.priority):
                steps.append(f"  - {change.description}")
        
        steps.append("Run tests to verify changes")
        steps.append("Validate improvements with benchmarks")
        
        return steps
    
    def _estimate_improvements(
        self,
        proposal: ModificationProposal,
        diagnosis: 'DiagnosisReport'
    ) -> List[str]:
        """Estimate expected improvements from the proposal."""
        improvements = []
        
        # Check for tool integration changes
        if any('tool' in change.description.lower() for change in proposal.code_changes):
            improvements.append("Enhanced task execution capability through tool usage")
            improvements.append(f"Expected score improvement: +{0.2:.1f} points")
        
        # Check for error handling
        if any('error' in change.description.lower() for change in proposal.code_changes):
            improvements.append("Improved reliability and error recovery")
            improvements.append("Reduced failure rate in benchmarks")
        
        # Check for performance optimizations
        if any('async' in change.description.lower() or 'performance' in change.description.lower() 
               for change in proposal.code_changes):
            improvements.append("Faster execution times")
            improvements.append("Reduced timeout occurrences")
        
        return improvements
    
    def _assess_risk(self, proposal: ModificationProposal) -> str:
        """Assess the risk level of the proposed changes."""
        # Count high-impact changes
        high_impact = sum(1 for change in proposal.code_changes 
                         if change.change_type in ['delete', 'modify'])
        
        if high_impact > 3:
            return "High risk - multiple core modifications"
        elif high_impact > 1:
            return "Medium risk - some core modifications"
        else:
            return "Low risk - mostly additions"
    
    def _estimate_complexity(self, proposal: ModificationProposal) -> str:
        """Estimate implementation complexity."""
        total_changes = len(proposal.code_changes)
        modify_changes = sum(1 for c in proposal.code_changes if c.change_type == 'modify')
        
        if total_changes > 4 or modify_changes > 2:
            return "high"
        elif total_changes > 2 or modify_changes > 0:
            return "medium"
        else:
            return "low"