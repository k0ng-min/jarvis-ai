# actions/code_helper.py — Claude CLI 기반 코드 어시스턴트

import subprocess
import sys
import json
import re
import time
from pathlib import Path

from ..paths import PROJECT_ROOT

def get_base_dir():
    return PROJECT_ROOT


BASE_DIR           = get_base_dir()
DESKTOP            = Path.home() / "Desktop"
MAX_BUILD_ATTEMPTS = 3


def _call_claude(prompt: str, timeout: int = 60) -> str:
    """Claude CLI로 응답 생성"""
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=timeout, encoding="utf-8"
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            return data.get("result", "").strip()
    except Exception as e:
        print(f"[코드] Claude 오류: {e}")
    return ""


def _clean_code(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _resolve_save_path(output_path: str, language: str) -> Path:
    ext_map = {
        "python": ".py", "py": ".py",
        "javascript": ".js", "js": ".js",
        "typescript": ".ts", "ts": ".ts",
        "html": ".html", "css": ".css",
        "java": ".java", "cpp": ".cpp", "c": ".c",
        "bash": ".sh", "shell": ".sh", "powershell": ".ps1",
        "sql": ".sql", "json": ".json", "rust": ".rs", "go": ".go",
    }
    if output_path:
        p = Path(output_path)
        return p if p.is_absolute() else DESKTOP / p
    ext = ext_map.get((language or "python").lower(), ".py")
    return DESKTOP / f"jarvis_code{ext}"


def _read_file(file_path: str) -> tuple[str, str]:
    if not file_path:
        return "", "파일 경로가 없습니다."
    p = Path(file_path)
    if not p.exists():
        return "", f"파일을 찾을 수 없습니다: {file_path}"
    try:
        return p.read_text(encoding="utf-8"), ""
    except Exception as e:
        return "", f"파일 읽기 실패: {e}"


def _save_file(path: Path, content: str) -> str:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"저장됨: {path}"
    except Exception as e:
        return f"저장 실패: {e}"


def _preview(code: str, lines: int = 10) -> str:
    all_lines = code.splitlines()
    preview   = "\n".join(all_lines[:lines])
    suffix    = f"\n... ({len(all_lines) - lines}줄 더)" if len(all_lines) > lines else ""
    return preview + suffix


def _has_error(output: str) -> bool:
    error_signals = ["error", "exception", "traceback", "syntaxerror",
                     "nameerror", "typeerror", "stderr", "failed", "crash"]
    return any(s in output.lower() for s in error_signals)


def _take_screenshot() -> Path | None:
    try:
        import pyautogui
        screenshot_path = Path.home() / "Desktop" / f"jarvis_debug_{int(time.time())}.png"
        screenshot = pyautogui.screenshot()
        screenshot.save(str(screenshot_path))
        return screenshot_path
    except Exception as e:
        print(f"[코드] ⚠️ 스크린샷 실패: {e}")
        return None


def _detect_intent(description: str, file_path: str, code: str) -> str:
    desc = (description or "").lower()

    screen_kw = ["화면", "screen", "스크린", "이 오류", "왜 오류", "what's wrong",
                 "뭐가 문제", "스크린샷", "screenshot"]
    if any(k in desc for k in screen_kw):
        return "screen_debug"

    optimize_kw = ["최적화", "리팩토링", "optimize", "refactor", "clean up",
                   "개선", "더 좋게", "make it better", "빠르게"]
    if any(k in desc for k in optimize_kw) and (code or file_path):
        return "optimize"

    if file_path:
        p = Path(file_path)
        edit_kw  = ["수정", "편집", "변경", "추가", "제거", "edit", "update", "modify",
                    "change", "add", "remove", "fix", "rename"]
        run_kw   = ["실행", "run", "execute", "launch"]
        build_kw = ["빌드", "build", "만들어봐", "시도해봐"]

        if p.exists() and any(k in desc for k in edit_kw):
            return "edit"
        if p.exists() and any(k in desc for k in run_kw):
            return "run"
        if any(k in desc for k in build_kw):
            return "build"
        if p.exists():
            return "explain"

    explain_kw = ["설명", "분석", "explain", "what does", "describe", "analyze", "뭐 하는"]
    if any(k in desc for k in explain_kw) and (code or file_path):
        return "explain"

    build_kw = ["빌드", "build", "만들어봐", "작동하게"]
    if any(k in desc for k in build_kw):
        return "build"

    return "write"


def _write(description: str, language: str, output_path: str, player=None) -> tuple[str, Path]:
    lang   = language or "python"
    prompt = (
        f"당신은 전문 {lang} 개발자입니다.\n"
        f"다음 설명에 대한 깔끔하고 작동하는, 잘 주석된 {lang} 코드를 작성하세요.\n\n"
        f"규칙:\n"
        f"- 코드만 출력. 설명, 마크다운, 백틱 없음.\n"
        f"- 도움이 되는 인라인 주석을 추가하세요.\n"
        f"- 오류와 엣지 케이스를 적절히 처리하세요.\n"
        f"- 현대적인 모범 사례를 사용하세요.\n\n"
        f"설명: {description}\n\n코드:"
    )

    code = _call_claude(prompt, timeout=90)
    if not code:
        raise RuntimeError("Claude에서 코드를 생성하지 못했습니다.")
    code = _clean_code(code)
    path = _resolve_save_path(output_path, lang)
    _save_file(path, code)
    return code, path


def _fix_code(code: str, error_output: str, description: str) -> str:
    prompt = (
        f"당신은 전문 디버거입니다.\n"
        f"아래 코드가 다음 오류로 실패했습니다. 수정하세요.\n"
        f"수정된 코드만 반환하세요 — 설명, 마크다운, 백틱 없음.\n\n"
        f"원래 목표: {description}\n\n"
        f"오류:\n{error_output[:2000]}\n\n"
        f"잘못된 코드:\n{code}\n\n수정된 코드:"
    )
    fixed = _call_claude(prompt, timeout=90)
    if not fixed:
        return code
    return _clean_code(fixed)


def _run_file(path: Path, args: list, timeout: int) -> str:
    interpreters = {
        ".py":  [sys.executable],
        ".js":  ["node"],
        ".ts":  ["ts-node"],
        ".sh":  ["bash"],
        ".ps1": ["powershell", "-File"],
        ".rb":  ["ruby"],
        ".php": ["php"],
    }
    interp = interpreters.get(path.suffix.lower())
    if not interp:
        return f".{path.suffix} 파일의 인터프리터가 없습니다."

    try:
        result = subprocess.run(
            interp + [str(path)] + (args or []),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, cwd=str(path.parent)
        )
        output = result.stdout.strip()
        error  = result.stderr.strip()
        parts  = []
        if output: parts.append(f"출력:\n{output}")
        if error:  parts.append(f"오류:\n{error}")
        return "\n\n".join(parts) if parts else "출력 없이 실행됨."
    except subprocess.TimeoutExpired:
        return f"{timeout}초 후 시간 초과."
    except FileNotFoundError:
        return f"인터프리터를 찾을 수 없습니다: {interp[0]}."
    except Exception as e:
        return f"실행 오류: {e}"


def _build(description, language, output_path, args, timeout, speak=None, player=None) -> str:
    if not description:
        return "무엇을 빌드하고 싶은지 설명해주세요."

    if player:
        player.write_log("[코드] 빌드 시작...")

    lang = language or "python"

    try:
        code, path = _write(description, lang, output_path, player)
        print(f"[코드] ✅ 작성됨: {path}")
    except Exception as e:
        msg = f"초기 코드를 작성할 수 없습니다: {e}"
        if speak: speak(msg)
        return msg

    last_output = ""
    for attempt in range(1, MAX_BUILD_ATTEMPTS + 1):
        print(f"[코드] 🔄 시도 {attempt}/{MAX_BUILD_ATTEMPTS}")
        if player:
            player.write_log(f"[코드] 시도 {attempt}...")

        last_output = _run_file(path, args, timeout)

        if not _has_error(last_output):
            msg = (
                f"빌드가 완료되었습니다. "
                f"{attempt}번 만에 코드가 작동합니다. "
                f"저장 위치: {path}."
            )
            if speak: speak(msg)
            return f"{msg}\n\n출력:\n{last_output}"

        print(f"[코드] ⚠️ 시도 {attempt}에서 오류 발생, 수정 중...")
        if player:
            player.write_log(f"[코드] 수정 중 (시도 {attempt})...")

        try:
            code = _fix_code(code, last_output, description)
            _save_file(path, code)
        except Exception as e:
            msg = f"시도 {attempt}에서 코드를 수정할 수 없습니다: {e}"
            if speak: speak(msg)
            return msg

    msg = (
        f"{MAX_BUILD_ATTEMPTS}번 시도 후에도 작동하는 버전을 빌드할 수 없습니다. "
        f"마지막 오류: {last_output[:200]}"
    )
    if speak: speak(msg)
    return f"{msg}\n\n마지막 코드 저장 위치: {path}"


def _write_action(description, language, output_path, player) -> str:
    if not description:
        return "무엇을 작성하고 싶은지 설명해주세요."
    if player:
        player.write_log("[코드] 코드 작성 중...")
    try:
        code, path = _write(description, language, output_path, player)
        print(f"[코드] ✅ 작성됨: {path}")
        return f"코드가 작성되었습니다. 저장 위치: {path}\n\n미리보기:\n{_preview(code)}"
    except Exception as e:
        return f"코드를 생성할 수 없습니다: {e}"


def _edit_action(file_path, instruction, player) -> str:
    if not file_path:
        return "수정할 파일 경로를 제공해주세요."
    if not instruction:
        return "어떤 변경을 할지 설명해주세요."

    content, err = _read_file(file_path)
    if err:
        return err

    if player:
        player.write_log("[코드] 파일 수정 중...")

    prompt = (
        f"당신은 전문 코드 편집기입니다.\n"
        f"아래 코드에 다음 변경 사항을 적용하세요.\n"
        f"완전한 업데이트된 코드만 반환하세요 — 설명, 마크다운, 백틱 없음.\n\n"
        f"변경 사항: {instruction}\n\n"
        f"원래 코드:\n{content}\n\n업데이트된 코드:"
    )

    edited = _call_claude(prompt, timeout=90)
    if not edited:
        return "코드를 수정할 수 없습니다."

    edited = _clean_code(edited)
    status = _save_file(Path(file_path), edited)
    print(f"[코드] ✅ 수정됨: {file_path}")
    return f"파일이 수정되었습니다. {status}\n\n미리보기:\n{_preview(edited)}"


def _explain_action(file_path, code, player) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err:
            return err
    if not code:
        return "설명할 코드 또는 파일 경로를 제공해주세요."

    if player:
        player.write_log("[코드] 코드 분석 중...")

    prompt = (
        f"이 코드가 무엇을 하는지 간단하고 명확한 언어로 설명하세요.\n"
        f"집중할 내용: 무엇을 하는지, 어떻게 작동하는지, 중요한 세부 사항.\n"
        f"한국어로 3~6문장으로 간결하게 답하세요.\n\n"
        f"코드:\n{code[:4000]}\n\n설명:"
    )

    result = _call_claude(prompt, timeout=60)
    return result or "코드를 설명할 수 없습니다."


def _run_action(file_path, args, timeout, player) -> str:
    if not file_path:
        return "실행할 파일 경로를 제공해주세요."
    p = Path(file_path)
    if not p.exists():
        return f"파일을 찾을 수 없습니다: {file_path}"
    if player:
        player.write_log(f"[코드] {p.name} 실행 중...")
    return _run_file(p, args, timeout)


def _optimize_action(file_path, code, language, output_path, player) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err:
            return err
    if not code:
        return "최적화할 코드 또는 파일 경로를 제공해주세요."

    if player:
        player.write_log("[코드] 코드 최적화 중...")

    lang   = language or "python"
    prompt = (
        f"당신은 전문 {lang} 개발자 및 코드 리뷰어입니다.\n"
        f"다음 코드를 최적화하세요:\n"
        f"1. 성능 — 불필요한 연산 제거\n"
        f"2. 가독성 — 명확한 변수명, 적절한 형식\n"
        f"3. 모범 사례 — 현대적인 {lang} 패턴, 오류 처리\n"
        f"4. 데드 코드, 불필요한 복잡성 제거\n\n"
        f"최적화된 코드만 반환하세요 — 설명, 마크다운, 백틱 없음.\n\n"
        f"원래 코드:\n{code[:6000]}\n\n최적화된 코드:"
    )

    optimized = _call_claude(prompt, timeout=90)
    if not optimized:
        return "코드를 최적화할 수 없습니다."

    optimized = _clean_code(optimized)

    if file_path:
        save_path = Path(file_path)
    else:
        save_path = _resolve_save_path(output_path, lang)

    status = _save_file(save_path, optimized)
    print(f"[코드] ✅ 최적화됨: {save_path}")

    original_lines  = len(code.splitlines())
    optimized_lines = len(optimized.splitlines())
    diff = original_lines - optimized_lines

    return (
        f"코드가 최적화되었습니다. {status}\n"
        f"줄 수: {original_lines} → {optimized_lines} "
        f"({'−' if diff > 0 else '+'}{abs(diff)}줄)\n\n"
        f"미리보기:\n{_preview(optimized)}"
    )


def _screen_debug_action(description, file_path, player, speak=None) -> str:
    if player:
        player.write_log("[코드] 분석을 위한 스크린샷 캡처 중...")

    screenshot_path = _take_screenshot()
    if not screenshot_path:
        return "스크린샷을 캡처할 수 없습니다. PyAutoGUI가 설치되어 있는지 확인하세요."

    file_content = ""
    if file_path:
        file_content, err = _read_file(file_path)
        if err:
            print(f"[코드] ⚠️ 파일 읽기 실패: {err}")

    user_question = description or "화면에서 오류나 문제를 찾아서 수정 방법을 알려주세요."

    context = ""
    if file_content:
        context = f"\n\n추가로 관련 파일 내용:\n```\n{file_content[:4000]}\n```"

    prompt = (
        f"스크린샷 파일: {screenshot_path}\n\n"
        f"질문: {user_question}{context}\n\n"
        f"다음을 해주세요:\n"
        f"1. 화면에서 보이는 오류나 예외를 식별하세요\n"
        f"2. 문제의 원인을 간단하게 설명하세요\n"
        f"3. 구체적인 수정 방법이나 해결책을 제공하세요\n"
        f"4. 코드가 보인다면 수정된 버전을 보여주세요\n"
        f"한국어로 답하세요."
    )

    try:
        analysis = _call_claude(prompt, timeout=60)
        if not analysis:
            return "화면을 분석할 수 없습니다."

        try:
            screenshot_path.unlink()
        except Exception:
            pass

        if file_path and file_content:
            code_match = re.search(r"```[a-zA-Z]*\n(.*?)```", analysis, re.DOTALL)
            if code_match:
                fixed_code = code_match.group(1).strip()
                save_path  = Path(file_path)
                _save_file(save_path, fixed_code)
                analysis += f"\n\n✅ 수정된 코드가 저장되었습니다: {file_path}"

        return analysis

    except Exception as e:
        try:
            screenshot_path.unlink()
        except Exception:
            pass
        return f"화면 분석 실패: {e}"


def code_helper(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None
) -> str:
    """
    코드 어시스턴트 — Claude CLI 기반

    parameters:
        action      : write | edit | explain | run | build | screen_debug | optimize | auto
        description : 코드 설명 / 변경 사항 / 분석할 문제
        language    : 프로그래밍 언어 (기본: python)
        output_path : 저장 경로
        file_path   : 기존 파일 경로 (edit/explain/run/build/optimize)
        code        : 원시 코드 문자열 (파일 없이 explain/optimize)
        args        : run/build용 CLI 인수 목록
        timeout     : 실행 타임아웃 (초, 기본: 30)
    """
    p           = parameters or {}
    action      = p.get("action", "auto").lower().strip()
    description = p.get("description", "").strip()
    language    = p.get("language", "python").strip()
    output_path = p.get("output_path", "").strip()
    file_path   = p.get("file_path", "").strip()
    code        = p.get("code", "").strip()
    args        = p.get("args", [])
    timeout     = int(p.get("timeout", 30))

    if action == "auto":
        action = _detect_intent(description, file_path, code)
        print(f"[코드] 🤖 자동 감지됨: {action}")

    if action == "write":
        return _write_action(description, language, output_path, player)

    elif action == "edit":
        return _edit_action(file_path, description or p.get("instruction", ""), player)

    elif action == "explain":
        return _explain_action(file_path, code, player)

    elif action == "run":
        return _run_action(file_path, args, timeout, player)

    elif action == "build":
        return _build(description, language, output_path, args, timeout, speak, player)

    elif action == "optimize":
        return _optimize_action(file_path, code, language, output_path, player)

    elif action == "screen_debug":
        return _screen_debug_action(description, file_path, player, speak)

    else:
        return f"알 수 없는 액션: '{action}'. write, edit, explain, run, build, optimize, screen_debug 중 하나를 사용하세요."
