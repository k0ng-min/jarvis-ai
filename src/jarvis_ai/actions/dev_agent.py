# actions/dev_agent.py — Claude CLI 기반 자율 개발 에이전트

import subprocess
import sys
import json
import re
import time
from pathlib import Path

from ..paths import PROJECT_ROOT

def get_base_dir():
    return PROJECT_ROOT


BASE_DIR         = get_base_dir()
PROJECTS_DIR     = Path.home() / "Desktop" / "JarvisProjects"
MAX_FIX_ATTEMPTS = 5


def _call_claude(prompt: str, timeout: int = 90) -> str:
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
        print(f"[개발에이전트] Claude 오류: {e}")
    return ""


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\r?\n?", "", text)
    text = re.sub(r"\r?\n?```\s*$", "", text)
    return text.strip()


def _is_rate_limit(error: Exception) -> bool:
    msg = str(error).lower()
    return "429" in msg or "quota" in msg or "rate" in msg


def _parse_traceback(output: str, project_files: list[str]) -> tuple[str | None, int | None]:
    pattern = re.compile(r'File ["\']([^"\']+\.py)["\'],\s+line\s+(\d+)', re.IGNORECASE)
    matches = pattern.findall(output)
    for raw_path, line_str in reversed(matches):
        raw_name = Path(raw_path).name
        for pf in project_files:
            if Path(pf).name == raw_name or pf == raw_path or raw_path.endswith(pf):
                return pf, int(line_str)
    return None, None


def _classify_error(output: str) -> str:
    low = output.lower()
    if any(x in low for x in ("no module named", "modulenotfounderror", "importerror")):
        return "dependency_error"
    if "syntaxerror" in low or "invalid syntax" in low:
        return "syntax_error"
    if "cannot import" in low:
        return "import_error"
    if any(x in low for x in ("traceback", "exception", "error:", "nameerror", "typeerror",
                               "attributeerror", "valueerror", "keyerror", "indexerror")):
        return "runtime_error"
    return "none"


def _has_error(output: str, run_command: str) -> bool:
    low = output.lower()
    if "timed out" in low or not output.strip():
        return False
    return _classify_error(output) != "none"


def _plan_project(description: str, language: str) -> dict:
    prompt = (
        f"당신은 수석 소프트웨어 아키텍트입니다. 이 프로젝트를 위한 최소한의 완전한 파일 계획을 만드세요.\n\n"
        f"언어: {language}\n설명: {description}\n\n"
        f"유효한 JSON만 반환 — 마크다운, 설명 없음:\n"
        f'{{\n'
        f'  "project_name": "snake_case_name",\n'
        f'  "entry_point": "main.py",\n'
        f'  "files": [\n'
        f'    {{\n'
        f'      "path": "main.py",\n'
        f'      "description": "진입점 — 무엇을 하고 어떤 모듈을 임포트하는지",\n'
        f'      "imports": ["utils.helpers"]\n'
        f'    }}\n'
        f'  ],\n'
        f'  "run_command": "python main.py",\n'
        f'  "dependencies": ["requests"]\n'
        f'}}\n\n'
        f"규칙: 파일을 의존성 순서로 나열, 최소화, 진입점은 파일 목록에 포함.\n\nJSON:"
    )

    try:
        raw = _call_claude(prompt, timeout=90)
        if not raw:
            raise ValueError("빈 응답")

        # JSON 블록 추출
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            raw = json_match.group(0)

        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"플래너가 잘못된 JSON을 반환했습니다: {e}")


def _write_file(
    file_info: dict,
    project_description: str,
    all_files: list[dict],
    language: str,
    project_dir: Path,
    already_written: dict[str, str],
) -> str:
    file_path    = file_info["path"]
    file_desc    = file_info.get("description", "")
    file_imports = file_info.get("imports", [])

    file_list = "\n".join(
        f"  [{i+1}] {f['path']}: {f.get('description', '')}"
        for i, f in enumerate(all_files)
    )

    dependency_context = ""
    for dep_dotted in file_imports:
        dep_path = dep_dotted.replace(".", "/") + ".py"
        if dep_path in already_written:
            code_snippet = already_written[dep_path][:2000]
            dependency_context += f"\n\n--- {dep_path} (이것에서 임포트해야 합니다) ---\n{code_snippet}"

    prompt = (
        f"당신은 실제 프로젝트를 위한 프로덕션 품질의 코드를 작성하는 수석 {language} 개발자입니다.\n\n"
        f"프로젝트 목표: {project_description}\n\n"
        f"전체 파일 구조 (의존성 순서):\n{file_list}\n"
        f"{f'이 파일이 임포트해야 할 의존성:{dependency_context}' if dependency_context else ''}\n\n"
        f"작성할 파일: {file_path}\n"
        f"이 파일의 목적: {file_desc}\n"
        f"{f'임포트할 것: {chr(44).join(file_imports)}' if file_imports else '프로젝트 내부 임포트 없음.'}\n\n"
        f"규칙:\n"
        f"- 원시 코드만 출력. 설명, 마크다운, 백틱 없음.\n"
        f"- 완전하고 실행 가능한 코드 — 플레이스홀더, TODO, pass 스텁 없음.\n"
        f"- 오류 처리를 적절히 사용하세요.\n"
        f"- 임포트 경로가 파일 구조와 정확히 일치해야 합니다.\n\n"
        f"{file_path}의 코드:"
    )

    code = _call_claude(prompt, timeout=90)
    if not code:
        raise RuntimeError(f"{file_path} 코드를 생성할 수 없습니다.")
    code = _strip_fences(code)

    full_path = project_dir / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(code, encoding="utf-8")

    print(f"[개발에이전트] ✅ 작성됨: {file_path} ({len(code)}자)")
    return code


def _install_dependencies(dependencies: list[str], project_dir: Path) -> str:
    if not dependencies:
        return "외부 의존성이 없습니다."

    to_install = []
    for dep in dependencies:
        pkg_name = re.split(r"[>=<!]", dep)[0].strip()
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", pkg_name],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            to_install.append(dep)
        else:
            print(f"[개발에이전트] ✓ 이미 설치됨: {pkg_name}")

    if not to_install:
        return f"모든 의존성이 이미 설치됨: {', '.join(dependencies)}"

    print(f"[개발에이전트] 📦 설치 중: {to_install}")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install"] + to_install,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=120, cwd=str(project_dir)
        )
        if result.returncode == 0:
            return f"설치됨: {', '.join(to_install)}"
        return f"설치 경고 (치명적이지 않음): {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return "의존성 설치 시간 초과 (치명적이지 않음)."
    except Exception as e:
        return f"설치 오류 (치명적이지 않음): {e}"


def _open_vscode(project_dir: Path) -> bool:
    vscode_candidates = [
        "code",
        rf"C:\Users\{Path.home().name}\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd",
        r"C:\Program Files\Microsoft VS Code\bin\code.cmd",
    ]
    for cmd in vscode_candidates:
        try:
            subprocess.Popen(
                [cmd, str(project_dir)],
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.5)
            print(f"[개발에이전트] 💻 VSCode 열림: {project_dir}")
            return True
        except Exception:
            continue
    return False


def _run_project(run_command: str, project_dir: Path, timeout: int = 30) -> str:
    print(f"[개발에이전트] 🚀 실행: {run_command}")
    try:
        parts = run_command.split()
        if parts[0].lower() == "python":
            parts[0] = sys.executable

        result = subprocess.run(
            parts,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout,
            cwd=str(project_dir)
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        combined_parts = []
        if stdout: combined_parts.append(f"STDOUT:\n{stdout}")
        if stderr: combined_parts.append(f"STDERR:\n{stderr}")

        return "\n\n".join(combined_parts) if combined_parts else "출력 없이 실행됨."

    except subprocess.TimeoutExpired:
        return f"{timeout}초 후 시간 초과 — 장시간 실행 앱(서버/GUI)이 작동 중일 수 있습니다."
    except FileNotFoundError as e:
        return f"명령을 찾을 수 없습니다: {e}"
    except Exception as e:
        return f"실행 오류: {e}"


def _try_auto_install(error_output: str, project_dir: Path) -> bool:
    pattern = re.compile(r"No module named ['\"]([a-zA-Z0-9_\-\.]+)['\"]", re.IGNORECASE)
    match = pattern.search(error_output)
    if not match:
        return False

    pkg = match.group(1).replace("_", "-").split(".")[0]
    print(f"[개발에이전트] 🔧 누락된 패키지 자동 설치: {pkg}")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=60, cwd=str(project_dir)
        )
        return result.returncode == 0
    except Exception:
        return False


def _fix_files(
    error_output: str,
    project_description: str,
    all_files: list[dict],
    file_codes: dict[str, str],
    language: str,
    project_dir: Path,
    entry_point: str,
) -> dict[str, str]:
    error_file, error_line = _parse_traceback(error_output, list(file_codes.keys()))
    error_type = _classify_error(error_output)

    files_to_fix: list[str] = []

    if error_file:
        files_to_fix.append(error_file)
        if error_type == "import_error":
            for fi in all_files:
                if error_file.replace("/", ".").replace(".py", "") in fi.get("imports", []):
                    p = fi["path"]
                    if p not in files_to_fix:
                        files_to_fix.append(p)
    else:
        files_to_fix.append(entry_point)

    updated_codes: dict[str, str] = {}

    for fix_path in files_to_fix:
        current_code = file_codes.get(fix_path, "")

        other_ctx = ""
        for fp, code in file_codes.items():
            if fp != fix_path and code:
                snippet = code[:1500] + ("..." if len(code) > 1500 else "")
                other_ctx += f"\n--- {fp} ---\n{snippet}\n"

        line_hint = f"\n오류는 이 파일의 {error_line}번째 줄 근처로 보입니다." if (
            error_line and fix_path == error_file
        ) else ""

        prompt = (
            f"당신은 전문 {language} 디버거입니다. 아래 잘못된 파일을 수정하세요.\n\n"
            f"프로젝트 목표: {project_description}\n\n"
            f"모든 프로젝트 파일:\n"
            f"{chr(10).join('  - ' + f['path'] + ': ' + f.get('description', '') for f in all_files)}\n\n"
            f"참고용 다른 파일 (수정 금지):\n{other_ctx[:3500]}\n\n"
            f"수정할 파일: {fix_path}{line_hint}\n"
            f"오류 유형: {error_type}\n\n"
            f"오류 출력:\n{error_output[:2500]}\n\n"
            f"현재 (잘못된) 코드:\n{current_code}\n\n"
            f"규칙:\n"
            f"- 완전한 수정된 코드만 출력. 설명, 마크다운, 백틱 없음.\n"
            f"- 오류 출력에서 보이는 모든 오류를 수정하세요.\n"
            f"- 기존의 올바른 로직은 유지하세요.\n\n"
            f"{fix_path}의 수정된 코드:"
        )

        fixed = _call_claude(prompt, timeout=90)
        if not fixed:
            print(f"[개발에이전트] ⚠️ {fix_path} 수정 실패")
            continue

        fixed = _strip_fences(fixed)
        full_path = project_dir / fix_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(fixed, encoding="utf-8")
        updated_codes[fix_path] = fixed
        print(f"[개발에이전트] 🔧 수정됨: {fix_path}")

    return updated_codes


def _build_project(
    description: str,
    language: str,
    project_name: str,
    timeout: int,
    speak=None,
    player=None,
) -> str:
    def log(msg: str):
        print(f"[개발에이전트] {msg}")
        if player:
            player.write_log(f"[개발에이전트] {msg}")

    log("프로젝트 구조 계획 중...")
    try:
        plan = _plan_project(description, language)
    except ValueError as e:
        msg = f"계획 수립 실패: {e}"
        if speak: speak(msg)
        return msg

    proj_name   = project_name or plan.get("project_name", "jarvis_project")
    proj_name   = re.sub(r"[^\w\-]", "_", proj_name)
    project_dir = PROJECTS_DIR / proj_name
    project_dir.mkdir(parents=True, exist_ok=True)

    files        = plan.get("files", [])
    entry_point  = plan.get("entry_point", "main.py")
    run_command  = plan.get("run_command", f"python {entry_point}")
    dependencies = plan.get("dependencies", [])

    log(f"프로젝트: {proj_name} | 파일: {len(files)}개 | 진입점: {entry_point}")

    sorted_files = sorted(files, key=lambda fi: len(fi.get("imports", [])))
    file_codes: dict[str, str] = {}

    for file_info in sorted_files:
        file_path = file_info.get("path", "")
        if not file_path:
            continue

        log(f"{file_path} 작성 중...")
        for attempt in range(2):
            try:
                code = _write_file(
                    file_info=file_info,
                    project_description=description,
                    all_files=files,
                    language=language,
                    project_dir=project_dir,
                    already_written=file_codes,
                )
                file_codes[file_path] = code
                time.sleep(0.4)
                break
            except Exception as e:
                if attempt == 0:
                    log(f"{file_path} 첫 번째 시도 실패: {e}")
                else:
                    log(f"{file_path} 건너뜀.")

    if not file_codes:
        msg = "프로젝트 파일을 작성할 수 없었습니다."
        if speak: speak(msg)
        return msg

    if dependencies:
        install_result = _install_dependencies(dependencies, project_dir)
        log(install_result)

    _open_vscode(project_dir)

    last_output   = ""
    auto_installs = 0

    for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
        log(f"프로젝트 실행 중 (시도 {attempt}/{MAX_FIX_ATTEMPTS})...")
        last_output = _run_project(run_command, project_dir, timeout)
        log(f"출력 미리보기: {last_output[:150]}")

        if not _has_error(last_output, run_command):
            msg = (
                f"'{proj_name}' 프로젝트가 작동합니다! "
                f"{attempt}번 시도 만에 빌드되었습니다. "
                f"저장 위치: {project_dir}"
            )
            if speak: speak(msg)
            return f"{msg}\n\n출력:\n{last_output}"

        if attempt == MAX_FIX_ATTEMPTS:
            break

        error_type = _classify_error(last_output)
        if error_type == "dependency_error" and auto_installs < 3:
            installed = _try_auto_install(last_output, project_dir)
            if installed:
                auto_installs += 1
                log("누락된 의존성이 설치됨, 다시 시도 중...")
                time.sleep(1)
                continue

        log(f"오류 수정 중 (유형: {error_type})...")
        try:
            updated = _fix_files(
                error_output=last_output,
                project_description=description,
                all_files=files,
                file_codes=file_codes,
                language=language,
                project_dir=project_dir,
                entry_point=entry_point,
            )
            file_codes.update(updated)
            time.sleep(1)
        except Exception as e:
            log(f"수정 단계 실패: {e}")

    msg = (
        f"'{proj_name}'을(를) {MAX_FIX_ATTEMPTS}번 시도 후에도 완전히 수정하지 못했습니다. "
        f"프로젝트는 {project_dir}에 저장되어 있습니다. VSCode에서 확인해주세요."
    )
    if speak: speak(msg)
    return f"{msg}\n\n마지막 오류:\n{last_output[:600]}"


def dev_agent(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    p            = parameters or {}
    description  = p.get("description", "").strip()
    language     = p.get("language", "python").strip()
    project_name = p.get("project_name", "").strip()
    timeout      = int(p.get("timeout", 30))

    if not description:
        return "빌드하고 싶은 프로젝트를 설명해주세요."

    return _build_project(
        description  = description,
        language     = language,
        project_name = project_name,
        timeout      = timeout,
        speak        = speak,
        player       = player,
    )
