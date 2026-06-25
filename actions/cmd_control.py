# actions/cmd_control.py — 자비스 명령어 제어

import json
import os
import platform
import re
import subprocess
import sys


_OS = platform.system()


def _call_claude(prompt: str) -> str:
    """Claude CLI로 셸 명령어 생성"""
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=30, encoding="utf-8"
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            return data.get("result", "").strip()
    except Exception as e:
        print(f"[CMD] Claude 오류: {e}")
    return ""


def _generate_command(task: str) -> str:
    """자연어 작업에서 셸 명령어 생성"""
    os_name = {"Windows": "Windows (PowerShell/CMD)", "Darwin": "macOS", "Linux": "Linux"}.get(_OS, _OS)
    prompt = (
        f"OS: {os_name}\n"
        f"다음 작업에 대한 셸 명령어를 생성하세요: {task}\n\n"
        f"규칙:\n"
        f"- 실행 가능한 명령어만 출력. 설명 없음.\n"
        f"- 파일 삭제, 시스템 포맷, 악의적인 명령어는 생성하지 마세요.\n"
        f"- Windows에서는 PowerShell 명령어를 선호하세요.\n"
        f"명령어:"
    )
    return _call_claude(prompt)


def _is_safe_command(cmd: str) -> bool:
    """위험한 명령어 필터"""
    dangerous = [
        "format", "del /f /s", "rm -rf /", "rmdir /s",
        "reg delete", "bcdedit", "diskpart", ":(){:|:&};:",
        "dd if=", "mkfs", "fdisk", "shutdown /r /t 0 /f",
    ]
    cmd_lower = cmd.lower()
    return not any(d in cmd_lower for d in dangerous)


def _run_command(cmd: str, visible: bool = False, timeout: int = 30) -> str:
    """명령어 실행"""
    if not _is_safe_command(cmd):
        return f"안전하지 않은 명령어가 감지되었습니다: {cmd[:50]}"

    try:
        if _OS == "Windows":
            if visible:
                # 창을 보이게 실행
                subprocess.Popen(
                    ["cmd", "/k", cmd],
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
                return f"명령어를 새 창에서 실행했습니다: {cmd[:60]}"
            else:
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                    capture_output=True, text=True, timeout=timeout,
                    encoding="utf-8", errors="replace"
                )
        else:
            if visible:
                # macOS/Linux에서 터미널로 열기
                if _OS == "Darwin":
                    subprocess.Popen(["open", "-a", "Terminal", "--args", "-c", cmd])
                else:
                    subprocess.Popen(["x-terminal-emulator", "-e", cmd])
                return f"명령어를 터미널에서 실행했습니다: {cmd[:60]}"
            else:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True,
                    timeout=timeout, encoding="utf-8", errors="replace"
                )

        output = result.stdout.strip()
        error  = result.stderr.strip()

        if result.returncode == 0:
            return output if output else "완료되었습니다."
        else:
            return f"오류 (코드 {result.returncode}): {error[:200]}" if error else "명령어가 오류로 종료되었습니다."

    except subprocess.TimeoutExpired:
        return f"{timeout}초 후 시간 초과되었습니다."
    except Exception as e:
        return f"명령어 실행 실패: {e}"


def _open_file_or_app(path_or_name: str) -> str:
    """파일 또는 앱 열기"""
    try:
        if _OS == "Windows":
            os.startfile(path_or_name)
        elif _OS == "Darwin":
            subprocess.Popen(["open", path_or_name])
        else:
            subprocess.Popen(["xdg-open", path_or_name])
        return f"열림: {path_or_name}"
    except Exception as e:
        return f"열기 실패: {e}"


# 자주 쓰는 작업 매핑
_QUICK_TASKS = {
    "ip": "ipconfig" if _OS == "Windows" else "ip addr",
    "ip주소": "ipconfig" if _OS == "Windows" else "ip addr",
    "디스크": "Get-PSDrive -PSProvider FileSystem | Select-Object Name, Used, Free" if _OS == "Windows" else "df -h",
    "프로세스": "Get-Process | Sort-Object CPU -Descending | Select-Object -First 15 | Format-Table Name, CPU, WorkingSet" if _OS == "Windows" else "ps aux --sort=-%cpu | head -15",
    "메모리": "Get-WmiObject Win32_ComputerSystem | Select-Object -ExpandProperty TotalPhysicalMemory" if _OS == "Windows" else "free -h",
    "현재경로": "Get-Location" if _OS == "Windows" else "pwd",
    "파이썬버전": f'"{sys.executable}" --version',
}


def cmd_control(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    명령어 제어 — 자연어 작업을 셸 명령어로 변환하고 실행합니다.

    parameters:
        task    : (필수) 자연어 작업 설명
        command : (선택) 직접 실행할 명령어
        visible : (선택) 새 창에서 실행 여부 (기본: False)
        timeout : (선택) 타임아웃 초 (기본: 30)
        open    : (선택) 열 파일/앱 경로
    """
    params  = parameters or {}
    task    = params.get("task",    "").strip()
    command = params.get("command", "").strip()
    visible = bool(params.get("visible", False))
    timeout = int(params.get("timeout", 30))
    open_target = params.get("open", "").strip()

    if player:
        player.write_log(f"[CMD] {task or command or open_target}")

    # 파일/앱 열기
    if open_target:
        return _open_file_or_app(open_target)

    # 직접 명령어
    if command:
        print(f"[CMD] ▶ 직접 실행: {command[:80]}")
        return _run_command(command, visible, timeout)

    if not task:
        return "실행할 작업 또는 명령어를 지정해주세요."

    # 빠른 작업 매핑 확인
    task_lower = task.lower().strip()
    for key, cmd in _QUICK_TASKS.items():
        if key in task_lower:
            print(f"[CMD] ⚡ 빠른 작업: {cmd[:60]}")
            return _run_command(cmd, visible, timeout)

    # 파일 열기 패턴 감지
    open_patterns = ["열어", "open", "실행해", "launch"]
    if any(p in task_lower for p in open_patterns):
        # 경로나 앱 이름 추출 시도
        path_match = re.search(r'["\']([^"\']+)["\']|(\S+\.\w+)', task)
        if path_match:
            target = path_match.group(1) or path_match.group(2)
            return _open_file_or_app(target)

    # Claude로 명령어 생성
    print(f"[CMD] 🤖 명령어 생성 중: {task[:60]}")
    generated_cmd = _generate_command(task)

    if not generated_cmd:
        return f"'{task}' 작업에 대한 명령어를 생성할 수 없습니다."

    # 코드 블록 제거
    generated_cmd = re.sub(r"```\w*\n?", "", generated_cmd).strip().rstrip("`").strip()

    if not _is_safe_command(generated_cmd):
        return f"생성된 명령어가 안전하지 않아 실행을 거부했습니다."

    print(f"[CMD] ▶ 생성된 명령어: {generated_cmd[:80]}")
    return _run_command(generated_cmd, visible, timeout)
