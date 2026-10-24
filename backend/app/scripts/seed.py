"""Database seed script wrapper pointing to backend/scripts/seed.py."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(backend_dir))

from scripts.seed import seed  # noqa: E402

if __name__ == "__main__":
    asyncio.run(seed())
