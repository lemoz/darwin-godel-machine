#!/usr/bin/env python3
"""
Reset the Darwin Gödel Machine to its initial state.
This script clears all generated data including:
- Archive (agents and metadata)
- Results
- Agent workspaces
- Logs
"""

import os
import shutil
import json
from pathlib import Path


def reset_dgm():
    """Reset the DGM to initial state."""
    print("Resetting Darwin Gödel Machine to initial state...")
    
    # 1. Clear and reset archive
    print("Clearing archive...")
    archive_dir = Path("archive/agents")
    
    # Remove all agent directories
    for item in archive_dir.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
            print(f"  Removed: {item}")
        elif item.name != "archive_metadata.json":
            item.unlink()
            print(f"  Removed: {item}")
    
    # Reset archive metadata
    metadata_path = archive_dir / "archive_metadata.json"
    with open(metadata_path, 'w') as f:
        json.dump({
            "agents": {},
            "last_updated": None
        }, f, indent=2)
    print("  Reset archive_metadata.json")
    
    # 2. Clear agent workspaces
    print("\nClearing agent workspaces...")
    workspace_dir = Path("agents/workspace")
    if workspace_dir.exists():
        for item in workspace_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
                print(f"  Removed: {item}")
    
    # 3. Clear results (optional - commented out to preserve history)
    # print("\nClearing results...")
    # results_dir = Path("results")
    # for item in results_dir.glob("*.json"):
    #     item.unlink()
    #     print(f"  Removed: {item}")
    
    # 4. Clear logs
    print("\nClearing logs...")
    log_files = [
        "dgm_run.log",
        "logs/dgm.log"
    ]
    for log_file in log_files:
        if Path(log_file).exists():
            Path(log_file).unlink()
            print(f"  Removed: {log_file}")
    
    # 5. Clear test results
    print("\nClearing test results...")
    test_results = Path("test_results.json")
    if test_results.exists():
        test_results.unlink()
        print(f"  Removed: {test_results}")
    
    print("\n✅ DGM reset complete!")
    print("\nThe Darwin Gödel Machine is now in a clean state.")
    print("You can run 'python run_dgm.py' to start fresh.")


if __name__ == "__main__":
    # Confirm with user
    response = input("This will clear all generated agents, archives, and logs. Continue? (y/N): ")
    if response.lower() == 'y':
        reset_dgm()
    else:
        print("Reset cancelled.")