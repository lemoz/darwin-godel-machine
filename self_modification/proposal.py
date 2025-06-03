"""
Modification Proposal Module for DGM.

Generates specific code modification proposals based on performance diagnosis.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import logging
import json

from .diagnosis import DiagnosisReport

logger = logging.getLogger(__name__)


@dataclass
class CodeChange:
    """Represents a specific code change to be made."""
    
    file_path: str
    change_type: str  # 'add', 'modify', 'delete'
    location: Optional[str] = None  # method/class name or line number
    old_code: Optional[str] = None
    new_code: Optional[str] = None
    description: str = ""
    priority: int = 1  # 1 = highest priority


@dataclass
class ModificationProposal:
    """Complete proposal for agent modifications."""
    
    proposal_id: str
    diagnosis_summary: str
    
    # Proposed changes
    code_changes: List[CodeChange] = field(default_factory=list)
    
    # New features to add
    new_features: List[Dict[str, Any]] = field(default_factory=list)
    
    # Refactoring suggestions
    refactoring_tasks: List[str] = field(default_factory=list)
    
    # Configuration changes
    config_updates: Dict[str, Any] = field(default_factory=dict)
    
    # Expected improvements
    expected_improvements: List[str] = field(default_factory=list)
    risk_assessment: List[str] = field(default_factory=list)
    
    # Implementation order
    implementation_steps: List[str] = field(default_factory=list)


class ModificationProposer:
    """Generates modification proposals based on diagnosis."""
    
    def __init__(self):
        """Initialize the modification proposer."""
        self.improvement_templates = {
            'tool_integration': {
                'description': 'Enhance tool integration for better code editing',
                'changes': [
                    {
                        'type': 'add_import',
                        'code': 'from agent.tools import EditTool'
                    },
                    {
                        'type': 'add_tool_registration',
                        'code': '''
        # Register edit tool for code modifications
        self.tool_registry.register_tool(
            'edit',
            EditTool(),
            description="Edit files with precise modifications"
        )'''
                    }
                ]
            },
            'error_handling': {
                'description': 'Improve error handling and recovery',
                'changes': [
                    {
                        'type': 'wrap_method',
                        'template': '''
    try:
        {original_code}
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return self._handle_file_error(e)
    except SyntaxError as e:
        logger.error(f"Syntax error in generated code: {e}")
        return self._handle_syntax_error(e)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return self._handle_general_error(e)'''
                    }
                ]
            },
            'prompt_optimization': {
                'description': 'Optimize prompts for better FM responses',
                'changes': [
                    {
                        'type': 'modify_system_prompt',
                        'code': '''
        self.system_prompt = """You are an expert coding assistant specializing in {task_type}.
You have access to the following tools: {available_tools}

When solving problems:
1. Analyze the requirements carefully
2. Plan your approach before coding
3. Use tools effectively to implement solutions
4. Test your code when possible
5. Handle errors gracefully

Your responses should be clear, concise, and focused on solving the task efficiently."""'''
                    }
                ]
            },
            'performance_optimization': {
                'description': 'Optimize for faster execution',
                'changes': [
                    {
                        'type': 'add_caching',
                        'code': '''
        # Add caching for FM responses
        self._response_cache = {}
        
    def _get_cached_response(self, prompt: str) -> Optional[str]:
        cache_key = hash(prompt)
        if cache_key in self._response_cache:
            return self._response_cache[cache_key]
        return None'''
                    },
                    {
                        'type': 'add_timeout',
                        'code': '''
        # Add timeout handling
        import asyncio
        
        try:
            result = await asyncio.wait_for(
                self._execute_with_tools(prompt),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            logger.warning("Execution timed out, trying simpler approach")
            result = await self._execute_simple(prompt)'''
                    }
                ]
            }
        }
    
    async def generate_proposal(
        self,
        diagnosis: DiagnosisReport,
        agent_path: str,
        target_improvements: Optional[List[str]] = None
    ) -> ModificationProposal:
        """
        Generate a modification proposal based on diagnosis.
        
        Args:
            diagnosis: Performance diagnosis report
            agent_path: Path to agent source code
            target_improvements: Specific improvements to target
            
        Returns:
            Detailed modification proposal
        """
        proposal = ModificationProposal(
            proposal_id=f"proposal_{Path(agent_path).name}",
            diagnosis_summary=self._summarize_diagnosis(diagnosis)
        )
        
        # Prioritize improvements based on diagnosis
        priorities = self._prioritize_improvements(diagnosis, target_improvements)
        
        # Generate specific code changes for each priority
        for priority, improvement_type in enumerate(priorities, 1):
            changes = await self._generate_code_changes(
                improvement_type,
                diagnosis,
                agent_path,
                priority
            )
            proposal.code_changes.extend(changes)
        
        # Add new features if needed
        if diagnosis.overall_score < 0.3:
            proposal.new_features.extend(self._suggest_new_features(diagnosis))
        
        # Add refactoring suggestions
        if diagnosis.complexity_metrics.get('avg_lines_per_function', 0) > 50:
            proposal.refactoring_tasks.append(
                "Break down large functions into smaller, focused methods"
            )
        
        # Generate implementation steps
        proposal.implementation_steps = self._generate_implementation_steps(proposal)
        
        # Add expected improvements and risks
        proposal.expected_improvements = self._estimate_improvements(proposal, diagnosis)
        proposal.risk_assessment = self._assess_risks(proposal)
        
        return proposal
    
    def _summarize_diagnosis(self, diagnosis: DiagnosisReport) -> str:
        """Create a summary of the diagnosis."""
        issues = []
        
        if diagnosis.code_structure_issues:
            issues.append(f"Code structure: {len(diagnosis.code_structure_issues)} issues")
        if diagnosis.tool_usage_issues:
            issues.append(f"Tool usage: {len(diagnosis.tool_usage_issues)} issues")
        if diagnosis.error_handling_issues:
            issues.append(f"Error handling: {len(diagnosis.error_handling_issues)} issues")
        
        return f"Overall score: {diagnosis.overall_score:.2f}. Issues: {', '.join(issues)}"
    
    def _prioritize_improvements(
        self,
        diagnosis: DiagnosisReport,
        target_improvements: Optional[List[str]] = None
    ) -> List[str]:
        """Prioritize improvements based on diagnosis."""
        priorities = []
        
        # User-specified targets first
        if target_improvements:
            priorities.extend(target_improvements)
        
        # Then critical issues
        if diagnosis.tool_usage_issues:
            priorities.append('tool_integration')
        
        if diagnosis.error_handling_issues:
            priorities.append('error_handling')
        
        if diagnosis.timeout_patterns:
            priorities.append('performance_optimization')
        
        if diagnosis.prompt_engineering_issues:
            priorities.append('prompt_optimization')
        
        # Remove duplicates while preserving order
        seen = set()
        unique_priorities = []
        for p in priorities:
            if p not in seen:
                seen.add(p)
                unique_priorities.append(p)
        
        return unique_priorities[:4]  # Limit to top 4 improvements
    
    async def _generate_code_changes(
        self,
        improvement_type: str,
        diagnosis: DiagnosisReport,
        agent_path: str,
        priority: int
    ) -> List[CodeChange]:
        """Generate specific code changes for an improvement type."""
        changes = []
        
        if improvement_type not in self.improvement_templates:
            logger.warning(f"Unknown improvement type: {improvement_type}")
            return changes
        
        template = self.improvement_templates[improvement_type]
        
        for change_spec in template['changes']:
            if change_spec['type'] == 'add_import':
                changes.append(CodeChange(
                    file_path="agent/agent.py",
                    change_type="add",
                    location="imports",
                    new_code=change_spec['code'],
                    description=f"Add import for {improvement_type}",
                    priority=priority
                ))
            
            elif change_spec['type'] == 'add_tool_registration':
                changes.append(CodeChange(
                    file_path="agent/agent.py",
                    change_type="add",
                    location="__init__",
                    new_code=change_spec['code'],
                    description=f"Register tool for {improvement_type}",
                    priority=priority
                ))
            
            elif change_spec['type'] == 'wrap_method':
                # This would require more sophisticated code analysis
                changes.append(CodeChange(
                    file_path="agent/agent.py",
                    change_type="modify",
                    location="solve_task",
                    old_code="# Original method implementation",
                    new_code=change_spec['template'],
                    description=f"Add error handling to methods",
                    priority=priority
                ))
            
            elif change_spec['type'] == 'modify_system_prompt':
                changes.append(CodeChange(
                    file_path="agent/agent.py",
                    change_type="modify",
                    location="__init__",
                    old_code="self.system_prompt = ",
                    new_code=change_spec['code'],
                    description="Optimize system prompt",
                    priority=priority
                ))
            
            elif change_spec['type'] == 'add_caching':
                changes.append(CodeChange(
                    file_path="agent/agent.py",
                    change_type="add",
                    location="__init__",
                    new_code=change_spec['code'],
                    description="Add response caching",
                    priority=priority
                ))
        
        return changes
    
    def _suggest_new_features(self, diagnosis: DiagnosisReport) -> List[Dict[str, Any]]:
        """Suggest new features based on poor performance."""
        features = []
        
        if diagnosis.overall_score < 0.2:
            features.append({
                'name': 'Multi-step reasoning',
                'description': 'Add chain-of-thought reasoning for complex problems',
                'implementation': 'Add a reasoning module that breaks down problems'
            })
        
        if 'string_manipulation' in diagnosis.benchmark_scores and \
           diagnosis.benchmark_scores['string_manipulation'] < 0.3:
            features.append({
                'name': 'String utilities',
                'description': 'Add specialized string manipulation utilities',
                'implementation': 'Create a string_utils module with common operations'
            })
        
        return features
    
    def _generate_implementation_steps(self, proposal: ModificationProposal) -> List[str]:
        """Generate ordered implementation steps."""
        steps = []
        
        # Group changes by priority
        priority_groups = {}
        for change in proposal.code_changes:
            if change.priority not in priority_groups:
                priority_groups[change.priority] = []
            priority_groups[change.priority].append(change)
        
        # Generate steps for each priority
        for priority in sorted(priority_groups.keys()):
            changes = priority_groups[priority]
            
            # Group by file
            file_changes = {}
            for change in changes:
                if change.file_path not in file_changes:
                    file_changes[change.file_path] = []
                file_changes[change.file_path].append(change)
            
            for file_path, file_change_list in file_changes.items():
                step = f"Modify {file_path}: "
                descriptions = [c.description for c in file_change_list]
                step += ", ".join(descriptions)
                steps.append(step)
        
        # Add feature implementations
        for feature in proposal.new_features:
            steps.append(f"Implement {feature['name']}: {feature['implementation']}")
        
        # Add refactoring tasks
        for task in proposal.refactoring_tasks:
            steps.append(f"Refactor: {task}")
        
        return steps
    
    def _estimate_improvements(
        self,
        proposal: ModificationProposal,
        diagnosis: DiagnosisReport
    ) -> List[str]:
        """Estimate expected improvements from the proposal."""
        improvements = []
        
        # Estimate based on changes
        change_types = [c.description for c in proposal.code_changes]
        
        if any('tool' in ct.lower() for ct in change_types):
            improvements.append("20-30% improvement in code editing tasks")
        
        if any('error' in ct.lower() for ct in change_types):
            improvements.append("Reduced failure rate by handling common errors")
        
        if any('prompt' in ct.lower() for ct in change_types):
            improvements.append("10-15% improvement in response quality")
        
        if any('caching' in ct.lower() or 'timeout' in ct.lower() for ct in change_types):
            improvements.append("25-40% faster execution time")
        
        # Overall estimate
        estimated_score = diagnosis.overall_score * 1.3  # Conservative 30% improvement
        improvements.append(f"Expected overall score: {estimated_score:.2f}")
        
        return improvements
    
    def _assess_risks(self, proposal: ModificationProposal) -> List[str]:
        """Assess risks of the proposed modifications."""
        risks = []
        
        # Check for breaking changes
        modify_changes = [c for c in proposal.code_changes if c.change_type == 'modify']
        if len(modify_changes) > 5:
            risks.append("High number of modifications may introduce bugs")
        
        # Check for complex features
        if proposal.new_features:
            risks.append("New features may increase complexity and maintenance burden")
        
        # Check for critical method changes
        critical_methods = ['solve_task', '__init__', 'get_completion']
        critical_changes = [
            c for c in proposal.code_changes 
            if c.location in critical_methods
        ]
        if critical_changes:
            risks.append("Changes to critical methods may affect core functionality")
        
        if not risks:
            risks.append("Low risk - changes are incremental and well-tested patterns")
        
        return risks