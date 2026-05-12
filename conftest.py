"""Project-root conftest. Ensures the source tree is importable as `src.*`
when running `pytest` from the project directory.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
