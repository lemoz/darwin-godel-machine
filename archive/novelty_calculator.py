"""
Novelty calculation for encouraging diverse agent behaviors.
"""

import ast
import difflib
from typing import List, Dict, Any, Set, Tuple
from collections import Counter
import re

from .archive_manager import ArchiveEntry, AgentArchive


class NoveltyCalculator:
    """
    Calculates novelty scores for agents based on their uniqueness.
    
    Novelty is measured by comparing agent characteristics against
    the existing population to encourage exploration of new approaches.
    """
    
    def __init__(self, k_nearest: int = 15):
        """
        Initialize novelty calculator.
        
        Args:
            k_nearest: Number of nearest neighbors to consider
        """
        self.k_nearest = k_nearest
    
    def calculate_novelty(
        self,
        agent_path: str,
        archive: AgentArchive,
        benchmark_results: Dict[str, Any]
    ) -> float:
        """
        Calculate novelty score for an agent.
        
        Args:
            agent_path: Path to agent code
            archive: Agent archive for comparison
            benchmark_results: Agent's benchmark results
            
        Returns:
            Novelty score (0-1)
        """
        # Get agent characteristics
        characteristics = self._extract_characteristics(agent_path, benchmark_results)
        
        # Get archive agents
        archive_agents = archive.get_all_agents()
        if not archive_agents:
            return 1.0  # First agent is maximally novel
        
        # Calculate distances to all archive agents
        distances = []
        for entry in archive_agents:
            # Skip if comparing to self
            if entry.agent_path == agent_path:
                continue
            
            # Get archived agent characteristics
            archive_chars = self._extract_characteristics(
                entry.agent_path,
                entry.benchmark_results
            )
            
            # Calculate distance
            distance = self._calculate_distance(characteristics, archive_chars)
            distances.append(distance)
        
        if not distances:
            return 1.0
        
        # Sort distances and take k-nearest
        distances.sort()
        k_distances = distances[:min(self.k_nearest, len(distances))]
        
        # Calculate average distance to k-nearest neighbors
        avg_distance = sum(k_distances) / len(k_distances)
        
        # Normalize to 0-1 range (assuming max distance is 1.0)
        return min(1.0, avg_distance)
    
    def _extract_characteristics(
        self,
        agent_path: str,
        benchmark_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract characteristics that define agent behavior."""
        characteristics = {}
        
        # Code structure characteristics
        try:
            with open(agent_path, 'r') as f:
                code = f.read()
            
            # AST-based features
            tree = ast.parse(code)
            characteristics['num_functions'] = len([
                node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
            ])
            characteristics['num_classes'] = len([
                node for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef)
            ])
            characteristics['num_loops'] = len([
                node for node in ast.walk(tree)
                if isinstance(node, (ast.For, ast.While))
            ])
            characteristics['num_conditionals'] = len([
                node for node in ast.walk(tree)
                if isinstance(node, ast.If)
            ])
            
            # Code patterns
            characteristics['uses_recursion'] = 'def ' in code and any(
                func_name in code.split(f'def {func_name}')[1].split('def ')[0]
                for func_name in re.findall(r'def\s+(\w+)', code)
            )
            characteristics['uses_comprehensions'] = '[' in code and 'for' in code
            characteristics['uses_generators'] = 'yield' in code
            characteristics['uses_decorators'] = '@' in code
            
            # Import patterns
            imports = [
                node for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
            ]
            characteristics['num_imports'] = len(imports)
            characteristics['import_modules'] = self._get_import_modules(imports)
            
        except Exception:
            # Fallback to basic characteristics
            characteristics['code_length'] = len(code) if 'code' in locals() else 0
        
        # Benchmark performance characteristics
        if benchmark_results:
            characteristics['success_rate'] = benchmark_results.get('success_rate', 0)
            characteristics['avg_score'] = benchmark_results.get('avg_score', 0)
            characteristics['benchmark_patterns'] = self._extract_benchmark_patterns(
                benchmark_results
            )
        
        return characteristics
    
    def _get_import_modules(self, imports: List[ast.AST]) -> Set[str]:
        """Extract imported module names."""
        modules = set()
        for node in imports:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    modules.add(node.module.split('.')[0])
        return modules
    
    def _extract_benchmark_patterns(
        self,
        benchmark_results: Dict[str, Any]
    ) -> List[str]:
        """Extract patterns from benchmark results."""
        patterns = []
        
        # Success/failure patterns
        if 'test_results' in benchmark_results:
            for test_name, result in benchmark_results['test_results'].items():
                if result.get('passed', False):
                    patterns.append(f"passed:{test_name}")
                else:
                    patterns.append(f"failed:{test_name}")
        
        # Error patterns
        if 'errors' in benchmark_results:
            for error in benchmark_results['errors']:
                error_type = error.get('type', 'unknown')
                patterns.append(f"error:{error_type}")
        
        return patterns
    
    def _calculate_distance(
        self,
        chars1: Dict[str, Any],
        chars2: Dict[str, Any]
    ) -> float:
        """Calculate distance between two characteristic sets."""
        distance = 0.0
        num_features = 0
        
        # Numeric features
        numeric_features = [
            'num_functions', 'num_classes', 'num_loops',
            'num_conditionals', 'num_imports', 'code_length',
            'success_rate', 'avg_score'
        ]
        
        for feature in numeric_features:
            if feature in chars1 and feature in chars2:
                val1 = chars1[feature]
                val2 = chars2[feature]
                # Normalize difference to 0-1 range
                if val1 + val2 > 0:
                    diff = abs(val1 - val2) / (val1 + val2)
                    distance += diff
                    num_features += 1
        
        # Boolean features
        boolean_features = [
            'uses_recursion', 'uses_comprehensions',
            'uses_generators', 'uses_decorators'
        ]
        
        for feature in boolean_features:
            if feature in chars1 and feature in chars2:
                if chars1[feature] != chars2[feature]:
                    distance += 1.0
                num_features += 1
        
        # Set features (imports)
        if 'import_modules' in chars1 and 'import_modules' in chars2:
            set1 = chars1['import_modules']
            set2 = chars2['import_modules']
            if set1 or set2:
                jaccard = len(set1 & set2) / len(set1 | set2)
                distance += (1 - jaccard)
                num_features += 1
        
        # Pattern features
        if 'benchmark_patterns' in chars1 and 'benchmark_patterns' in chars2:
            patterns1 = set(chars1['benchmark_patterns'])
            patterns2 = set(chars2['benchmark_patterns'])
            if patterns1 or patterns2:
                jaccard = len(patterns1 & patterns2) / len(patterns1 | patterns2)
                distance += (1 - jaccard)
                num_features += 1
        
        # Average distance across all features
        if num_features > 0:
            return distance / num_features
        else:
            return 0.5  # Default distance if no features to compare
    
    def get_diversity_metrics(self, archive: AgentArchive) -> Dict[str, float]:
        """Calculate diversity metrics for the archive."""
        agents = archive.get_all_agents()
        if len(agents) < 2:
            return {
                'avg_pairwise_distance': 0.0,
                'characteristic_diversity': 0.0,
                'behavioral_diversity': 0.0
            }
        
        # Calculate pairwise distances
        distances = []
        for i, agent1 in enumerate(agents):
            chars1 = self._extract_characteristics(
                agent1.agent_path,
                agent1.benchmark_results
            )
            for agent2 in agents[i+1:]:
                chars2 = self._extract_characteristics(
                    agent2.agent_path,
                    agent2.benchmark_results
                )
                distance = self._calculate_distance(chars1, chars2)
                distances.append(distance)
        
        avg_distance = sum(distances) / len(distances) if distances else 0.0
        
        # Calculate characteristic diversity
        all_chars = []
        for agent in agents:
            chars = self._extract_characteristics(
                agent.agent_path,
                agent.benchmark_results
            )
            all_chars.append(chars)
        
        # Count unique values for each characteristic
        char_diversity = {}
        for key in all_chars[0].keys():
            if isinstance(all_chars[0][key], (int, float, bool, str)):
                unique_values = len(set(chars.get(key, None) for chars in all_chars))
                char_diversity[key] = unique_values / len(agents)
        
        avg_char_diversity = sum(char_diversity.values()) / len(char_diversity) if char_diversity else 0.0
        
        # Calculate behavioral diversity (based on benchmark patterns)
        all_patterns = []
        for agent in agents:
            patterns = self._extract_benchmark_patterns(agent.benchmark_results)
            all_patterns.extend(patterns)
        
        pattern_counter = Counter(all_patterns)
        behavioral_diversity = len(pattern_counter) / len(agents) if agents else 0.0
        
        return {
            'avg_pairwise_distance': avg_distance,
            'characteristic_diversity': avg_char_diversity,
            'behavioral_diversity': behavioral_diversity
        }