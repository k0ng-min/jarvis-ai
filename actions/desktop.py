# actions/desktop.py — 자비스 바탕화면 제어

import json
import os
import shutil
import subprocess
import tempfile
import platform
from pathlib import Path
from datetime import datetime

try:
    import pyautogui
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

_OS = platform.system()


def _get_desktop() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DESKTOP_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Desktop"


def _ask_claude_for_desktop_action(task: str) -> str:
    """Claude CLI로 바탕화면 작업 코드 생성"""
    desktop = str(_get_desktop())
    prompt = (
        f"현재 OS: {_OS}, 바탕화면 경로: {desktop}\n"
        f"다음 작업을 수행하는 안전한 Python 코드를 작성하세요:\n{task}\n\n"
        f"허용 모듈: pyautogui, pathlib.Path, shutil(copy/copy2만), os.path\n"
        f"파일 삭제, subprocess, exec/eval 금지.\n"
        f"코드만 출력, 설명 없음."
    )
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=45, encoding="utf-8"
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            return data.get("result", "").strip()
    except Exception as e:
        print(f"[Desktop] Claude 오류: {e}")
    return "UNSAFE"


def _execute_generated_code(code: str, player=None) -> str:
    if not code or code.strip() == "UNSAFE":
        return "이 작업은 안전하게 수행할 수 없습니다."

    code = code.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        code  = "\n".join(lines[1:-1]).strip()

    import time
    sandbox = {
        "__builtins__": {
            "print": print, "len": len, "str": str, "int": int,
            "float": float, "bool": bool, "list": list, "dict": dict,
            "range": range, "enumerate": enumerate, "sorted": sorted,
            "isinstance": isinstance, "max": max, "min": min, "sum": sum,
        },
        "Path": Path, "time": time,
        "shutil": type("shutil", (), {
            "copy2": shutil.copy2,
            "copytree": shutil.copytree,
            "disk_usage": shutil.disk_usage,
        })(),
    }
    if _PYAUTOGUI:
        sandbox["pyautogui"] = pyautogui

    output_lines = []
    sandbox["__builtins__"]["print"] = lambda *a: output_lines.append(" ".join(str(x) for x in a))

    try:
        exec(compile(code, "<jarvis_desktop>", "exec"), sandbox)
        return "\n".join(output_lines) if output_lines else "완료"
    except Exception as e:
        print(f"[Desktop] 실행 오류: {e}")
        return f"실행 오류: {e}"


def set_wallpaper(image_path: str) -> str:
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        return f"이미지를 찾을 수 없습니다: {image_path}"

    try:
        if _OS == "Windows":
            import ctypes
            if path.suffix.lower() in {".webp", ".png"}:
                try:
                    from PIL import Image
                    bmp_path = Path(tempfile.mktemp(suffix=".bmp"))
                    Image.open(path).convert("RGB").save(bmp_path, "BMP")
                    path = bmp_path
                except ImportError:
                    pass
            ctypes.windll.user32.SystemParametersInfoW(20, 0, str(path), 3)
            return f"배경화면이 설정되었습니다: {path.name}"
        elif _OS == "Darwin":
            script = f'tell application "System Events" to tell every desktop to set picture to POSIX file "{path}"'
            subprocess.run(["osascript", "-e", script], capture_output=True)
            return f"배경화면이 설정되었습니다: {path.name}"
        else:
            subprocess.run(["feh", "--bg-scale", str(path)], capture_output=True)
            return f"배경화면이 설정되었습니다: {path.name}"
    except Exception as e:
        return f"배경화면 설정 실패: {e}"


def set_wallpaper_from_url(url: str) -> str:
    try:
        import urllib.request
        suffix = Path(url.split("?")[0]).suffix or ".jpg"
        tmp    = Path(tempfile.mktemp(suffix=suffix))
        urllib.request.urlretrieve(url, str(tmp))
        result = set_wallpaper(str(tmp))
        try: tmp.unlink()
        except: pass
        return result
    except Exception as e:
        return f"이미지 다운로드 실패: {e}"


FILE_TYPE_MAP = {
    "이미지":   {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"},
    "문서":     {".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx", ".ppt", ".pptx", ".csv"},
    "동영상":   {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"},
    "음악":     {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma"},
    "압축파일": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "코드":     {".py", ".js", ".ts", ".html", ".css", ".json", ".xml", ".cpp", ".java"},
}


def organize_desktop(mode: str = "by_type") -> str:
    desktop = _get_desktop()
    moved, skipped = [], []

    for item in desktop.iterdir():
        if item.is_dir() or item.name.startswith("."):
            continue
        if item.suffix.lower() in {".lnk", ".url"}:
            continue

        if mode == "by_date":
            mtime       = datetime.fromtimestamp(item.stat().st_mtime)
            folder_name = mtime.strftime("%Y-%m")
        else:
            ext = item.suffix.lower()
            folder_name = "기타"
            for folder, exts in FILE_TYPE_MAP.items():
                if ext in exts:
                    folder_name = folder
                    break

        target_dir = desktop / folder_name
        target_dir.mkdir(exist_ok=True)
        new_path = target_dir / item.name

        if new_path.exists():
            skipped.append(item.name)
            continue

        shutil.move(str(item), str(new_path))
        moved.append(f"{item.name} → {folder_name}/")

    result = f"바탕화면 정리 완료: {len(moved)}개 파일 이동"
    if moved:
        result += "\n" + "\n".join(moved[:8])
        if len(moved) > 8:
            result += f"\n... 외 {len(moved) - 8}개"
    if skipped:
        result += f"\n{len(skipped)}개 건너뜀 (이름 충돌)"
    return result


def list_desktop() -> str:
    desktop = _get_desktop()
    items   = []
    for item in sorted(desktop.iterdir()):
        if item.name.startswith("."): continue
        if item.is_dir():
            try: count = len(list(item.iterdir()))
            except: count = "?"
            items.append(f"📁 {item.name}/ ({count}개)")
        else:
            size = item.stat().st_size
            size_str = f"{size/1024:.1f}KB" if size < 1024*1024 else f"{size/1024/1024:.1f}MB"
            items.append(f"📄 {item.name} ({size_str})")

    if not items:
        return "바탕화면이 비어있습니다."
    return f"바탕화면 ({len(items)}개):\n" + "\n".join(items)


def clean_desktop() -> str:
    desktop     = _get_desktop()
    today       = datetime.now().strftime("%Y-%m-%d")
    archive_dir = desktop / f"바탕화면 보관 {today}"
    archive_dir.mkdir(exist_ok=True)
    moved = 0
    for item in desktop.iterdir():
        if item.is_dir() or item.name.startswith("."): continue
        if item.suffix.lower() in {".lnk", ".url"}: continue
        new_path = archive_dir / item.name
        if not new_path.exists():
            shutil.move(str(item), str(new_path))
            moved += 1
    return f"바탕화면 정리 완료: {moved}개 파일을 '{archive_dir.name}'에 보관했습니다."


def get_desktop_stats() -> str:
    desktop    = _get_desktop()
    files      = [i for i in desktop.iterdir() if i.is_file()]
    folders    = [i for i in desktop.iterdir() if i.is_dir()]
    total_size = sum(f.stat().st_size for f in files if f.exists())
    size_str   = f"{total_size/1024:.1f}KB" if total_size < 1024*1024 else f"{total_size/1024/1024:.1f}MB"
    return (
        f"바탕화면 통계:\n"
        f"  파일: {len(files)}개\n"
        f"  폴더: {len(folders)}개\n"
        f"  크기: {size_str}\n"
        f"  경로: {desktop}"
    )


def desktop_control(parameters: dict = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = params.get("action", "").lower().strip()
    task   = params.get("task", "").strip()

    if player:
        player.write_log(f"[바탕화면] {action or task[:40]}")

    try:
        if action == "wallpaper":
            return set_wallpaper(params.get("path", ""))
        elif action == "wallpaper_url":
            return set_wallpaper_from_url(params.get("url", ""))
        elif action == "organize":
            return organize_desktop(params.get("mode", "by_type"))
        elif action == "clean":
            return clean_desktop()
        elif action == "list":
            return list_desktop()
        elif action == "stats":
            return get_desktop_stats()
        elif action == "task" or task:
            actual_task = task or params.get("description", "")
            if not actual_task:
                return "어떤 바탕화면 작업을 원하는지 설명해주세요."
            code = _ask_claude_for_desktop_action(actual_task)
            return _execute_generated_code(code, player=player)
        else:
            if action:
                code = _ask_claude_for_desktop_action(action)
                return _execute_generated_code(code, player=player)
            return "액션 또는 작업을 지정해주세요."
    except Exception as e:
        print(f"[Desktop] 오류: {e}")
        return f"바탕화면 제어 오류: {e}"
