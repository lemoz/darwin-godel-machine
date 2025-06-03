#!/usr/bin/env python3
"""
Test harness for running all DGM tests.
"""

import sys
import unittest
import asyncio
import argparse
from pathlib import Path
import time
import json
from datetime import datetime


class TestHarness:
    """Main test harness for DGM system."""
    
    def __init__(self, verbosity=2):
        """Initialize test harness."""
        self.verbosity = verbosity
        self.test_results = {
            "timestamp": datetime.now().isoformat(),
            "unit_tests": {},
            "integration_tests": {},
            "summary": {}
        }
    
    def discover_tests(self, test_dir, pattern="test_*.py"):
        """Discover all tests in directory."""
        loader = unittest.TestLoader()
        suite = loader.discover(str(test_dir), pattern=pattern)
        return suite
    
    def run_test_suite(self, suite, suite_name):
        """Run a test suite and collect results."""
        print(f"\n{'='*60}")
        print(f"Running {suite_name}")
        print(f"{'='*60}")
        
        runner = unittest.TextTestRunner(verbosity=self.verbosity)
        start_time = time.time()
        result = runner.run(suite)
        duration = time.time() - start_time
        
        # Collect results
        test_count = result.testsRun
        failures = len(result.failures)
        errors = len(result.errors)
        skipped = len(result.skipped)
        success = test_count - failures - errors - skipped
        
        suite_results = {
            "total": test_count,
            "success": success,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
            "duration": round(duration, 2),
            "success_rate": round((success / test_count * 100) if test_count > 0 else 0, 2)
        }
        
        # Store detailed failure/error info
        if result.failures:
            suite_results["failure_details"] = [
                {"test": str(test), "error": traceback}
                for test, traceback in result.failures
            ]
        
        if result.errors:
            suite_results["error_details"] = [
                {"test": str(test), "error": traceback}
                for test, traceback in result.errors
            ]
        
        return suite_results, result.wasSuccessful()
    
    def run_unit_tests(self):
        """Run all unit tests."""
        unit_test_dir = Path("tests/unit")
        if not unit_test_dir.exists():
            print(f"Unit test directory not found: {unit_test_dir}")
            return False
        
        suite = self.discover_tests(unit_test_dir)
        results, success = self.run_test_suite(suite, "Unit Tests")
        self.test_results["unit_tests"] = results
        return success
    
    def run_integration_tests(self):
        """Run all integration tests."""
        integration_test_dir = Path("tests/integration")
        if not integration_test_dir.exists():
            print(f"Integration test directory not found: {integration_test_dir}")
            return False
        
        suite = self.discover_tests(integration_test_dir)
        results, success = self.run_test_suite(suite, "Integration Tests")
        self.test_results["integration_tests"] = results
        return success
    
    def run_specific_test(self, test_path):
        """Run a specific test file or test case."""
        print(f"\n{'='*60}")
        print(f"Running specific test: {test_path}")
        print(f"{'='*60}")
        
        loader = unittest.TestLoader()
        
        # Handle different test path formats
        if ".py" in test_path:
            # Test file
            module_name = test_path.replace("/", ".").replace(".py", "")
            suite = loader.loadTestsFromName(module_name)
        else:
            # Test case or method
            suite = loader.loadTestsFromName(test_path)
        
        runner = unittest.TextTestRunner(verbosity=self.verbosity)
        result = runner.run(suite)
        return result.wasSuccessful()
    
    def generate_summary(self):
        """Generate test summary."""
        unit_results = self.test_results.get("unit_tests", {})
        integration_results = self.test_results.get("integration_tests", {})
        
        total_tests = unit_results.get("total", 0) + integration_results.get("total", 0)
        total_success = unit_results.get("success", 0) + integration_results.get("success", 0)
        total_failures = unit_results.get("failures", 0) + integration_results.get("failures", 0)
        total_errors = unit_results.get("errors", 0) + integration_results.get("errors", 0)
        total_duration = unit_results.get("duration", 0) + integration_results.get("duration", 0)
        
        self.test_results["summary"] = {
            "total_tests": total_tests,
            "total_success": total_success,
            "total_failures": total_failures,
            "total_errors": total_errors,
            "total_duration": round(total_duration, 2),
            "overall_success_rate": round((total_success / total_tests * 100) if total_tests > 0 else 0, 2),
            "all_passed": total_failures == 0 and total_errors == 0
        }
    
    def print_summary(self):
        """Print test summary."""
        summary = self.test_results["summary"]
        
        print(f"\n{'='*60}")
        print("TEST SUMMARY")
        print(f"{'='*60}")
        print(f"Total Tests Run: {summary['total_tests']}")
        print(f"Successful: {summary['total_success']}")
        print(f"Failures: {summary['total_failures']}")
        print(f"Errors: {summary['total_errors']}")
        print(f"Success Rate: {summary['overall_success_rate']}%")
        print(f"Total Duration: {summary['total_duration']}s")
        print(f"{'='*60}")
        
        if summary['all_passed']:
            print("✅ ALL TESTS PASSED!")
        else:
            print("❌ SOME TESTS FAILED!")
    
    def save_results(self, output_file="test_results.json"):
        """Save test results to JSON file."""
        with open(output_file, 'w') as f:
            json.dump(self.test_results, f, indent=2)
        print(f"\nTest results saved to: {output_file}")
    
    def run_all_tests(self):
        """Run all test suites."""
        print("Starting DGM Test Harness...")
        print(f"Timestamp: {self.test_results['timestamp']}")
        
        # Run unit tests
        unit_success = self.run_unit_tests()
        
        # Run integration tests
        integration_success = self.run_integration_tests()
        
        # Generate summary
        self.generate_summary()
        self.print_summary()
        
        # Save results
        self.save_results()
        
        return unit_success and integration_success


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="DGM Test Harness")
    parser.add_argument(
        "--verbosity", "-v",
        type=int,
        choices=[0, 1, 2],
        default=2,
        help="Test output verbosity (0=quiet, 1=normal, 2=verbose)"
    )
    parser.add_argument(
        "--unit-only",
        action="store_true",
        help="Run only unit tests"
    )
    parser.add_argument(
        "--integration-only",
        action="store_true",
        help="Run only integration tests"
    )
    parser.add_argument(
        "--test",
        type=str,
        help="Run specific test (e.g., 'tests.unit.test_archive' or 'tests.unit.test_archive.TestArchive.test_add_agent')"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="test_results.json",
        help="Output file for test results (default: test_results.json)"
    )
    
    args = parser.parse_args()
    
    # Initialize harness
    harness = TestHarness(verbosity=args.verbosity)
    
    # Run tests based on arguments
    if args.test:
        # Run specific test
        success = harness.run_specific_test(args.test)
    elif args.unit_only:
        # Run only unit tests
        success = harness.run_unit_tests()
        harness.test_results["summary"] = harness.test_results["unit_tests"]
        harness.print_summary()
        harness.save_results(args.output)
    elif args.integration_only:
        # Run only integration tests
        success = harness.run_integration_tests()
        harness.test_results["summary"] = harness.test_results["integration_tests"]
        harness.print_summary()
        harness.save_results(args.output)
    else:
        # Run all tests
        success = harness.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    # Handle async tests properly
    if sys.platform.startswith('win'):
        # Windows-specific event loop policy
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    main()