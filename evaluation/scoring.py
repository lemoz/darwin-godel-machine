"""
Scoring methods for evaluating agent performance on benchmarks.
"""

from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
import re
import ast
import difflib


@dataclass
class ScoringResult:
    """Result of a scoring operation."""
    score: float
    max_score: float
    passed: bool
    details: Dict[str, Any]
    
    @property
    def percentage(self) -> float:
        """Get score as percentage."""
        if self.max_score == 0:
            return 0.0
        return (self.score / self.max_score) * 100


class ScoringMethods:
    """Collection of scoring methods for different types of benchmarks."""
    
    @staticmethod
    def exact_match(expected: str, actual: str) -> ScoringResult:
        """Score based on exact string match."""
        score = 1.0 if expected.strip() == actual.strip() else 0.0
        return ScoringResult(
            score=score,
            max_score=1.0,
            passed=score == 1.0,
            details={
                'expected': expected,
                'actual': actual,
                'match': score == 1.0
            }
        )
    
    @staticmethod
    def substring_match(expected: str, actual: str) -> ScoringResult:
        """Score based on substring presence."""
        score = 1.0 if expected.strip() in actual.strip() else 0.0
        return ScoringResult(
            score=score,
            max_score=1.0,
            passed=score == 1.0,
            details={
                'expected_substring': expected,
                'actual': actual,
                'found': score == 1.0
            }
        )
    
    @staticmethod
    def regex_match(pattern: str, actual: str) -> ScoringResult:
        """Score based on regex pattern match."""
        try:
            match = bool(re.search(pattern, actual))
            score = 1.0 if match else 0.0
            return ScoringResult(
                score=score,
                max_score=1.0,
                passed=score == 1.0,
                details={
                    'pattern': pattern,
                    'actual': actual,
                    'matched': match
                }
            )
        except re.error as e:
            return ScoringResult(
                score=0.0,
                max_score=1.0,
                passed=False,
                details={
                    'pattern': pattern,
                    'actual': actual,
                    'error': str(e)
                }
            )
    
    @staticmethod
    def similarity_score(expected: str, actual: str, threshold: float = 0.8) -> ScoringResult:
        """Score based on string similarity ratio."""
        ratio = difflib.SequenceMatcher(None, expected, actual).ratio()
        passed = ratio >= threshold
        return ScoringResult(
            score=ratio,
            max_score=1.0,
            passed=passed,
            details={
                'expected': expected,
                'actual': actual,
                'similarity': ratio,
                'threshold': threshold
            }
        )
    
    @staticmethod
    def ast_match(expected_code: str, actual_code: str) -> ScoringResult:
        """Score based on AST equivalence (for Python code)."""
        try:
            expected_ast = ast.parse(expected_code)
            actual_ast = ast.parse(actual_code)
            
            # Simple AST comparison (could be enhanced)
            expected_dump = ast.dump(expected_ast, annotate_fields=False)
            actual_dump = ast.dump(actual_ast, annotate_fields=False)
            
            match = expected_dump == actual_dump
            score = 1.0 if match else 0.0
            
            return ScoringResult(
                score=score,
                max_score=1.0,
                passed=score == 1.0,
                details={
                    'expected_code': expected_code,
                    'actual_code': actual_code,
                    'ast_match': match
                }
            )
        except SyntaxError as e:
            return ScoringResult(
                score=0.0,
                max_score=1.0,
                passed=False,
                details={
                    'expected_code': expected_code,
                    'actual_code': actual_code,
                    'error': str(e)
                }
            )
    
    @staticmethod
    def multi_criteria(
        actual: str,
        criteria: List[Dict[str, Any]]
    ) -> ScoringResult:
        """
        Score based on multiple criteria.
        
        Each criterion should have:
        - 'method': scoring method name
        - 'expected': expected value
        - 'weight': weight for this criterion (default 1.0)
        """
        total_score = 0.0
        total_weight = 0.0
        results = []
        
        methods = {
            'exact': ScoringMethods.exact_match,
            'substring': ScoringMethods.substring_match,
            'regex': ScoringMethods.regex_match,
            'similarity': ScoringMethods.similarity_score,
            'ast': ScoringMethods.ast_match
        }
        
        for criterion in criteria:
            method_name = criterion.get('method', 'exact')
            expected = criterion.get('expected', '')
            weight = criterion.get('weight', 1.0)
            
            if method_name in methods:
                method = methods[method_name]
                if method_name == 'similarity':
                    threshold = criterion.get('threshold', 0.8)
                    result = method(expected, actual, threshold)
                else:
                    result = method(expected, actual)
                
                total_score += result.score * weight
                total_weight += weight
                results.append({
                    'method': method_name,
                    'result': result,
                    'weight': weight
                })
        
        if total_weight == 0:
            final_score = 0.0
        else:
            final_score = total_score / total_weight
        
        return ScoringResult(
            score=final_score,
            max_score=1.0,
            passed=final_score >= 0.5,  # Default passing threshold
            details={
                'criteria_results': results,
                'total_score': total_score,
                'total_weight': total_weight
            }
        )
    
    @staticmethod
    def custom_scorer(
        expected: Any,
        actual: Any,
        scorer_func: Callable[[Any, Any], float]
    ) -> ScoringResult:
        """Use a custom scoring function."""
        try:
            score = scorer_func(expected, actual)
            score = max(0.0, min(1.0, score))  # Clamp to [0, 1]
            
            return ScoringResult(
                score=score,
                max_score=1.0,
                passed=score >= 0.5,
                details={
                    'expected': str(expected),
                    'actual': str(actual),
                    'custom_score': score
                }
            )
        except Exception as e:
            return ScoringResult(
                score=0.0,
                max_score=1.0,
                passed=False,
                details={
                    'expected': str(expected),
                    'actual': str(actual),
                    'error': str(e)
                }
            )


class BenchmarkScorer:
    """Base class for benchmark scoring."""
    
    def score(self, actual: str, expected: str, metadata: Dict[str, Any]) -> float:
        """Score the actual output against expected output."""
        raise NotImplementedError("Subclasses must implement score method")
    
    def get_scorer(self, config: Dict[str, Any]) -> 'BenchmarkScorer':
        """Get appropriate scorer based on config."""
        # Check for nested scoring config first (test expects this structure)
        scoring_config = config.get('scoring', {})
        scorer_type = scoring_config.get('method', config.get('scorer', 'binary'))
        
        if scorer_type == 'binary':
            return BinaryScorer(strict=config.get('strict', True))
        elif scorer_type == 'partial':
            return PartialCreditScorer(
                similarity_threshold=config.get('similarity_threshold', 0.9),
                ignore_whitespace=config.get('ignore_whitespace', True)
            )
        elif scorer_type == 'json':
            return JsonScorer(
                required_fields=config.get('required_fields', []),
                partial_credit=config.get('partial_credit', True)
            )
        elif scorer_type == 'function':
            return FunctionOutputScorer(
                eval_function=config.get('eval_function')
            )
        else:
            # Default to binary scorer
            return BinaryScorer(strict=True)
    
    def score_benchmark(self, config: Dict[str, Any], results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Score complete benchmark results."""
        total_score = 0.0
        total_tests = len(results)
        passed_tests = 0
        
        # Get the appropriate scorer
        scorer = self.get_scorer(config)
        
        # Score each test result
        scored_results = []
        for result in results:
            if result.get('error'):
                # Test failed with error
                test_score = 0.0
            else:
                # Score the output
                test_score = scorer.score(
                    result.get('actual_output', ''),
                    result.get('expected_output', ''),
                    result.get('metadata', {})
                )
            
            if test_score >= config.get('pass_threshold', 1.0):
                passed_tests += 1
            
            total_score += test_score
            
            scored_results.append({
                **result,
                'score': test_score,
                'passed': test_score >= config.get('pass_threshold', 1.0)
            })
        
        # Calculate summary statistics
        avg_score = total_score / total_tests if total_tests > 0 else 0.0
        pass_rate = passed_tests / total_tests if total_tests > 0 else 0.0
        
        return {
            'benchmark_name': config.get('name', 'unknown'),
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'failed_tests': total_tests - passed_tests,
            'average_score': avg_score,
            'total_score': avg_score,  # Added for test compatibility
            'pass_rate': pass_rate,
            'scores': scored_results,  # Also provide as 'scores' for test compatibility
            'test_results': scored_results,
            'scorer_type': config.get('scorer', 'binary'),
            'pass_threshold': config.get('pass_threshold', 1.0)
        }


class BinaryScorer(BenchmarkScorer):
    """Binary scoring - exact match or not."""
    
    def __init__(self, strict: bool = True):
        self.strict = strict
    
    def score(self, actual: str, expected: str, metadata: Dict[str, Any]) -> float:
        """Return 1.0 for exact match, 0.0 otherwise."""
        if self.strict:
            return 1.0 if actual == expected else 0.0
        else:
            return 1.0 if actual.strip() == expected.strip() else 0.0


class PartialCreditScorer(BenchmarkScorer):
    """Partial credit based on similarity."""
    
    def __init__(self, similarity_threshold: float = 0.9, ignore_whitespace: bool = True):
        self.similarity_threshold = similarity_threshold
        self.ignore_whitespace = ignore_whitespace
    
    def score(self, actual: str, expected: str, metadata: Dict[str, Any]) -> float:
        """Return partial credit based on string similarity."""
        if self.ignore_whitespace:
            actual = ' '.join(actual.split())
            expected = ' '.join(expected.split())
        
        result = ScoringMethods.similarity_score(expected, actual, self.similarity_threshold)
        return result.score


class JsonScorer(BenchmarkScorer):
    """JSON output scoring."""
    
    def __init__(self, required_fields: Optional[List[str]] = None, partial_credit: bool = True):
        self.required_fields = required_fields or []
        self.partial_credit = partial_credit
    
    def score(self, actual: str, expected: str, metadata: Dict[str, Any]) -> float:
        """Score JSON outputs."""
        try:
            import json
            actual_json = json.loads(actual)
            expected_json = json.loads(expected)
            
            # Check required fields
            for field in self.required_fields:
                if field not in actual_json:
                    return 0.0
            
            if not self.partial_credit:
                return 1.0 if actual_json == expected_json else 0.0
            
            # Calculate partial credit
            total_fields = len(expected_json)
            matching_fields = 0
            
            for key, value in expected_json.items():
                if key in actual_json and actual_json[key] == value:
                    matching_fields += 1
            
            return matching_fields / total_fields if total_fields > 0 else 0.0
            
        except json.JSONDecodeError:
            return 0.0


class FunctionOutputScorer(BenchmarkScorer):
    """Score based on function output evaluation."""
    
    def __init__(self, eval_function: Optional[Callable[[str, str], float]] = None):
        self.eval_function = eval_function or self._default_eval
    
    def _default_eval(self, actual: str, expected: str) -> float:
        """Default evaluation function."""
        return 1.0 if actual == expected else 0.0
    
    def score(self, actual: str, expected: str, metadata: Dict[str, Any]) -> float:
        """Score using the evaluation function."""
        try:
            return self.eval_function(actual, expected)
        except Exception:
            return 0.0