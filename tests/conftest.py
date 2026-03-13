from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root + project/ are importable for tests.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_DIR = _REPO_ROOT / "project"

for p in (str(_REPO_ROOT), str(_PROJECT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)
