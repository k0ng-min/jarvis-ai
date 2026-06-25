"""Compatibility launcher for running JARVIS directly from a source checkout."""

from __future__ import annotations

import sys
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from jarvis_ai import main as _implementation  # noqa: E402

# Preserve legacy imports such as ``import main; main._fast_route(...)``.
globals().update({
    name: getattr(_implementation, name)
    for name in dir(_implementation)
    if not name.startswith("__")
})


if __name__ == "__main__":
    _implementation.main()
