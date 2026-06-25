"""Application and runtime path definitions."""

from __future__ import annotations

import sys
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent

if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = PACKAGE_DIR.parents[1]

CONFIG_DIR = PROJECT_ROOT / "config"
MEMORY_DIR = PROJECT_ROOT / "memory"
LOG_DIR = PROJECT_ROOT / "logs"
PROMPT_PATH = PACKAGE_DIR / "core" / "prompt.txt"
