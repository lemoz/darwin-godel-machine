"""
Benchmark Scorer for DGM.

Provides different scoring methods for evaluating agent performance on benchmarks.
"""

from typing import Dict, Any, List, Optional, Tuple
from abc import ABC, abstractmethod
import json
import difflib
import logging

logger = logging.getLogger(__name__)


class BaseScorer(ABC):
    """Base class for benchmark scorers."""
    
    @abstractmethod
    def score(
        self,
        actual_output: str,
        expected_output: str,
        test_case: Dict[str, Any]
    ) -> float:
        """
        Score the actual output against expected output.
        
        Args:
            actual_output: The actual output produced
            expected_output: The expected output
            test_case: The test case metadata
            
        Returns:
            Score between 0.0 and 1.0
        """
        pass


class BinaryScorer(BaseScorer):
    """Binary pass/fail scorer."""
    
    def __init__(self, strict: bool = True):
        """
        Initialize binary scorer.
        
        Args:
            strict: If True, requires exact match. If False, strips whitespace.
        """
        self.strict = strict
    
    def score(
        self,
        actual_output: str,
        expected_output: str,
        test_case: Dict[str, Any]
    ) -> float:
        """Return 1.0 if outputs match, 0.0 otherwise."""
        if not self.strict:
            actual_output = actual_output.strip()
            expected_output = expected_output.strip()
        
        return 1.0 if actual_output == expected_output else 0.0


class PartialCreditScorer(BaseScorer):
    """Scorer that gives partial credit based on similarity."""
    
    def __init__(
        self,
        similarity_threshold: float = 0.9,
        ignore_whitespace: bool = True,
        ignore_case: bool = False
    ):
        """
        Initialize partial credit scorer.
        
        Args:
            similarity_threshold: Minimum similarity for full credit
            ignore_whitespace: Whether to normalize whitespace
            ignore_case: Whether to ignore case differences
        """
        self.similarity_threshold = similarity_threshold
        self.ignore_whitespace = ignore_whitespace
        self.ignore_case = ignore_case
    
    def score(
        self,
        actual_output: str,
        expected_output: str,
        test_case: Dict[str, Any]
    ) -> float:
        """Score based on string similarity."""
        # Normalize outputs if needed
        if self.ignore_whitespace:
            actual_output = ' '.join(actual_output.split())
            expected_output = ' '.join(expected_output.split())
        
        if self.ignore_case:
            actual_output = actual_output.lower()
            expected_output = expected_output.lower()
        
        # Calculate similarity
        similarity = difflib.SequenceMatcher(
            None, actual_output, expected_output
        ).ratio()
        
        # Return score based on threshold
        if similarity >= self.similarity_threshold:
            return 1.0
        else:
            return similarity


class JsonScorer(BaseScorer):
    """Scorer for JSON outputs."""
    
    def __init__(
        self,
        required_fields: Optional[List[str]] = None,
        ignore_extra_fields: bool = True,
        partial_credit: bool = True
    ):
        """
        Initialize JSON scorer.
        
        Args:
            required_fields: Fields that must be present and correct
            ignore_extra_fields: Whether to ignore extra fields in actual output
            partial_credit: Whether to give partial credit for partially correct JSON
        """
        self.required_fields = required_fields or []
        self.ignore_extra_fields = ignore_extra_fields
        self.partial_credit = partial_credit
    
    def score(
        self,
        actual_output: str,
        expected_output: str,
        test_case: Dict[str, Any]
    ) -> float:
        """Score JSON outputs."""
        try:
            actual_json = json.loads(actual_output)
            expected_json = json.loads(expected_output)
        except json.JSONDecodeError:
            return 0.0
        
        if not self.partial_credit:
            # Binary comparison
            if self.ignore_extra_fields:
                # Check only that expected fields match
                for key, value in expected_json.items():
                    if actual_json.get(key) != value:
                        return 0.0
                return 1.0
            else:
                return 1.0 if actual_json == expected_json else 0.0
        
        # Partial credit scoring
        total_fields = len(expected_json)
        if total_fields == 0:
            return 1.0
        
        correct_fields = 0
        for key, expected_value in expected_json.items():
            if key in actual_json:
                actual_value = actual_json[key]
                if actual_value == expected_value:
                    correct_fields += 1
                elif isinstance(expected_value, (int, float)) and isinstance(actual_value, (int, float)):
                    # Allow numeric comparisons with tolerance
                    if abs(expected_value - actual_value) < 1e-6:
                        correct_fields += 1
        
        # Check required fields
        if self.required_fields:
            for field in self.required_fields:
                if field not in actual_json or actual_json[field] != expected_json.get(field):
                    return 0.0
        
        return correct_fields / total_fields


class FunctionOutputScorer(BaseScorer):
    """Scorer for function outputs with multiple test cases."""
    
    def __init__(
        self,
        scoring_method: str = "average",
        min_pass_rate: float = 1.0
    ):
        """
        Initialize function output scorer.
        
        Args:
            scoring_method: How to aggregate scores ("average", "min_pass_rate")
            min_pass_rate: Minimum fraction of tests that must pass for credit
        """
        self.scoring_method = scoring_method
        self.min_pass_rate = min_pass_rate
        self.binary_scorer = BinaryScorer(strict=False)
    
    def score(
        self,
        actual_output: str,
        expected_output: str,
        test_case: Dict[str, Any]
    ) -> float:
        """Score function output against expected output."""
        # For single test case, use binary scoring
        return self.binary_scorer.score(actual_output, expected_output, test_case)
    
    def score_multiple(
        self,
        results: List[Tuple[str, str, Dict[str, Any]]]
    ) -> float:
        """
        Score multiple test cases.
        
        Args:
            results: List of (actual_output, expected_output, test_case) tuples
            
        Returns:
            Aggregated score
        """
        if not results:
            return 0.0
        
        scores = []
        for actual, expected, test_case in results:
            scores.append(self.score(actual, expected, test_case))
        
        if self.scoring_method == "average":
            return sum(scores) / len(scores)
        elif self.scoring_method == "min_pass_rate":
            pass_rate = sum(1 for s in scores if s == 1.0) / len(scores)
            return 1.0 if pass_rate >= self.min_pass_rate else 0.0
        else:
            raise ValueError(f"Unknown scoring method: {self.scoring_method}")


class BenchmarkScorer:
    """Main scorer that selects appropriate scoring method based on benchmark type."""
    
    def __init__(self):
        """Initialize benchmark scorer with available scoring methods."""
        self.scorers = {
            'binary': BinaryScorer(),
            'partial': PartialCreditScorer(),
            'json': JsonScorer(),
            'function': FunctionOutputScorer()
        }
    
    def get_scorer(self, benchmark_config: Dict[str, Any]) -> BaseScorer:
        """
        Get appropriate scorer based on benchmark configuration.
        
        Args:
            benchmark_config: Benchmark configuration dictionary
            
        Returns:
            Appropriate scorer instance
        """
        scoring_config = benchmark_config.get('scoring', {})
        scoring_method = scoring_config.get('method', 'binary')
        
        if scoring_method == 'binary':
            strict = scoring_config.get('strict', True)
            return BinaryScorer(strict=strict)
        
        elif scoring_method == 'partial':
            return PartialCreditScorer(
                similarity_threshold=scoring_config.get('similarity_threshold', 0.9),
                ignore_whitespace=scoring_config.get('ignore_whitespace', True),
                ignore_case=scoring_config.get('ignore_case', False)
            )
        
        elif scoring_method == 'json':
            return JsonScorer(
                required_fields=scoring_config.get('required_fields'),
                ignore_extra_fields=scoring_config.get('ignore_extra_fields', True),
                partial_credit=scoring_config.get('partial_credit', True)
            )
        
        elif scoring_method == 'function':
            return FunctionOutputScorer(
                scoring_method=scoring_config.get('aggregation', 'average'),
                min_pass_rate=scoring_config.get('min_pass_rate', 1.0)
            )
        
        else:
            logger.warning(f"Unknown scoring method '{scoring_method}', using binary")
            return BinaryScorer()
    
    def score_result(
        self,
        benchmark_config: Dict[str, Any],
        actual_output: str,
        expected_output: str,
        test_case: Dict[str, Any]
    ) -> float:
        """
        Score a single test result.
        
        Args:
            benchmark_config: Benchmark configuration
            actual_output: Actual output produced
            expected_output: Expected output
            test_case: Test case metadata
            
        Returns:
            Score between 0.0 and 1.0
        """
        scorer = self.get_scorer(benchmark_config)
        return scorer.score(actual_output, expected_output, test_case)
    
    def score_benchmark(
        self,
        benchmark_config: Dict[str, Any],
        results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Score complete benchmark results.
        
        Args:
            benchmark_config: Benchmark configuration
            results: List of test results
            
        Returns:
            Benchmark scoring summary
        """
        if not results:
            return {
                'total_score': 0.0,
                'passed_tests': 0,
                'total_tests': 0,
                'scores': []
            }
        
        scorer = self.get_scorer(benchmark_config)
        scores = []
        
        for result in results:
            if result.get('error'):
                scores.append(0.0)
            else:
                score = scorer.score(
                    result.get('actual_output', ''),
                    result.get('expected_output', ''),
                    result.get('test_case', {})
                )
                scores.append(score)
        
        # Calculate aggregate score based on method
        if isinstance(scorer, FunctionOutputScorer):
            # Use function scorer's aggregation method
            test_results = [
                (r.get('actual_output', ''), r.get('expected_output', ''), r.get('test_case', {}))
                for r in results if not r.get('error')
            ]
            total_score = scorer.score_multiple(test_results) if test_results else 0.0
        else:
            # Average all scores
            total_score = sum(scores) / len(scores) if scores else 0.0
        
        return {
            'total_score': total_score,
            'passed_tests': sum(1 for s in scores if s == 1.0),
            'total_tests': len(results),
            'scores': scores,
            'scoring_method': benchmark_config.get('scoring', {}).get('method', 'binary')
        }