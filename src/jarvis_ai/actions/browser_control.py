import asyncio
import threading
import concurrent.futures
import platform
import shutil
import subprocess
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout


def _get_default_browser_id() -> str:
    """Returns raw default browser identifier string for current OS."""
    system = platform.system()
    try:
        if system == "Windows":
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice"
            )
            prog_id = winreg.QueryValueEx(key, "ProgId")[0].lower()
            winreg.CloseKey(key)
            return prog_id

        elif system == "Darwin":
            result = subprocess.run(
                ["defaults", "read",
                 "com.apple.LaunchServices/com.apple.launchservices.secure",
                 "LSHandlers"],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.lower()

        elif system == "Linux":
            result = subprocess.run(
                ["xdg-settings", "get", "default-web-browser"],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.lower()

    except Exception:
        pass

    return ""


_BROWSER_BINARIES = {
    "Windows": {
        "opera":   ["opera.exe"],
        "brave":   ["brave.exe"],
        "vivaldi": ["vivaldi.exe"],
        "chrome":  ["chrome.exe"],
        "firefox": ["firefox.exe"],
    },
    "Darwin": {
        "opera":   ["opera"],
        "brave":   ["brave browser", "brave"],
        "vivaldi": ["vivaldi"],
        "chrome":  ["google chrome", "google-chrome"],
        "firefox": ["firefox"],
    },
    "Linux": {
        "opera":   ["opera", "opera-stable"],
        "brave":   ["brave-browser", "brave"],
        "vivaldi": ["vivaldi-stable", "vivaldi"],
        "chrome":  ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"],
        "firefox": ["firefox"],
    },
}


def _get_opera_executable() -> str | None:
    if platform.system() != "Windows":
        return None
    try:
        import winreg
        candidate_keys = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\opera.exe",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\launcher.exe",
            r"SOFTWARE\Clients\StartMenuInternet\OperaStable\shell\open\command",
            r"SOFTWARE\Clients\StartMenuInternet\OperaGXStable\shell\open\command",
        ]
        for key_path in candidate_keys:
            for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                try:
                    key = winreg.OpenKey(hive, key_path)
                    val = winreg.QueryValue(key, None)
                    winreg.CloseKey(key)
                    exe = val.strip().strip('"').split('"')[0].split(" --")[0].strip()
                    if exe and Path(exe).exists():
                        print(f"[브라우저] 🔍 Opera 레지스트리에서 발견: {exe}")
                        return exe
                except Exception:
                    continue
    except Exception:
        pass
    return None


def _find_browser_executable(prog_id: str) -> tuple:
    system  = platform.system()
    os_bins = _BROWSER_BINARIES.get(system, {})

    if any(x in prog_id for x in ["firefox", "mozilla"]):
        return "firefox", None, None, False

    if "safari" in prog_id:
        return "webkit", None, None, False

    if "edge" in prog_id:
        return "chromium", None, "msedge", False

    if "opera" in prog_id:
        exe = _get_opera_executable()
        if exe:
            return "chromium", exe, None, True
        for binary in os_bins.get("opera", []):
            path = shutil.which(binary)
            if path:
                return "chromium", path, None, True

    browser_patterns = {
        "brave":   ["brave"],
        "vivaldi": ["vivaldi"],
        "chrome":  ["chrome"],
    }
    for browser_name, patterns in browser_patterns.items():
        if not any(p in prog_id for p in patterns):
            continue
        binaries = os_bins.get(browser_name, [])
        for binary in binaries:
            path = shutil.which(binary)
            if path:
                print(f"[브라우저] 🔍 {browser_name} 발견: {path}")
                return "chromium", path, None, False

    if "chrome" in prog_id or not prog_id:
        return "chromium", None, "chrome", False

    return "chromium", None, None, False


class _BrowserThread:

    def __init__(self):
        self._loop        = None
        self._thread      = None
        self._ready       = threading.Event()
        self._playwright  = None
        self._browser     = None
        self._context     = None
        self._page        = None
        self._engine_name = "chromium"
        self._exe_path    = None
        self._channel     = None
        self._is_opera    = False

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="BrowserThread"
        )
        self._thread.start()
        self._ready.wait(timeout=15)

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._init())
        self._ready.set()
        self._loop.run_forever()

    async def _init(self):
        self._playwright = await async_playwright().start()

    def run(self, coro, timeout: int = 30):
        if not self._loop:
            raise RuntimeError("BrowserThread가 시작되지 않았습니다.")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    async def _launch_browser_if_needed(self):
        if self._browser and self._browser.is_connected():
            return

        prog_id = _get_default_browser_id()
        self._engine_name, self._exe_path, self._channel, self._is_opera = _find_browser_executable(prog_id)
        engine = getattr(self._playwright, self._engine_name)

        chromium_args = ["--start-maximized"]

        if self._is_opera:
            chromium_args += [
                "--disable-features=OperaPrivacyMode",
                "--no-private",
            ]
            print("[브라우저] 🎭 Opera 감지됨 — 개인 모드 비활성화")

        launch_kwargs = {"headless": False}
        if self._engine_name == "chromium":
            launch_kwargs["args"] = chromium_args
        if self._exe_path:
            launch_kwargs["executable_path"] = self._exe_path
        elif self._channel:
            launch_kwargs["channel"] = self._channel

        try:
            self._browser = await engine.launch(**launch_kwargs)
            print(
                f"[브라우저] ✅ 실행됨 ({self._engine_name}"
                f"{' / ' + self._channel if self._channel else ''}"
                f"{' / ' + self._exe_path if self._exe_path else ''})"
            )
        except Exception as e:
            print(f"[브라우저] ⚠️ 실행 실패 ({e}), 기본 Chromium으로 전환")
            self._browser = await self._playwright.chromium.launch(
                headless=False,
                args=["--start-maximized"]
            )

    async def _get_page(self):
        await self._launch_browser_if_needed()

        if self._context is None:
            self._context = await self._browser.new_context(
                viewport=None,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )

        if self._page is None or self._page.is_closed():
            self._page = await self._context.new_page()

        return self._page

    async def _go_to(self, url: str) -> str:
        if not url.startswith("http"):
            url = "https://" + url
        page = await self._get_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            return f"열림: {page.url}"
        except PlaywrightTimeout:
            return f"시간 초과: {url}"
        except Exception as e:
            return f"탐색 오류: {e}"

    async def _search(self, query: str, engine: str = "google") -> str:
        engines = {
            "google":     f"https://www.google.com/search?q={query.replace(' ', '+')}",
            "bing":       f"https://www.bing.com/search?q={query.replace(' ', '+')}",
            "duckduckgo": f"https://duckduckgo.com/?q={query.replace(' ', '+')}",
        }
        url = engines.get(engine.lower(), engines["google"])
        return await self._go_to(url)

    async def _click(self, selector=None, text=None) -> str:
        page = await self._get_page()
        try:
            if text:
                await page.get_by_text(text, exact=False).first.click(timeout=8000)
                return f"클릭됨: '{text}'"
            elif selector:
                await page.click(selector, timeout=8000)
                return f"클릭됨: {selector}"
            return "선택자 또는 텍스트가 없습니다."
        except PlaywrightTimeout:
            return "요소를 찾을 수 없거나 클릭할 수 없습니다."
        except Exception as e:
            return f"클릭 오류: {e}"

    async def _type(self, selector=None, text: str = "", clear_first: bool = True) -> str:
        page = await self._get_page()
        try:
            element = page.locator(selector).first if selector else page.locator(":focus")
            if clear_first:
                await element.clear()
            await element.type(text, delay=50)
            return "텍스트 입력됨."
        except Exception as e:
            return f"입력 오류: {e}"

    async def _scroll(self, direction: str = "down", amount: int = 500) -> str:
        page = await self._get_page()
        try:
            y = amount if direction == "down" else -amount
            await page.mouse.wheel(0, y)
            return f"{direction} 스크롤됨."
        except Exception as e:
            return f"스크롤 오류: {e}"

    async def _press(self, key: str) -> str:
        page = await self._get_page()
        try:
            await page.keyboard.press(key)
            return f"키 입력됨: {key}"
        except Exception as e:
            return f"키 입력 오류: {e}"

    async def _get_text(self) -> str:
        page = await self._get_page()
        try:
            text = await page.inner_text("body")
            return text[:4000] if len(text) > 4000 else text
        except Exception as e:
            return f"페이지 텍스트 가져오기 실패: {e}"

    async def _fill_form(self, fields: dict) -> str:
        page    = await self._get_page()
        results = []
        for selector, value in fields.items():
            try:
                el = page.locator(selector).first
                await el.clear()
                await el.type(str(value), delay=40)
                results.append(f"✓ {selector}")
            except Exception as e:
                results.append(f"✗ {selector}: {e}")
        return "양식 입력됨: " + ", ".join(results)

    async def _smart_click(self, description: str) -> str:
        page       = await self._get_page()
        desc_lower = description.lower()

        role_hints = {
            "button":    ["button", "버튼", "btn"],
            "link":      ["link", "링크"],
            "searchbox": ["search", "검색"],
            "textbox":   ["input", "field", "입력"],
        }
        for role, keywords in role_hints.items():
            if any(k in desc_lower for k in keywords):
                try:
                    await page.get_by_role(role).first.click(timeout=5000)
                    return f"클릭됨 ({role}): '{description}'"
                except Exception:
                    pass

        try:
            await page.get_by_text(description, exact=False).first.click(timeout=5000)
            return f"클릭됨 (텍스트): '{description}'"
        except Exception:
            pass

        try:
            await page.get_by_placeholder(description, exact=False).first.click(timeout=5000)
            return f"클릭됨 (placeholder): '{description}'"
        except Exception:
            pass

        return f"찾을 수 없습니다: '{description}'"

    async def _smart_type(self, description: str, text: str) -> str:
        page = await self._get_page()

        for method, locator in [
            ("placeholder", page.get_by_placeholder(description, exact=False)),
            ("label",       page.get_by_label(description, exact=False)),
            ("role",        page.get_by_role("textbox")),
        ]:
            try:
                el = locator.first
                await el.clear()
                await el.type(text, delay=50)
                return f"입력됨 ({method}): '{description}'"
            except Exception:
                continue

        return f"입력창을 찾을 수 없습니다: '{description}'"

    async def _close_browser(self) -> str:
        if self._browser:
            await self._browser.close()
            self._browser = None
            self._context = None
            self._page    = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        return "브라우저가 닫혔습니다."


_bt         = _BrowserThread()
_bt_started = False
_bt_lock    = threading.Lock()


def _ensure_started():
    global _bt_started
    with _bt_lock:
        if not _bt_started:
            _bt.start()
            _bt_started = True


def browser_control(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None
) -> str:
    """
    브라우저 컨트롤러 — 시스템 기본 브라우저를 자동 감지하여 사용합니다.

    parameters:
        action      : go_to | search | click | type | scroll | fill_form |
                      smart_click | smart_type | get_text | press | close
        url         : go_to용 URL
        query       : 검색어
        engine      : google | bing | duckduckgo (기본: google)
        selector    : CSS 선택자
        text        : 클릭하거나 입력할 텍스트
        description : smart_click/smart_type용 요소 설명
        direction   : up | down (스크롤 방향)
        amount      : 스크롤 픽셀 수 (기본: 500)
        key         : 키 이름 (예: Enter, Escape, Tab)
        fields      : {selector: value} 딕셔너리 (fill_form용)
        clear_first : 입력 전 지우기 여부 (기본: True)
    """
    _ensure_started()

    action = (parameters or {}).get("action", "").lower().strip()
    result = "알 수 없는 액션입니다."

    try:
        if action == "go_to":
            result = _bt.run(_bt._go_to(parameters.get("url", "")))

        elif action == "search":
            result = _bt.run(_bt._search(
                parameters.get("query", ""),
                parameters.get("engine", "google"),
            ))

        elif action == "click":
            result = _bt.run(_bt._click(
                selector=parameters.get("selector"),
                text=parameters.get("text"),
            ))

        elif action == "type":
            result = _bt.run(_bt._type(
                selector=parameters.get("selector"),
                text=parameters.get("text", ""),
                clear_first=parameters.get("clear_first", True),
            ))

        elif action == "scroll":
            result = _bt.run(_bt._scroll(
                direction=parameters.get("direction", "down"),
                amount=parameters.get("amount", 500),
            ))

        elif action == "fill_form":
            result = _bt.run(_bt._fill_form(parameters.get("fields", {})))

        elif action == "smart_click":
            result = _bt.run(_bt._smart_click(parameters.get("description", "")))

        elif action == "smart_type":
            result = _bt.run(_bt._smart_type(
                parameters.get("description", ""),
                parameters.get("text", ""),
            ))

        elif action == "get_text":
            result = _bt.run(_bt._get_text())

        elif action == "press":
            result = _bt.run(_bt._press(parameters.get("key", "Enter")))

        elif action == "close":
            result = _bt.run(_bt._close_browser())

        else:
            result = f"알 수 없는 액션: {action}"

    except concurrent.futures.TimeoutError:
        result = "브라우저 작업 시간이 초과되었습니다."
    except Exception as e:
        result = f"브라우저 오류: {e}"

    print(f"[브라우저] {result[:80]}")
    if player:
        player.write_log(f"[브라우저] {result[:60]}")

    return result
