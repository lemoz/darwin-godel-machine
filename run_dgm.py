#!/usr/bin/env python3
"""
Run the Darwin Gödel Machine with basic benchmarks.
"""

import asyncio
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dgm_controller import DGMController

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('dgm_run.log')
    ]
)

logger = logging.getLogger(__name__)


async def main():
    """Run the DGM loop."""
    try:
        # Initialize the DGM controller
        logger.info("Initializing Darwin Gödel Machine...")
        controller = DGMController()
        
        # Run for a limited number of generations
        num_generations = 3  # Start with 3 generations for testing
        logger.info(f"Running DGM for {num_generations} generations...")
        
        await controller.run(num_generations=num_generations)
        
        logger.info("DGM run completed successfully!")
        
    except Exception as e:
        logger.error(f"Error running DGM: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())