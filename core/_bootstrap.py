"""
PSO Bootstrap Module
====================

Handles Python path setup for all core modules.
Import this at the top of any module that needs cross-package imports.

This centralizes the sys.path manipulation that was previously duplicated
across 31+ files, making the codebase more maintainable.

Usage:
    from core import _bootstrap  # That's it!
    from core.database import Database  # Now this works
"""

import sys
from pathlib import Path

# Calculate project root (parent of 'core' directory)
_PROJECT_ROOT = Path(__file__).parent.parent

# Add to path if not already present (idempotent)
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Optional: Make this module's imports available
__all__ = []  # Empty - this module just sets up paths
