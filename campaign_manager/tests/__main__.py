from __future__ import annotations

import sys
import unittest
from pathlib import Path

loader = unittest.TestLoader()
suite = loader.discover(str(Path(__file__).parent), pattern="test_*.py")
runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
