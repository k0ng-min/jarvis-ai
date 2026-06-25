#computer_settings.py — 자비스 컴퓨터 설정 제어
import json
import re
import subprocess
import sys
import time
import platform
from pathlib import Path

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

_OS = platform.system()


def _get_macos_wifi_interface() -> str:
    try:
        result = subprocess.run(["networksetup", "-listallhardwareports"],
            capture_output=True, text=True, timeout=5)
        lines = result.stdout.splitlines()
        for i, line in enumerate(lines):
            if "Wi-Fi" in line or "AirPort" in line:
                for j in range(i, min(i + 4, len(lines))):
                    if lines[j].startswith("Device:"):
                        return lines[j].split(":", 1)[1].strip()
    except Exception:
        pass
    return "en0"


def volume_up():
    if _OS == "Windows":
        for _ in range(5): pyautogui.press("volumeup")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            "set volume output volume (output volume of (get volume settings) + 10)"], capture_output=True)
    else:
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+10%"], capture_output=True)

def volume_down():
    if _OS == "Windows":
        for _ in range(5): pyautogui.press("volumedown")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            "set volume output volume (output volume of (get volume settings) - 10)"], capture_output=True)
    else:
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-10%"], capture_output=True)

def volume_mute():
    if _OS == "Windows":     pyautogui.press("volumemute")
    elif _OS == "Darwin":    subprocess.run(["osascript", "-e", "set volume with output muted"], capture_output=True)
    else:                    subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"], capture_output=True)

def volume_set(value: int):
    value = max(0, min(100, int(value)))
    if _OS == "Windows":
        try:
            import math
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices   = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol       = cast(interface, POINTER(IAudioEndpointVolume))
            vol_db    = -65.25 if value == 0 else max(-65.25, 20 * math.log10(value / 100))
            vol.SetMasterVolumeLevel(vol_db, None)
        except Exception as e:
            print(f"[Settings] pycaw 실패: {e}")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e", f"set volume output volume {value}"], capture_output=True)
    else:
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{value}%"], capture_output=True)

def brightness_up():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 144'], capture_output=True)
    elif _OS == "Linux":
        subprocess.run(["brightnessctl", "set", "+10%"], capture_output=True)
    else:
        subprocess.run(["powershell", "-Command",
            "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, [math]::Min(100, (Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightness).CurrentBrightness + 10))"],
            capture_output=True, timeout=5)

def brightness_down():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 145'], capture_output=True)
    elif _OS == "Linux":
        subprocess.run(["brightnessctl", "set", "10%-"], capture_output=True)
    else:
        subprocess.run(["powershell", "-Command",
            "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, [math]::Max(0, (Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightness).CurrentBrightness - 10))"],
            capture_output=True, timeout=5)

def close_app():
    if _OS == "Darwin": pyautogui.hotkey("command", "q")
    else:               pyautogui.hotkey("alt", "f4")

def close_window():
    if _OS == "Darwin": pyautogui.hotkey("command", "w")
    else:               pyautogui.hotkey("ctrl", "w")

def full_screen():
    if _OS == "Darwin": pyautogui.hotkey("ctrl", "command", "f")
    else:               pyautogui.press("f11")

def minimize_window():
    if _OS == "Darwin": pyautogui.hotkey("command", "m")
    else:               pyautogui.hotkey("win", "down")

def maximize_window():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e", 'tell application "System Events" to keystroke "f" using {control down, command down}'], capture_output=True)
    elif _OS == "Windows": pyautogui.hotkey("win", "up")
    else:                  pyautogui.hotkey("super", "up")

def snap_left():
    if _OS == "Windows": pyautogui.hotkey("win", "left")

def snap_right():
    if _OS == "Windows": pyautogui.hotkey("win", "right")

def switch_window():
    if _OS == "Darwin": pyautogui.hotkey("command", "tab")
    else:               pyautogui.hotkey("alt", "tab")

def show_desktop():
    if _OS == "Darwin":    pyautogui.hotkey("fn", "f11")
    elif _OS == "Windows": pyautogui.hotkey("win", "d")
    else:                  pyautogui.hotkey("super", "d")

def open_task_manager():
    if _OS == "Windows": pyautogui.hotkey("ctrl", "shift", "esc")
    elif _OS == "Darwin": subprocess.Popen(["open", "-a", "Activity Monitor"])

def refresh_page():
    if _OS == "Darwin": pyautogui.hotkey("command", "r")
    else:               pyautogui.press("f5")

def close_tab():
    if _OS == "Darwin": pyautogui.hotkey("command", "w")
    else:               pyautogui.hotkey("ctrl", "w")

def new_tab():
    if _OS == "Darwin": pyautogui.hotkey("command", "t")
    else:               pyautogui.hotkey("ctrl", "t")

def next_tab():
    if _OS == "Darwin": pyautogui.hotkey("command", "shift", "bracketright")
    else:               pyautogui.hotkey("ctrl", "tab")

def prev_tab():
    if _OS == "Darwin": pyautogui.hotkey("command", "shift", "bracketleft")
    else:               pyautogui.hotkey("ctrl", "shift", "tab")

def go_back():
    if _OS == "Darwin": pyautogui.hotkey("command", "left")
    else:               pyautogui.hotkey("alt", "left")

def go_forward():
    if _OS == "Darwin": pyautogui.hotkey("command", "right")
    else:               pyautogui.hotkey("alt", "right")

def zoom_in():
    if _OS == "Darwin": pyautogui.hotkey("command", "equal")
    else:               pyautogui.hotkey("ctrl", "equal")

def zoom_out():
    if _OS == "Darwin": pyautogui.hotkey("command", "minus")
    else:               pyautogui.hotkey("ctrl", "minus")

def zoom_reset():
    if _OS == "Darwin": pyautogui.hotkey("command", "0")
    else:               pyautogui.hotkey("ctrl", "0")

def find_on_page():
    if _OS == "Darwin": pyautogui.hotkey("command", "f")
    else:               pyautogui.hotkey("ctrl", "f")

def scroll_up(amount: int = 500):  pyautogui.scroll(amount)
def scroll_down(amount: int = 500): pyautogui.scroll(-amount)

def scroll_top():
    if _OS == "Darwin": pyautogui.hotkey("command", "up")
    else:               pyautogui.hotkey("ctrl", "home")

def scroll_bottom():
    if _OS == "Darwin": pyautogui.hotkey("command", "down")
    else:               pyautogui.hotkey("ctrl", "end")

def page_up():   pyautogui.press("pageup")
def page_down(): pyautogui.press("pagedown")

def copy():
    if _OS == "Darwin": pyautogui.hotkey("command", "c")
    else:               pyautogui.hotkey("ctrl", "c")

def paste():
    if _OS == "Darwin": pyautogui.hotkey("command", "v")
    else:               pyautogui.hotkey("ctrl", "v")

def undo():
    if _OS == "Darwin": pyautogui.hotkey("command", "z")
    else:               pyautogui.hotkey("ctrl", "z")

def redo():
    if _OS == "Darwin": pyautogui.hotkey("command", "shift", "z")
    else:               pyautogui.hotkey("ctrl", "y")

def select_all():
    if _OS == "Darwin": pyautogui.hotkey("command", "a")
    else:               pyautogui.hotkey("ctrl", "a")

def save_file():
    if _OS == "Darwin": pyautogui.hotkey("command", "s")
    else:               pyautogui.hotkey("ctrl", "s")

def press_enter():   pyautogui.press("enter")
def press_escape():  pyautogui.press("escape")
def press_key(key: str): pyautogui.press(key)

def type_text(text: str, press_enter_after: bool = False):
    if not text: return
    if _PYPERCLIP:
        pyperclip.copy(str(text))
        time.sleep(0.15)
        paste()
    else:
        pyautogui.write(str(text), interval=0.03)
    if press_enter_after:
        time.sleep(0.1)
        pyautogui.press("enter")

def take_screenshot():
    if _OS == "Windows":  pyautogui.hotkey("win", "shift", "s")
    elif _OS == "Darwin": pyautogui.hotkey("command", "shift", "3")
    else:                 pyautogui.hotkey("ctrl", "print_screen")

def lock_screen():
    if _OS == "Windows":  pyautogui.hotkey("win", "l")
    elif _OS == "Darwin": subprocess.run(["pmset", "displaysleepnow"], capture_output=True)

def sleep_display():
    if _OS == "Windows":
        try:
            import ctypes
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
        except Exception: pass
    elif _OS == "Darwin":
        subprocess.run(["pmset", "displaysleepnow"], capture_output=True)

def dark_mode():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell app "System Events" to tell appearance preferences to set dark mode to not dark mode'],
            capture_output=True)
    elif _OS == "Windows":
        try:
            import winreg
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            current, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, 1 - current)
            winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, 1 - current)
            winreg.CloseKey(key)
        except Exception as e:
            print(f"[Settings] 다크모드 전환 실패: {e}")

def toggle_wifi():
    if _OS == "Darwin":
        iface = _get_macos_wifi_interface()
        result = subprocess.run(["networksetup", "-getairportpower", iface], capture_output=True, text=True)
        state  = "off" if "On" in result.stdout else "on"
        subprocess.run(["networksetup", "-setairportpower", iface, state], capture_output=True)
    elif _OS == "Windows":
        subprocess.run(["powershell", "-Command",
            "$a = Get-NetAdapter | Where-Object {$_.PhysicalMediaType -eq 'Native 802.11'};"
            "if ($a.Status -eq 'Up') { Disable-NetAdapter -Name $a.Name -Confirm:$false }"
            "else { Enable-NetAdapter -Name $a.Name -Confirm:$false }"],
            capture_output=True, timeout=10)
    else:
        result = subprocess.run(["nmcli", "radio", "wifi"], capture_output=True, text=True)
        state  = "off" if "enabled" in result.stdout else "on"
        subprocess.run(["nmcli", "radio", "wifi", state], capture_output=True)

def restart_computer():
    if _OS == "Windows":  subprocess.run(["shutdown", "/r", "/t", "10"], capture_output=True)
    elif _OS == "Darwin": subprocess.run(["osascript", "-e", 'tell application "System Events" to restart'], capture_output=True)
    else:                 subprocess.run(["systemctl", "reboot"], capture_output=True)

def shutdown_computer():
    if _OS == "Windows":  subprocess.run(["shutdown", "/s", "/t", "10"], capture_output=True)
    elif _OS == "Darwin": subprocess.run(["osascript", "-e", 'tell application "System Events" to shut down'], capture_output=True)
    else:                 subprocess.run(["systemctl", "poweroff"], capture_output=True)

def pause_video():  pyautogui.press("space")
def focus_search():
    if _OS == "Darwin": pyautogui.hotkey("command", "l")
    else:               pyautogui.hotkey("ctrl", "l")
def reload_page_n(n: int):
    for _ in range(max(1, n)):
        refresh_page()
        time.sleep(0.8)
def open_file_explorer():
    if _OS == "Windows":  pyautogui.hotkey("win", "e")
    elif _OS == "Darwin": subprocess.Popen(["open", str(Path.home())])
def open_system_settings():
    if _OS == "Windows":  pyautogui.hotkey("win", "i")
    elif _OS == "Darwin": subprocess.Popen(["open", "-a", "System Preferences"])
def open_run():
    if _OS == "Windows": pyautogui.hotkey("win", "r")

ACTION_MAP: dict = {
    "volume_up": volume_up, "volume_down": volume_down,
    "mute": volume_mute, "unmute": volume_mute, "toggle_mute": volume_mute,
    "brightness_up": brightness_up, "brightness_down": brightness_down,
    "sleep_display": sleep_display, "screen_off": sleep_display,
    "pause_video": pause_video, "play_pause": pause_video,
    "close_app": close_app, "close_window": close_window,
    "full_screen": full_screen, "fullscreen": full_screen,
    "minimize": minimize_window, "maximize": maximize_window,
    "snap_left": snap_left, "snap_right": snap_right,
    "switch_window": switch_window, "show_desktop": show_desktop,
    "task_manager": open_task_manager, "focus_search": focus_search,
    "refresh_page": refresh_page, "reload": refresh_page,
    "close_tab": close_tab, "new_tab": new_tab,
    "next_tab": next_tab, "prev_tab": prev_tab,
    "go_back": go_back, "go_forward": go_forward,
    "zoom_in": zoom_in, "zoom_out": zoom_out, "zoom_reset": zoom_reset,
    "find_on_page": find_on_page,
    "scroll_up": scroll_up, "scroll_down": scroll_down,
    "scroll_top": scroll_top, "scroll_bottom": scroll_bottom,
    "page_up": page_up, "page_down": page_down,
    "copy": copy, "paste": paste, "undo": undo, "redo": redo,
    "select_all": select_all, "save": save_file,
    "enter": press_enter, "escape": press_escape,
    "screenshot": take_screenshot, "lock_screen": lock_screen,
    "open_settings": open_system_settings, "file_explorer": open_file_explorer,
    "open_run": open_run, "dark_mode": dark_mode,
    "toggle_wifi": toggle_wifi, "restart": restart_computer, "shutdown": shutdown_computer,
}

_DANGEROUS_ACTIONS = {"restart", "shutdown"}


def _detect_action_with_claude(description: str) -> dict:
    """Claude CLI로 자연어 명령어를 액션으로 변환"""
    available = ", ".join(sorted(ACTION_MAP.keys())) + ", volume_set, type_text, press_key, reload_n"
    prompt = (
        f'사용자 명령: "{description}"\n'
        f'사용 가능한 액션 목록: {available}\n'
        f'반드시 JSON만 반환: {{"action": "액션명", "value": null_or_값}}\n'
        f'규칙:\n'
        f'- volume_set: 0-100 정수\n'
        f'- type_text: 타이핑할 텍스트\n'
        f'- press_key: 키 이름 (예: f5, tab, enter)\n'
        f'JSON만 반환, 설명 없음.'
    )
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=30, encoding="utf-8"
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            raw  = data.get("result", "{}").strip()
            raw  = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
            return json.loads(raw)
    except Exception as e:
        print(f"[Settings] Claude 의도 감지 실패: {e}")
    return {"action": description.lower().replace(" ", "_"), "value": None}


def computer_settings(parameters: dict = None, response=None, player=None, session_memory=None) -> str:
    if not _PYAUTOGUI:
        return "pyautogui가 설치되지 않았습니다. pip install pyautogui"

    params      = parameters or {}
    raw_action  = params.get("action", "").strip()
    description = params.get("description", "").strip()
    value       = params.get("value", None)

    if not raw_action and description:
        detected   = _detect_action_with_claude(description)
        raw_action = detected.get("action", "")
        if value is None:
            value = detected.get("value")

    action = raw_action.lower().strip().replace(" ", "_").replace("-", "_")

    if not action:
        return "어떤 동작을 할지 알 수 없습니다."

    print(f"[Settings] 액션: {action}  값: {value}  OS: {_OS}")
    if player:
        player.write_log(f"[설정] {action}")

    if action in _DANGEROUS_ACTIONS:
        confirmed = str(params.get("confirmed", "")).lower()
        if confirmed not in ("yes", "true", "1", "confirm"):
            return f"컴퓨터를 {action}하려 합니다. confirmed=yes 로 다시 호출하면 실행됩니다."

    if action == "volume_set":
        try:
            volume_set(int(value or 50))
            return f"볼륨을 {value}%로 설정했습니다."
        except Exception as e:
            return f"볼륨 설정 실패: {e}"

    if action in ("type_text", "write_on_screen", "type", "write"):
        text = str(value or params.get("text", "")).strip()
        if not text:
            return "타이핑할 텍스트가 없습니다."
        enter_after = str(params.get("press_enter", "false")).lower() in ("true", "1", "yes")
        type_text(text, press_enter_after=enter_after)
        return f"입력 완료: {text[:80]}"

    if action == "press_key":
        key = str(value or params.get("key", "")).strip()
        if not key:
            return "키를 지정해주세요."
        press_key(key)
        return f"키 입력: {key}"

    if action in ("reload_n", "refresh_n", "reload_page_n"):
        try:
            reload_page_n(int(value or 1))
            return f"{value or 1}회 새로고침 완료."
        except Exception as e:
            return f"새로고침 실패: {e}"

    if action == "scroll_up":
        scroll_up(int(value or 500))
        return "위로 스크롤했습니다."

    if action == "scroll_down":
        scroll_down(int(value or 500))
        return "아래로 스크롤했습니다."

    func = ACTION_MAP.get(action)
    if not func:
        return f"알 수 없는 액션: '{raw_action}'"

    try:
        func()
        return f"완료: {action}"
    except Exception as e:
        print(f"[Settings] 액션 실패 ({action}): {e}")
        return f"실행 실패 ({action}): {e}"
