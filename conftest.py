"""
Root conftest.py — sets dummy env vars so no test ever needs a real API key.
"""
import os
import sys
from pathlib import Path

# Ensure the project root is on sys.path so all absolute imports resolve.
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Dummy credentials — prevent real API calls from test code.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-dummy")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key-dummy")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-dummy")
