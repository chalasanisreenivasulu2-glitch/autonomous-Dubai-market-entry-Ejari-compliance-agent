"""
Pytest configuration: ensures the project root is on sys.path
so `from src.* import ...` works when tests run from any directory.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))