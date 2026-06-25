"""Run a test script with the local src-layout package available."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

if len(sys.argv) != 2:
    raise SystemExit("사용법: python scripts/run_test.py tests/integration/<파일>.py")

target = (ROOT / sys.argv[1]).resolve()
if ROOT not in target.parents or not target.is_file():
    raise SystemExit(f"유효한 테스트 파일이 아닙니다: {target}")

runpy.run_path(str(target), run_name="__main__")
