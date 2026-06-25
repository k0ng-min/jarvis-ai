"""
자비스 설치 스크립트
Claude CLI(claude -p) 기반 한국어 AI 어시스턴트

사용법:
    python scripts/bootstrap.py          - 의존성 설치 + 브라우저 설치
    python scripts/bootstrap.py --check  - 환경 점검만
"""

from __future__ import annotations
import subprocess
import sys
import shutil
import platform
import os

_OS = platform.system()

REQUIRED_PACKAGES = [
    "PyQt6",
    "psutil",
    "SpeechRecognition",
    "sounddevice",
    "soundfile",
    "edge-tts",
    "Pillow",
    "pymupdf",
    "python-docx",
    "python-pptx",
    "openpyxl",
    "playwright",
    "pyautogui",
    "pyperclip",
    "requests",
]

if _OS == "Windows":
    REQUIRED_PACKAGES.append("pywin32")


def _ok(msg: str): print(f"  ✅  {msg}")
def _warn(msg: str): print(f"  ⚠️  {msg}")
def _err(msg: str): print(f"  ❌  {msg}")
def _info(msg: str): print(f"  ℹ️  {msg}")


def check_python():
    print("\n[ Python 버전 확인 ]")
    ver = sys.version_info
    if ver >= (3, 10):
        _ok(f"Python {ver.major}.{ver.minor}.{ver.micro}")
    else:
        _err(f"Python 3.10 이상 필요 (현재: {ver.major}.{ver.minor}.{ver.micro})")
        sys.exit(1)


def check_claude_cli():
    print("\n[ Claude CLI 확인 ]")
    if shutil.which("claude"):
        try:
            r = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=5)
            version = r.stdout.strip() or r.stderr.strip()
            _ok(f"Claude CLI 설치됨: {version}")
            return True
        except Exception:
            _warn("Claude CLI가 있지만 버전 확인 실패")
            return True
    else:
        _err("Claude CLI 미설치")
        _info("설치 방법: npm install -g @anthropic-ai/claude-code")
        _info("그 후 'claude' 명령어로 로그인하세요")
        return False


def install_packages():
    print("\n[ 패키지 설치 ]")
    for pkg in REQUIRED_PACKAGES:
        mod = pkg.split(">=")[0].replace("-", "_").lower()
        # 임포트 이름 매핑
        import_names = {
            "pyqt6": "PyQt6",
            "pymupdf": "fitz",
            "python_docx": "docx",
            "python_pptx": "pptx",
            "pillow": "PIL",
            "speechrecognition": "speech_recognition",
            "edge_tts": "edge_tts",
        }
        import_name = import_names.get(mod, mod)
        try:
            __import__(import_name)
            _ok(f"{pkg} — 이미 설치됨")
        except ImportError:
            print(f"  📦  {pkg} 설치 중...", end=" ", flush=True)
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", pkg,
                 "--break-system-packages", "-q"],
                capture_output=True
            )
            if r.returncode == 0:
                print("완료")
            else:
                print(f"실패\n     {r.stderr.decode()[:200]}")


def install_playwright():
    print("\n[ Playwright 브라우저 설치 ]")
    try:
        import playwright
        print("  📦  Playwright 브라우저 설치 중 (처음 실행 시 시간이 걸릴 수 있습니다)...")
        r = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=False
        )
        if r.returncode == 0:
            _ok("Chromium 설치 완료")
        else:
            _warn("Playwright 브라우저 설치 실패 — 브라우저 기능이 제한될 수 있습니다")
    except ImportError:
        _warn("Playwright 미설치 — 브라우저 자동화 기능 비활성")


def create_dirs():
    print("\n[ 디렉토리 초기화 ]")
    dirs = ["config", "memory", "logs"]
    from pathlib import Path
    base = Path(__file__).resolve().parents[1]
    for d in dirs:
        p = base / d
        p.mkdir(exist_ok=True)
        _ok(f"{d}/")

    # long_term.json 초기화
    mem_file = base / "memory" / "long_term.json"
    if not mem_file.exists():
        mem_file.write_text("{}", encoding="utf-8")
        _ok("memory/long_term.json 생성됨")

    # config/api_keys.json 초기화 (OS만)
    cfg_file = base / "config" / "api_keys.json"
    if not cfg_file.exists():
        import json
        os_key = {"Windows": "windows", "Darwin": "mac"}.get(platform.system(), "linux")
        cfg_file.write_text(json.dumps({"os_system": os_key}, indent=4), encoding="utf-8")
        _ok(f"config/api_keys.json 생성됨 (OS: {os_key})")


def main():
    print("=" * 55)
    print("   자비스 (JARVIS) — Claude CLI 기반 AI 어시스턴트")
    print("=" * 55)

    check_only = "--check" in sys.argv

    check_python()
    claude_ok = check_claude_cli()

    if not check_only:
        create_dirs()
        install_packages()
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", str(base)],
            check=False,
        )
        install_playwright()

    print("\n" + "=" * 55)
    if claude_ok:
        print("  ✅  설치 완료! 실행 방법: python main.py")
    else:
        print("  ⚠️  Claude CLI를 먼저 설치하세요:")
        print("      npm install -g @anthropic-ai/claude-code")
        print("      claude   # 최초 로그인")
    print("=" * 55)


if __name__ == "__main__":
    main()
