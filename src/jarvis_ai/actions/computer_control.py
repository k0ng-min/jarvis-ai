# actions/computer_control.py — 자비스 컴퓨터 제어

import io
import json
import re
import string
import subprocess
import sys
import time
import random
import tempfile
import os
from pathlib import Path

from ..paths import PROJECT_ROOT

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.05
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False


def _base_dir() -> Path:
    return PROJECT_ROOT


_BASE        = _base_dir()
_MEMORY_PATH = _BASE / "memory" / "long_term.json"

_SAFE_SCREENSHOT_ROOTS = (Path.home(),)


def _safe_screenshot_path(requested: str | None) -> Path:
    fallback = Path.home() / "Desktop" / "jarvis_screenshot.png"
    if not requested:
        return fallback
    try:
        p = Path(requested).expanduser().resolve()
        for root in _SAFE_SCREENSHOT_ROOTS:
            if p.is_relative_to(root.resolve()):
                p.parent.mkdir(parents=True, exist_ok=True)
                return p
    except Exception:
        pass
    return fallback


def _require_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI가 설치되지 않았습니다. 실행: pip install pyautogui")


_FIRST_NAMES = ["Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Drew", "Quinn",
                "Avery", "Blake", "Cameron", "Dakota", "Emerson", "Finley", "Harper"]
_LAST_NAMES  = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
                "Davis", "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson"]
_DOMAINS     = ["gmail.com", "yahoo.com", "outlook.com", "proton.me", "mail.com"]


def _random_data(data_type: str) -> str:
    dt = data_type.lower().strip()
    if dt == "first_name":   return random.choice(_FIRST_NAMES)
    if dt == "last_name":    return random.choice(_LAST_NAMES)
    if dt == "name":         return f"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}"
    if dt == "email":
        first = random.choice(_FIRST_NAMES).lower()
        last  = random.choice(_LAST_NAMES).lower()
        num   = random.randint(10, 999)
        return f"{first}.{last}{num}@{random.choice(_DOMAINS)}"
    if dt == "username":  return f"{random.choice(_FIRST_NAMES).lower()}{random.randint(100, 9999)}"
    if dt == "password":
        chars = string.ascii_letters + string.digits + "!@#$%"
        raw   = (random.choice(string.ascii_uppercase) + random.choice(string.digits)
                 + random.choice("!@#$%") + "".join(random.choices(chars, k=9)))
        return "".join(random.sample(raw, len(raw)))
    if dt == "phone":    return f"+82{random.randint(1000000000, 9999999999)}"
    if dt == "birthday":
        y = random.randint(1980, 2000)
        m = random.randint(1, 12)
        d = random.randint(1, 28)
        return f"{y}-{m:02d}-{d:02d}"
    if dt == "address":
        num    = random.randint(100, 9999)
        street = random.choice(["서울시 강남구", "서울시 마포구", "서울시 종로구", "부산시 해운대구"])
        return f"{street} {num}"
    if dt == "zip_code": return str(random.randint(10000, 99999))
    if dt == "city":     return random.choice(["서울", "부산", "대구", "인천", "광주", "대전"])
    return f"random_{data_type}_{random.randint(1000, 9999)}"


def _user_profile() -> dict:
    try:
        if _MEMORY_PATH.exists():
            data     = json.loads(_MEMORY_PATH.read_text(encoding="utf-8"))
            identity = data.get("identity", {})
            return {k: v.get("value", "") for k, v in identity.items()}
    except Exception:
        pass
    return {}


def _type(text: str, interval: float = 0.03) -> str:
    _require_pyautogui()
    time.sleep(0.3)
    pyautogui.typewrite(text, interval=interval)
    return f"입력됨: {text[:60]}{'…' if len(text) > 60 else ''}"


def _smart_type(text: str, clear_first: bool = True) -> str:
    _require_pyautogui()
    if clear_first:
        _clear_field()
        time.sleep(0.1)
    if len(text) > 20 and _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "v")
        return f"스마트 입력 (클립보드): {text[:60]}{'…' if len(text) > 60 else ''}"
    pyautogui.typewrite(text, interval=0.04)
    return f"스마트 입력: {text[:60]}{'…' if len(text) > 60 else ''}"


def _click(x=None, y=None, button: str = "left", clicks: int = 1) -> str:
    _require_pyautogui()
    if x is not None and y is not None:
        pyautogui.click(x, y, button=button, clicks=clicks)
        return f"{'더블' if clicks == 2 else ''}클릭 ({x}, {y}) [{button}]"
    pyautogui.click(button=button, clicks=clicks)
    return f"현재 위치 클릭 [{button}]"


def _hotkey(*keys) -> str:
    _require_pyautogui()
    pyautogui.hotkey(*keys)
    return f"단축키: {'+'.join(keys)}"


def _press(key: str) -> str:
    _require_pyautogui()
    pyautogui.press(key)
    return f"키 입력: {key}"


def _scroll(direction: str = "down", amount: int = 3) -> str:
    _require_pyautogui()
    vertical = direction in ("up", "down")
    clicks   = amount if direction in ("up", "right") else -amount
    pyautogui.scroll(clicks) if vertical else pyautogui.hscroll(clicks)
    return f"{direction} 스크롤 ×{amount}"


def _move(x: int, y: int, duration: float = 0.3) -> str:
    _require_pyautogui()
    pyautogui.moveTo(x, y, duration=duration)
    return f"마우스 → ({x}, {y})"


def _drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> str:
    _require_pyautogui()
    pyautogui.moveTo(x1, y1, duration=0.2)
    pyautogui.dragTo(x2, y2, duration=duration, button="left")
    return f"드래그 ({x1},{y1}) → ({x2},{y2})"


def _clipboard_get() -> str:
    if _PYPERCLIP:
        return pyperclip.paste()
    _hotkey("ctrl", "c")
    time.sleep(0.2)
    return "(복사됨 — pyperclip 없이는 읽기 불가)"


def _clipboard_paste(text: str) -> str:
    if _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.1)
        _require_pyautogui()
        pyautogui.hotkey("ctrl", "v")
        return f"붙여넣기: {text[:60]}{'…' if len(text) > 60 else ''}"
    return "pyperclip이 없습니다"


def _screenshot(save_path: str | None = None) -> str:
    _require_pyautogui()
    path = _safe_screenshot_path(save_path)
    img  = pyautogui.screenshot()
    img.save(str(path))
    return f"스크린샷 저장됨: {path}"


def _clear_field() -> str:
    _require_pyautogui()
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.press("delete")
    return "필드 지워짐"


def _focus_window(title: str) -> str:
    import platform
    os_name = platform.system().lower()

    if os_name == "windows":
        try:
            script = f'(New-Object -ComObject WScript.Shell).AppActivate("{title}")'
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, timeout=5,
            )
            time.sleep(0.3)
            return f"창 포커스: {title}"
        except Exception as e:
            return f"focus_window (Windows) 실패: {e}"

    if os_name == "darwin":
        script = (f'tell application "System Events" to '
                  f'set frontmost of (first process whose name contains "{title}") to true')
        try:
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
            time.sleep(0.3)
            return f"창 포커스: {title}"
        except Exception as e:
            return f"focus_window (macOS) 실패: {e}"

    return f"focus_window: 지원하지 않는 OS"


def _screen_find(description: str) -> tuple[int, int] | None:
    """Claude CLI를 사용하여 화면에서 UI 요소를 찾습니다."""
    try:
        import PIL.Image
        _require_pyautogui()
        w, h  = pyautogui.size()
        img   = pyautogui.screenshot()
        buf   = io.BytesIO()
        img.save(buf, format="PNG")
        img_bytes = buf.getvalue()

        # 임시 파일로 저장
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(img_bytes)
            tmp_path = tmp.name

        prompt = (
            f"이것은 {w}×{h} 픽셀 화면의 스크린샷입니다 (파일: {tmp_path}).\n"
            f"UI 요소를 찾으세요: '{description}'\n"
            f"중심 좌표만 'x,y' 형식으로 답하거나 찾을 수 없으면 'NOT_FOUND'라고 답하세요."
        )

        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=30, encoding="utf-8"
        )

        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            text = data.get("result", "")
            if "NOT_FOUND" in text.upper():
                return None
            match = re.search(r"(\d+)\s*,\s*(\d+)", text)
            if match:
                return int(match.group(1)), int(match.group(2))
    except Exception as e:
        print(f"[컴퓨터제어] ⚠️ screen_find 실패: {e}")
    return None


def computer_control(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    컴퓨터 제어 액션 디스패처.

    파라미터 (모두 선택):
      action      : (필수) 아래 액션 중 하나
      text        : 입력하거나 붙여넣을 텍스트
      x, y        : 화면 좌표
      button      : 'left' | 'right' (기본: left)
      keys        : 단축키 문자열 (예: 'ctrl+c')
      key         : 단일 키 이름 (예: 'enter')
      direction   : 'up' | 'down' | 'left' | 'right'
      amount      : 스크롤 양 (기본: 3)
      seconds     : 대기 시간
      title       : focus_window용 창 제목
      description : screen_find/screen_click용 자연어 요소 설명
      type        : random_data용 데이터 타입
      field       : user_data용 메모리 필드 이름
      clear_first : 입력 전 필드 지우기 (기본: true)
      path        : 스크린샷 저장 경로 (홈 디렉토리 내)

    액션:
      type, smart_type, click, double_click, right_click, move, drag,
      hotkey, press, scroll, copy, paste, screenshot, wait, clear_field,
      focus_window, screen_find, screen_click, random_data, user_data
    """
    params = parameters or {}
    action = params.get("action", "").lower().strip()

    if not action:
        return "computer_control에 액션이 지정되지 않았습니다."

    if player:
        player.write_log(f"[컴퓨터] {action}")

    print(f"[컴퓨터제어] ▶ {action}  {params}")

    try:
        if action == "type":
            return _type(params.get("text", ""))

        if action == "smart_type":
            return _smart_type(params.get("text", ""), clear_first=params.get("clear_first", True))

        if action in ("click", "left_click"):
            return _click(params.get("x"), params.get("y"), "left", 1)

        if action == "double_click":
            return _click(params.get("x"), params.get("y"), "left", 2)

        if action == "right_click":
            return _click(params.get("x"), params.get("y"), "right", 1)

        if action == "move":
            return _move(int(params.get("x", 0)), int(params.get("y", 0)))

        if action == "drag":
            return _drag(int(params.get("x1", 0)), int(params.get("y1", 0)),
                         int(params.get("x2", 0)), int(params.get("y2", 0)))

        if action == "hotkey":
            raw  = params.get("keys", "")
            keys = [k.strip() for k in raw.split("+")] if isinstance(raw, str) else raw
            return _hotkey(*keys)

        if action == "press":
            return _press(params.get("key", "enter"))

        if action == "scroll":
            return _scroll(direction=params.get("direction", "down"),
                           amount=int(params.get("amount", 3)))

        if action == "copy":
            return _clipboard_get()

        if action == "paste":
            return _clipboard_paste(params.get("text", ""))

        if action == "screenshot":
            return _screenshot(params.get("path"))

        if action == "screen_find":
            coords = _screen_find(params.get("description", ""))
            return f"{coords[0]},{coords[1]}" if coords else "NOT_FOUND"

        if action == "screen_click":
            desc   = params.get("description", "")
            coords = _screen_find(desc)
            if coords:
                time.sleep(0.2)
                _click(x=coords[0], y=coords[1])
                return f"'{desc}' 클릭됨 ({coords})"
            return f"화면에서 요소를 찾을 수 없습니다: '{desc}'"

        if action == "wait":
            secs = float(params.get("seconds", 1.0))
            secs = min(secs, 30.0)
            time.sleep(secs)
            return f"{secs}초 대기됨"

        if action == "clear_field":
            return _clear_field()

        if action == "focus_window":
            return _focus_window(params.get("title", ""))

        if action == "random_data":
            dt     = params.get("type", "name")
            result = _random_data(dt)
            print(f"[컴퓨터제어] 🎲 랜덤 {dt} → {result}")
            return result

        if action == "user_data":
            field   = params.get("field", "name")
            profile = _user_profile()
            value   = profile.get(field, "")
            if not value:
                value = _random_data(field)
                print(f"[컴퓨터제어] ⚠️ 메모리에 '{field}' 없음, 랜덤 사용: {value}")
            return value

        return f"알 수 없는 액션: '{action}'"

    except Exception as e:
        print(f"[컴퓨터제어] ❌ {action}: {e}")
        return f"computer_control '{action}' 실패: {e}"
