#!/usr/bin/env python3
"""Run every test. No dependencies, no test runner to install.

    python3 tests/run_all.py            run everything
    python3 tests/run_all.py --report   print the measured numbers the docs quote
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    if "--report" in sys.argv:
        failed = 0
        for name in ("test_secret_guard.py", "test_estate_map.py"):
            failed |= subprocess.call(
                [sys.executable, str(ROOT / name), "--report"], cwd=ROOT.parent
            )
        return failed

    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT), pattern="test_*.py", top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
