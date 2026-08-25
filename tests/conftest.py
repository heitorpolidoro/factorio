"""Pytest configuration for tests."""
import sys
from pathlib import Path

# Add parent directory to path so we can import tree module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
