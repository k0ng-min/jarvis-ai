import os
import re
import sys
import json
import time
import subprocess
import threading
import winreg
from pathlib import Path
from datetime import datetime


def _find_steam_path() -> Path | None:
    registry_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
        (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Valve\Steam"),
    ]
    for hive, key_path in registry_keys:
        try:
            key = winreg.OpenKey(hive, key_path)
            val, _ = winreg.QueryValueEx(key, "InstallPath")
            winreg.CloseKey(key)
            p = Path(val)
            if p.exists() and (p / "steam.exe").exists():
                return p
        except Exception:
            continue
    for p in [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Steam",
        Path(os.environ.get("ProgramFiles", "")) / "Steam",
        Path("C:/Steam"), Path("D:/Steam"), Path("E:/Steam"), Path("F:/Steam"),
    ]:
        if p.exists() and (p / "steam.exe").exists():
            return p
    return None


def _find_epic_path() -> Path | None:
    registry_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\EpicGames\EpicGamesLauncher"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\EpicGames\EpicGamesLauncher"),
        (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\EpicGames\EpicGamesLauncher"),
    ]
    for hive, key_path in registry_keys:
        try:
            key = winreg.OpenKey(hive, key_path)
            val, _ = winreg.QueryValueEx(key, "AppDataPath")
            winreg.CloseKey(key)
            exe = Path(val) / "Binaries" / "Win64" / "EpicGamesLauncher.exe"
            if exe.exists():
                return exe.parent
        except Exception:
            continue
    for p in [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Epic Games" / "Launcher" / "Portal" / "Binaries" / "Win64",
        Path(os.environ.get("ProgramFiles", "")) / "Epic Games" / "Launcher" / "Portal" / "Binaries" / "Win64",
        Path(os.environ.get("LOCALAPPDATA", "")) / "EpicGamesLauncher" / "Portal" / "Binaries" / "Win64",
    ]:
        if p.exists() and (p / "EpicGamesLauncher.exe").exists():
            return p
    return None


def _get_steam_libraries(steam_path: Path) -> list[Path]:
    libraries = [steam_path / "steamapps"]
    vdf_path  = steam_path / "steamapps" / "libraryfolders.vdf"
    if not vdf_path.exists():
        return libraries
    try:
        content = vdf_path.read_text(encoding="utf-8", errors="ignore")
        for raw_path in re.findall(r'"path"\s+"([^"]+)"', content):
            lib = Path(raw_path.replace("\\\\", "/")) / "steamapps"
            if lib.exists() and lib not in libraries:
                libraries.append(lib)
    except Exception:
        pass
    return libraries


def _get_steam_games(steam_path: Path) -> list[dict]:
    games = []
    for lib in _get_steam_libraries(steam_path):
        for acf in lib.glob("appmanifest_*.acf"):
            try:
                content = acf.read_text(encoding="utf-8", errors="ignore")
                app_id  = re.search(r'"appid"\s+"(\d+)"',     content)
                name    = re.search(r'"name"\s+"([^"]+)"',     content)
                state   = re.search(r'"StateFlags"\s+"(\d+)"', content)
                size    = re.search(r'"SizeOnDisk"\s+"(\d+)"', content)
                if app_id and name:
                    games.append({
                        "id":    app_id.group(1),
                        "name":  name.group(1),
                        "state": int(state.group(1)) if state else 0,
                        "size":  int(size.group(1))  if size  else 0,
                        "lib":   str(lib),
                    })
            except Exception:
                continue
    return games


def _is_steam_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq steam.exe"],
                             capture_output=True, text=True).stdout
        return "steam.exe" in out.lower()
    except Exception:
        return False


def _get_steam_window_rect() -> tuple[int, int, int, int] | None:
    try:
        import pygetwindow as gw
        for w in gw.getAllWindows():
            if "steam" in w.title.lower() and w.width > 200 and w.visible:
                return w.left, w.top, w.width, w.height
    except Exception:
        pass
    return None


def _click_first_profile_by_screenshot() -> bool:
    try:
        import pyautogui
        import numpy as np

        time.sleep(1.5)

        win = _get_steam_window_rect()
        if not win:
            print("[게임업데이터] ⚠️ Steam 창을 찾을 수 없습니다")
            return False

        wx, wy, ww, wh = win
        screenshot = pyautogui.screenshot(region=(wx, wy, ww, wh))
        img        = np.array(screenshot)

        h, w = img.shape[:2]

        search_y1 = h // 3
        search_y2 = h * 3 // 4
        search_x1 = w // 5
        search_x2 = w * 4 // 5
        region = img[search_y1:search_y2, search_x1:search_x2]

        r = region[:, :, 0].astype(int)
        g = region[:, :, 1].astype(int)
        b = region[:, :, 2].astype(int)

        max_c = np.maximum(np.maximum(r, g), b)
        min_c = np.minimum(np.minimum(r, g), b)
        sat   = max_c - min_c

        colorful = (max_c > 60) & (sat > 40)

        if not colorful.any():
            print("[게임업데이터] ⚠️ 컬러풀한 아바타 영역 없음 — 중앙 왼쪽 클릭")
            pyautogui.click(wx + ww // 2 - ww // 6, wy + wh // 2)
            return True

        cols = np.where(colorful.any(axis=0))[0]
        rows = np.where(colorful.any(axis=1))[0]

        if len(cols) == 0 or len(rows) == 0:
            return False

        avatar_w  = min(90, (region.shape[1]) // 4)
        first_col = int(cols[0])
        block_cols = cols[cols < first_col + avatar_w]

        center_x_local = int(block_cols.mean())
        center_y_local = int(rows.mean())

        abs_x = wx + search_x1 + center_x_local
        abs_y = wy + search_y1 + center_y_local

        print(f"[게임업데이터] 🎯 첫 번째 프로필 아바타 ({abs_x}, {abs_y}) — 클릭")
        pyautogui.click(abs_x, abs_y)
        return True

    except ImportError as e:
        print(f"[게임업데이터] ⚠️ 라이브러리 없음: {e}")
        return False
    except Exception as e:
        print(f"[게임업데이터] ⚠️ 스크린샷 프로필 감지 실패: {e}")
        return False


def _handle_steam_profile_selection() -> bool:
    print("[게임업데이터] 🔍 '누가 플레이하나요?' 대화상자 확인 중...")

    win = _get_steam_window_rect()
    if not win:
        return False

    wx, wy, ww, wh = win

    try:
        import pyautogui
        import numpy as np

        screenshot = pyautogui.screenshot(region=(wx, wy, ww, wh))
        img        = np.array(screenshot)

        is_small_window = ww < 900 and wh < 700

        top_region   = img[:wh // 3, :, :]
        white_pixels = int(np.sum(
            (top_region[:, :, 0] > 200) &
            (top_region[:, :, 1] > 200) &
            (top_region[:, :, 2] > 200)
        ))
        has_white_text = white_pixels > 100

        if not is_small_window and not has_white_text:
            print("[게임업데이터] ℹ️ 프로필 대화상자 없음 — Steam 이미 로그인됨")
            return False

    except ImportError:
        pass
    except Exception:
        pass

    print("[게임업데이터] 👤 프로필 선택 감지됨 — 첫 번째 프로필 클릭")
    return _click_first_profile_by_screenshot()


def _ensure_steam_running(steam_path: Path) -> bool:
    if _is_steam_running():
        return True

    steam_exe = steam_path / "steam.exe"
    if not steam_exe.exists():
        print("[게임업데이터] ❌ steam.exe를 찾을 수 없습니다")
        return False

    print("[게임업데이터] 🚀 Steam 시작 중...")
    subprocess.Popen([str(steam_exe)])

    for _ in range(20):
        time.sleep(1)
        if _is_steam_running():
            print("[게임업데이터] ✅ Steam 실행 중")
            time.sleep(4)
            _handle_steam_profile_selection()
            time.sleep(2)
            return True

    print("[게임업데이터] ⚠️ Steam이 제 시간에 시작되지 않았습니다")
    return False


def _update_steam_games(steam_path: Path, game_name: str = None) -> str:
    if not _ensure_steam_running(steam_path):
        return "Steam을 시작할 수 없습니다."

    steam_exe = steam_path / "steam.exe"
    games     = _get_steam_games(steam_path)

    if not games:
        return "Steam 게임을 찾을 수 없습니다."

    if game_name:
        name_lower = game_name.lower()
        matched    = [g for g in games if name_lower in g["name"].lower()]
        if not matched:
            available = ", ".join(g["name"] for g in games[:5])
            return f"'{game_name}' 게임을 찾을 수 없습니다. 설치된 게임: {available}..."
        targets = matched
    else:
        targets = games

    already_updated, already_running, update_started, errors = [], [], [], []

    for game in targets:
        state = game["state"]
        name  = game["name"]
        if state == 4:
            already_updated.append(name)
        elif state == 1026:
            already_running.append(name)
        else:
            try:
                subprocess.Popen([str(steam_exe), f"steam://update/{game['id']}"])
                update_started.append(name)
                time.sleep(0.3)
            except Exception as e:
                errors.append(f"{name}: {e}")

    parts = []
    if update_started:
        names  = ", ".join(update_started[:3])
        suffix = f" 외 {len(update_started) - 3}개" if len(update_started) > 3 else ""
        parts.append(f"업데이트 시작: {names}{suffix}.")
    if already_running:
        parts.append(f"이미 업데이트 중: {', '.join(already_running)}.")
    if already_updated:
        parts.append(
            f"'{already_updated[0]}'은(는) 이미 최신 버전입니다."
            if game_name else
            f"{len(already_updated)}개 게임이 이미 최신 버전입니다."
        )
    if errors:
        parts.append(f"오류: {'; '.join(errors)}.")
    return " ".join(parts) if parts else "업데이트할 게임이 없습니다."


_KNOWN_APPIDS: dict[str, tuple[str, str]] = {
    "pubg":                ("578080",  "PUBG: Battlegrounds"),
    "pubg battlegrounds":  ("578080",  "PUBG: Battlegrounds"),
    "배틀그라운드":         ("578080",  "PUBG: Battlegrounds"),
    "gta5":                ("271590",  "Grand Theft Auto V"),
    "gta v":               ("271590",  "Grand Theft Auto V"),
    "grand theft auto v":  ("271590",  "Grand Theft Auto V"),
    "cs2":                 ("730",     "Counter-Strike 2"),
    "csgo":                ("730",     "Counter-Strike 2"),
    "counter-strike 2":    ("730",     "Counter-Strike 2"),
    "카운터스트라이크":     ("730",     "Counter-Strike 2"),
    "dota2":               ("570",     "Dota 2"),
    "dota 2":              ("570",     "Dota 2"),
    "rust":                ("252490",  "Rust"),
    "valheim":             ("892970",  "Valheim"),
    "cyberpunk":           ("1091500", "Cyberpunk 2077"),
    "cyberpunk 2077":      ("1091500", "Cyberpunk 2077"),
    "사이버펑크":           ("1091500", "Cyberpunk 2077"),
    "elden ring":          ("1245620", "ELDEN RING"),
    "엘든링":              ("1245620", "ELDEN RING"),
    "minecraft":           ("1672970", "Minecraft Launcher"),
    "마인크래프트":         ("1672970", "Minecraft Launcher"),
    "apex legends":        ("1172470", "Apex Legends"),
    "apex":                ("1172470", "Apex Legends"),
    "에이펙스":             ("1172470", "Apex Legends"),
    "fortnite":            ("1517990", "Fortnite"),
    "포트나이트":           ("1517990", "Fortnite"),
    "goose goose duck":    ("1568590", "Goose Goose Duck"),
    "among us":            ("945360",  "Among Us"),
    "어몽어스":             ("945360",  "Among Us"),
    "fall guys":           ("1097150", "Fall Guys"),
    "폴가이즈":             ("1097150", "Fall Guys"),
    "rocket league":       ("252950",  "Rocket League"),
    "로켓리그":             ("252950",  "Rocket League"),
    "warframe":            ("230410",  "Warframe"),
    "destiny 2":           ("1085660", "Destiny 2"),
    "team fortress 2":     ("440",     "Team Fortress 2"),
    "tf2":                 ("440",     "Team Fortress 2"),
    "left 4 dead 2":       ("550",     "Left 4 Dead 2"),
    "l4d2":                ("550",     "Left 4 Dead 2"),
}


def _search_steam_appid(game_name: str) -> tuple[str | None, str | None]:
    name_lower = game_name.lower().strip()

    steam_path = _find_steam_path()
    if steam_path:
        for g in _get_steam_games(steam_path):
            if name_lower in g["name"].lower():
                return g["id"], g["name"]

    if name_lower in _KNOWN_APPIDS:
        app_id, canonical = _KNOWN_APPIDS[name_lower]
        return app_id, canonical

    for key, (app_id, canonical) in _KNOWN_APPIDS.items():
        if name_lower in key or key in name_lower:
            return app_id, canonical

    try:
        import urllib.request, urllib.parse
        query = urllib.parse.quote(game_name)
        url   = f"https://store.steampowered.com/api/storesearch/?term={query}&l=korean&cc=KR"
        req   = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            items = json.loads(resp.read().decode()).get("items", [])
        if items:
            best = items[0]
            return str(best["id"]), best["name"]
    except Exception as e:
        print(f"[게임업데이터] ⚠️ AppID 검색 실패: {e}")

    return None, None


def _find_best_drive() -> dict | None:
    import shutil, string
    drives = []
    for letter in string.ascii_uppercase:
        drive_path = f"{letter}:\\"
        if os.path.exists(drive_path):
            try:
                gb = shutil.disk_usage(drive_path).free / (1024 ** 3)
                if gb > 0:
                    drives.append({"letter": letter, "path": drive_path, "free_gb": gb})
            except Exception:
                continue
    return max(drives, key=lambda d: d["free_gb"]) if drives else None


def _select_drive_in_dialog(dialog, drive_letter: str) -> bool:
    target = drive_letter.upper()
    for control_type in ("ListItem", "RadioButton"):
        try:
            for ctrl in dialog.descendants(control_type=control_type):
                if target in ctrl.window_text().upper():
                    ctrl.click_input()
                    return True
        except Exception:
            continue
    try:
        for combo in dialog.descendants(control_type="ComboBox"):
            try:
                combo.expand()
                time.sleep(0.15)
                for idx, txt in enumerate(combo.texts()):
                    if target in txt.upper():
                        combo.select(idx)
                        return True
                combo.collapse()
            except Exception:
                continue
    except Exception:
        pass
    return False


def _click_button(window, keywords: list[str]) -> bool:
    try:
        for btn in window.descendants(control_type="Button"):
            try:
                txt = btn.window_text().lower().strip()
                if txt in keywords or any(kw in txt for kw in keywords):
                    btn.click_input()
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _handle_install_dialog(game_name: str) -> str:
    best_drive = _find_best_drive()
    if not best_drive:
        return f"'{game_name}' 설치 대화상자가 열렸습니다. 드라이브를 수동으로 선택해주세요."

    drive_letter = best_drive["letter"]
    drive_label  = f"{drive_letter}:"

    try:
        from pywinauto import Application, findwindows
        dialog = None
        for _ in range(40):
            time.sleep(0.5)
            try:
                for hwnd in findwindows.find_windows(title_re=r"(?i)(install|설치|steam)", visible_only=True):
                    try:
                        app  = Application(backend="uia").connect(handle=hwnd)
                        win  = app.window(handle=hwnd)
                        rect = win.rectangle()
                        if win.is_visible() and rect.width() > 300 and rect.height() > 200:
                            all_text = " ".join(c.window_text() for c in win.descendants() if c.window_text()).upper()
                            if any(x in all_text for x in ("C:", "D:", "E:", "F:", "INSTALL", "설치")):
                                dialog = win
                                break
                    except Exception:
                        continue
            except Exception:
                pass
            if dialog:
                break

        if not dialog:
            raise RuntimeError("대화상자를 찾을 수 없습니다")

        dialog.set_focus()
        time.sleep(0.4)
        drive_selected  = _select_drive_in_dialog(dialog, drive_letter)
        install_clicked = _click_button(dialog, ["install", "설치", "next", "다음", "ok", "확인"])

        if install_clicked:
            suffix = f"{drive_label}을(를) 선택하고" if drive_selected else "기본 드라이브에서"
            return f"{suffix} '{game_name}' 설치가 클릭되었습니다."
        return f"'{game_name}'의 설치 버튼을 수동으로 클릭해주세요."

    except ImportError:
        return _handle_install_dialog_pyautogui(game_name, best_drive)
    except Exception as e:
        return _handle_install_dialog_pyautogui(game_name, best_drive)


def _handle_install_dialog_pyautogui(game_name: str, best_drive: dict) -> str:
    try:
        import pyautogui
        import pygetwindow as gw
    except ImportError:
        return f"'{game_name}' 설치 대화상자에서 '{best_drive['letter']}:'을(를) 선택하고 설치를 클릭해주세요."

    pyautogui.FAILSAFE = False
    drive_label  = f"{best_drive['letter']}:"
    install_win  = None

    for _ in range(30):
        time.sleep(0.5)
        for w in gw.getAllWindows():
            if ("install" in w.title.lower() or "설치" in w.title or "steam" in w.title.lower()) and w.width > 300 and w.visible:
                install_win = w
                break
        if install_win:
            break

    if not install_win:
        return f"'{game_name}' Steam에서 '{drive_label}'을(를) 선택하고 설치를 클릭해주세요."

    try:
        install_win.activate()
        time.sleep(0.4)
    except Exception:
        pass

    wx, wy = install_win.left, install_win.top
    ww, wh = install_win.width, install_win.height
    pyautogui.click(wx + int(ww * 0.35), wy + int(wh * 0.45))
    time.sleep(0.2)
    pyautogui.typewrite(best_drive["letter"], interval=0.05)
    time.sleep(0.2)
    pyautogui.click(wx + int(ww * 0.72), wy + int(wh * 0.88))
    return f"'{game_name}'의 드라이브 {drive_label} 선택 및 설치 클릭을 시도했습니다."


def _install_steam_game(steam_path: Path, game_name: str = None, app_id: str = None) -> str:
    if not _ensure_steam_running(steam_path):
        return "Steam을 시작할 수 없습니다."

    steam_exe       = steam_path / "steam.exe"
    installed_games = _get_steam_games(steam_path)

    already = None
    if app_id:
        already = next((g for g in installed_games if g["id"] == str(app_id)), None)
    elif game_name:
        name_lower = game_name.lower()
        already    = next((g for g in installed_games if name_lower in g["name"].lower()), None)
    else:
        return "게임 이름 또는 AppID를 지정해주세요."

    if already:
        state = already["state"]
        name  = already["name"]
        if state == 4:
            return f"'{name}'은(는) 이미 설치되어 최신 버전입니다."
        if state == 1026:
            return f"'{name}'은(는) 현재 다운로드 또는 업데이트 중입니다."
        if state in (6, 516):
            subprocess.Popen([str(steam_exe), f"steam://update/{already['id']}"])
            return f"'{name}'에 보류 중인 업데이트가 있습니다. 업데이트를 시작했습니다."
        return f"'{name}'은(는) 이미 설치되어 있습니다."

    if not app_id and game_name:
        found_id, found_name = _search_steam_appid(game_name)
        if not found_id:
            return f"'{game_name}'을(를) Steam에서 찾을 수 없습니다. AppID를 직접 제공해주세요."
        app_id    = found_id
        game_name = found_name or game_name

    try:
        subprocess.Popen([str(steam_exe), f"steam://install/{app_id}"])
        threading.Thread(target=_handle_install_dialog, args=(game_name or str(app_id),), daemon=True).start()
        return f"'{game_name}' 설치를 시작했습니다. Steam에서 다운로드 대화상자가 열립니다."
    except Exception as e:
        return f"설치 실패: {e}"


def _get_download_status(steam_path: Path) -> str:
    games   = _get_steam_games(steam_path)
    active  = [g for g in games if g["state"] == 1026]
    pending = [g for g in games if g["state"] in (6, 516)]
    lines   = []
    if active:
        lines.append(f"다운로드 중: {', '.join(g['name'] for g in active)}.")
    if pending:
        names  = ", ".join(g["name"] for g in pending[:5])
        suffix = f" 외 {len(pending) - 5}개" if len(pending) > 5 else ""
        lines.append(f"업데이트 대기: {names}{suffix}.")
    return " ".join(lines) if lines else "현재 활성 다운로드 또는 업데이트 대기 없음."


def _watch_and_shutdown(steam_path: Path, speak=None, check_interval: int = 30, timeout_hours: int = 12):
    print("[게임업데이터] 👁️ 다운로드 완료 후 종료 대기 중...")
    deadline = time.time() + timeout_hours * 3600

    for _ in range(24):
        time.sleep(5)
        active = [g for g in _get_steam_games(steam_path) if g["state"] == 1026]
        if active:
            names = ", ".join(g["name"] for g in active)
            if speak: speak(f"{names} 다운로드가 시작되었습니다. 완료되면 자동으로 종료합니다.")
            break
    else:
        return

    while time.time() < deadline:
        time.sleep(check_interval)
        if not any(g["state"] == 1026 for g in _get_steam_games(steam_path)):
            if speak: speak("다운로드가 완료되었습니다. 지금 종료합니다.")
            time.sleep(5)
            subprocess.run(["shutdown", "/s", "/t", "10"])
            return

    if speak: speak("다운로드가 너무 오래 걸립니다. 자동 종료를 취소합니다.")


def _get_epic_games() -> list[dict]:
    manifests_path = (Path(os.environ.get("PROGRAMDATA", "C:/ProgramData"))
                      / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests")
    if not manifests_path.exists():
        return []
    games = []
    for item_file in manifests_path.glob("*.item"):
        try:
            data = json.loads(item_file.read_text(encoding="utf-8"))
            name = data.get("DisplayName") or data.get("AppName", "")
            if name:
                games.append({"id": data.get("AppName", ""), "name": name})
        except Exception:
            continue
    return games


def _is_epic_running() -> bool:
    try:
        return "epicgameslauncher.exe" in subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq EpicGamesLauncher.exe"],
            capture_output=True, text=True
        ).stdout.lower()
    except Exception:
        return False


def _update_epic_games(epic_path: Path, game_name: str = None) -> str:
    epic_exe = epic_path / "EpicGamesLauncher.exe"
    if not epic_exe.exists():
        return "Epic Games 런처를 찾을 수 없습니다."
    games = _get_epic_games()
    if game_name:
        name_lower = game_name.lower()
        matched    = [g for g in games if name_lower in g["name"].lower()]
        if not matched:
            return f"Epic에서 '{game_name}'을(를) 찾을 수 없습니다."
        try:
            subprocess.Popen([str(epic_exe), f"com.epicgames.launcher://apps/{matched[0]['id']}?action=launch&silent=true"])
            return f"'{matched[0]['name']}'의 Epic 업데이트를 열었습니다."
        except Exception as e:
            return f"Epic 업데이트 실패: {e}"
    else:
        try:
            if _is_epic_running():
                for g in games[:10]:
                    subprocess.Popen([str(epic_exe), f"com.epicgames.launcher://apps/{g['id']}?action=launch&silent=true"])
                    time.sleep(0.5)
                return f"{len(games)}개의 Epic 게임 업데이트 확인을 트리거했습니다."
            else:
                subprocess.Popen([str(epic_exe)])
                return f"Epic Games 런처가 열렸습니다. {len(games)}개 게임이 확인됩니다."
        except Exception as e:
            return f"Epic 업데이트 실패: {e}"


def _schedule_daily_update(hour: int = 3, minute: int = 0) -> str:
    task_name   = "JARVIS_GameUpdater"
    script_path = Path(__file__).resolve()
    subprocess.run(["schtasks", "/Delete", "/TN", task_name, "/F"], capture_output=True)
    for extra in (["/RL", "HIGHEST", "/RU", "SYSTEM"], []):
        cmd    = ["schtasks", "/Create", "/TN", task_name,
                  "/TR", f'"{sys.executable}" "{script_path}" --scheduled',
                  "/SC", "DAILY", "/ST", f"{hour:02d}:{minute:02d}", "/F", *extra]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return f"매일 {hour:02d}:{minute:02d}에 게임 업데이트가 예약되었습니다."
    return f"예약 실패: {result.stderr.strip()}"


def _cancel_scheduled_update() -> str:
    result = subprocess.run(["schtasks", "/Delete", "/TN", "JARVIS_GameUpdater", "/F"],
                            capture_output=True, text=True)
    return "예약된 업데이트가 취소되었습니다." if result.returncode == 0 else "예약된 업데이트를 찾을 수 없습니다."


def _get_schedule_status() -> str:
    result = subprocess.run(["schtasks", "/Query", "/TN", "JARVIS_GameUpdater", "/FO", "LIST"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        return "예약된 게임 업데이트를 찾을 수 없습니다."
    for line in result.stdout.strip().split("\n"):
        if "Next Run" in line or "다음 실행" in line:
            return f"게임 업데이트가 예약되어 있습니다. {line.strip()}"
    return "게임 업데이트가 예약되어 있습니다."


def game_updater(parameters: dict, player=None, speak=None) -> str:
    p         = parameters or {}
    action    = p.get("action",    "update").lower().strip()
    platform  = p.get("platform",  "both").lower().strip()
    game_name = (p.get("game_name") or "").strip() or None
    app_id    = (p.get("app_id")    or "").strip() or None
    hour      = int(p.get("hour",   3))
    minute    = int(p.get("minute", 0))
    shutdown  = str(p.get("shutdown_when_done", "false")).lower() == "true"

    results = []

    if action == "schedule":        return _schedule_daily_update(hour=hour, minute=minute)
    if action == "cancel_schedule": return _cancel_scheduled_update()
    if action == "schedule_status": return _get_schedule_status()

    if action == "list":
        if platform in ("steam", "both"):
            steam_path = _find_steam_path()
            if steam_path:
                games = _get_steam_games(steam_path)
                if games:
                    names  = ", ".join(g["name"] for g in games[:8])
                    suffix = f" 외 {len(games) - 8}개" if len(games) > 8 else ""
                    results.append(f"Steam ({len(games)}개): {names}{suffix}.")
                else:
                    results.append("Steam: 게임을 찾을 수 없습니다.")
            else:
                results.append("Steam: 설치되지 않았습니다.")
        if platform in ("epic", "both"):
            games = _get_epic_games()
            if games:
                names  = ", ".join(g["name"] for g in games[:8])
                suffix = f" 외 {len(games) - 8}개" if len(games) > 8 else ""
                results.append(f"Epic ({len(games)}개): {names}{suffix}.")
            else:
                results.append("Epic: 게임을 찾을 수 없습니다.")
        return " | ".join(results) or "플랫폼을 찾을 수 없습니다."

    if action == "download_status":
        if platform in ("steam", "both"):
            steam_path = _find_steam_path()
            results.append(_get_download_status(steam_path) if steam_path else "Steam: 설치되지 않았습니다.")
        if platform in ("epic", "both"):
            results.append("Epic 다운로드 상태는 직접 확인할 수 없습니다.")
        return " ".join(results)

    if action in ("install", "update"):
        if platform in ("steam", "both"):
            steam_path = _find_steam_path()
            if not steam_path:
                results.append("Steam: 설치되지 않았습니다.")
            else:
                if game_name:
                    installed    = _get_steam_games(steam_path)
                    name_lower   = game_name.lower()
                    is_installed = any(name_lower in g["name"].lower() for g in installed)

                    if not is_installed:
                        msg = _install_steam_game(steam_path, game_name=game_name, app_id=app_id)
                        if shutdown:
                            threading.Thread(target=_watch_and_shutdown,
                                             kwargs={"steam_path": steam_path, "speak": speak},
                                             daemon=True).start()
                            msg += " 자동 종료가 활성화되었습니다."
                        if player: player.write_log(f"[게임업데이터] {msg[:100]}")
                        if speak: speak(msg)
                        return msg
                    else:
                        results.append(f"Steam: {_update_steam_games(steam_path, game_name=game_name)}")
                else:
                    if action == "install":
                        results.append("Steam: 설치할 게임 이름을 지정해주세요.")
                    else:
                        results.append(f"Steam: {_update_steam_games(steam_path)}")

                if shutdown:
                    threading.Thread(target=_watch_and_shutdown,
                                     kwargs={"steam_path": steam_path, "speak": speak},
                                     daemon=True).start()
                    results.append("자동 종료가 활성화되었습니다.")

        if platform in ("epic", "both"):
            epic_path = _find_epic_path()
            if epic_path:
                results.append(f"Epic: {_update_epic_games(epic_path, game_name=game_name)}")
            else:
                results.append("Epic: 설치되지 않았습니다.")

        output = " | ".join(results) or "할 작업이 없습니다."
        if player: player.write_log(f"[게임업데이터] {output[:100]}")
        if speak: speak(output)
        return output

    return f"알 수 없는 액션: '{action}'."


if __name__ == "__main__":
    if "--scheduled" in sys.argv:
        print(f"[게임업데이터] 🕐 예약 실행: {datetime.now().strftime('%H:%M')}")
        print(f"[게임업데이터] ✅ {game_updater({'action': 'update', 'platform': 'both'})}")
