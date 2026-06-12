#!/usr/bin/env python3
"""
Run the Darwin Gödel Machine with basic benchmarks.
"""

import argparse
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


def parse_args(argv=None):
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Run the Darwin Gödel Machine")
    parser.add_argument(
        "--config",
        default="config/dgm_config.yaml",
        help="Path to DGM configuration file",
    )
    parser.add_argument(
        "--generations",
        type=int,
        default=3,
        help="Number of DGM generations to run",
    )
    return parser.parse_args(argv)


async def main(argv=None):
    """Run the DGM loop."""
    args = parse_args(argv)
    try:
        # Initialize the DGM controller
        logger.info("Initializing Darwin Gödel Machine...")
        controller = DGMController(config_or_path=args.config)
        
        logger.info(f"Running DGM for {args.generations} generations...")
        
        await controller.run(num_generations=args.generations)
        
        logger.info("DGM run completed successfully!")
        
    except Exception as e:
        logger.error(f"Error running DGM: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
