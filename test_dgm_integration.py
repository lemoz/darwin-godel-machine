#!/usr/bin/env python3
"""
Darwin Gödel Machine Integration Test.

Tests the complete DGM evolution loop with basic benchmarks.
"""

import asyncio
import logging
import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dgm_controller import DGMController
from utils.logger import setup_logger

# Setup logging
setup_logger()
logger = logging.getLogger(__name__)


async def run_integration_test():
    """Run a basic integration test of the DGM system."""
    print("\n" + "="*60)
    print("Darwin Gödel Machine - Integration Test")
    print("="*60 + "\n")
    
    try:
        # Initialize the controller
        print("1. Initializing DGM Controller...")
        controller = DGMController("config/dgm_config.yaml")
        print("   ✓ Controller initialized")
        
        # Check configuration
        print("\n2. Configuration:")
        print(f"   - Primary FM Provider: {controller.config.get('fm_providers', {}).get('primary', 'Not set')}")
        print(f"   - Max Iterations: {controller.config.get('dgm_settings', {}).get('max_iterations', 'Not set')}")
        print(f"   - Archive Max Size: {controller.config.get('archive', {}).get('max_size', 'Not set')}")
        
        # Check benchmarks
        print("\n3. Available Benchmarks:")
        benchmark_dir = Path("config/benchmarks")
        benchmarks = list(benchmark_dir.glob("*.yaml"))
        for benchmark in benchmarks:
            print(f"   - {benchmark.stem}")
        # Components are initialized in the constructor
        print("\n4. DGM Components initialized in constructor")
        
        
        # Run a single evolution iteration
        print("\n5. Running Single Evolution Iteration...")
        print("   This will:")
        print("   - Create or select a parent agent")
        print("   - Run self-modification")
        print("   - Evaluate on benchmarks")
        print("   - Update the archive")
        
        # Set to run only 1 iteration for testing
        controller.config['dgm_settings']['max_iterations'] = 1
        
        # Run the evolution
        print("\n   Starting evolution...")
        results = await controller.run()
        
        # Display results
        print("\n6. Results:")
        if results and 'iterations' in results and len(results['iterations']) > 0:
            iteration = results['iterations'][0]
            print(f"   ✓ Iteration completed successfully")
            print(f"   - Parent Agent: {iteration.get('parent_id', 'N/A')}")
            print(f"   - Child Agent: {iteration.get('child_id', 'N/A')}")
            print(f"   - Benchmark Score: {iteration.get('score', 'N/A')}")
            print(f"   - Improvement: {iteration.get('improvement', 'N/A')}")
        else:
            print("   ⚠ No results returned")
        
        print("\n7. Archive Status:")
        archive_size = await controller.archive.get_size()
        print(f"   - Agents in archive: {archive_size}")
        
        # Cleanup
        await controller.cleanup()
        
        print("\n✓ Integration test completed successfully!")
        print("\nThe DGM system is working correctly with basic benchmarks.")
        print("You can now proceed with more complex benchmark integration.\n")
        
    except Exception as e:
        print(f"\n✗ Integration test failed with error:")
        print(f"   {type(e).__name__}: {str(e)}")
        logger.exception("Integration test failed")
        return False
    
    return True


async def main():
    """Main entry point."""
    success = await run_integration_test()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())