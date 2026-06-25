import json
import re
import sys
import threading
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Callable

from .planner       import create_plan, replan
from .error_handler import analyze_error, generate_fix, ErrorDecision


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
        print(f"[실행기] Claude 오류: {e}")
    return ""


def _run_generated_code(description: str, speak: Callable | None = None) -> str:
    if speak:
        speak("이 작업을 위한 코드를 작성하고 있습니다.")

    home      = Path.home()
    desktop   = home / "Desktop"
    downloads = home / "Downloads"
    documents = home / "Documents"

    prompt = (
        f"다음 작업을 수행하는 Python 코드를 작성하세요:\n\n{description}\n\n"
        f"시스템 경로:\n"
        f"  바탕화면 = r'{desktop}'\n"
        f"  다운로드 = r'{downloads}'\n"
        f"  문서 = r'{documents}'\n"
        f"  홈 = r'{home}'\n\n"
        f"규칙: 코드만 출력. 설명, 마크다운, 백틱 없음."
    )

    try:
        code = _call_claude(prompt, timeout=60)
        if not code:
            raise RuntimeError("Claude에서 코드를 생성하지 못했습니다.")

        code = re.sub(r"```(?:python)?", "", code).strip().rstrip("`").strip()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        print(f"[실행기] 🐍 생성된 코드 실행: {tmp_path}")

        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True, text=True,
            timeout=120, cwd=str(home)
        )

        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        output = result.stdout.strip()
        error  = result.stderr.strip()

        if result.returncode == 0 and output:
            return output
        elif result.returncode == 0:
            return "작업이 성공적으로 완료되었습니다."
        elif error:
            raise RuntimeError(f"코드 오류: {error[:400]}")
        return "완료되었습니다."

    except subprocess.TimeoutExpired:
        raise RuntimeError("생성된 코드가 120초 후 시간 초과되었습니다.")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"생성된 코드 실패: {e}")


def _inject_context(params: dict, tool: str, step_results: dict, goal: str = "") -> dict:
    if not step_results:
        return params

    params = dict(params)

    if tool == "file_controller" and params.get("action") in ("write", "create_file"):
        content = params.get("content", "")
        if not content or len(content) < 50:
            all_results = [
                v for v in step_results.values()
                if v and len(v) > 100 and v not in ("완료.", "완료되었습니다.")
            ]
            if all_results:
                combined = "\n\n---\n\n".join(all_results)
                params["content"] = combined
                print(f"[실행기] 💉 컨텍스트 주입됨")

    return params


def _call_tool(tool: str, parameters: dict, speak: Callable | None) -> str:
    if tool == "open_app":
        from ..actions.open_app import open_app
        return open_app(parameters=parameters, player=None) or "완료."

    elif tool == "web_search":
        from ..actions.web_search import web_search
        return web_search(parameters=parameters, player=None) or "완료."

    elif tool == "game_updater":
        from ..actions.game_updater import game_updater
        return game_updater(parameters=parameters, player=None, speak=speak) or "완료."

    elif tool == "browser_control":
        from ..actions.browser_control import browser_control
        return browser_control(parameters=parameters, player=None) or "완료."

    elif tool == "file_controller":
        from ..actions.file_controller import file_controller
        return file_controller(parameters=parameters, player=None) or "완료."

    elif tool == "cmd_control":
        from ..actions.cmd_control import cmd_control
        return cmd_control(parameters=parameters, player=None) or "완료."

    elif tool == "code_helper":
        from ..actions.code_helper import code_helper
        return code_helper(parameters=parameters, player=None, speak=speak) or "완료."

    elif tool == "dev_agent":
        from ..actions.dev_agent import dev_agent
        return dev_agent(parameters=parameters, player=None, speak=speak) or "완료."

    elif tool == "screen_process":
        from ..actions.screen_processor import screen_process
        screen_process(parameters=parameters, player=None)
        return "화면이 캡처되고 분석되었습니다."

    elif tool == "send_message":
        from ..actions.send_message import send_message
        return send_message(parameters=parameters, player=None) or "완료."

    elif tool == "reminder":
        from ..actions.reminder import reminder
        return reminder(parameters=parameters, player=None) or "완료."

    elif tool == "youtube_video":
        from ..actions.youtube_video import youtube_video
        return youtube_video(parameters=parameters, player=None) or "완료."

    elif tool == "weather_report":
        from ..actions.weather_report import weather_action
        return weather_action(parameters=parameters, player=None) or "완료."

    elif tool == "computer_settings":
        from ..actions.computer_settings import computer_settings
        return computer_settings(parameters=parameters, player=None) or "완료."

    elif tool == "desktop_control":
        from ..actions.desktop import desktop_control
        return desktop_control(parameters=parameters, player=None) or "완료."

    elif tool == "computer_control":
        from ..actions.computer_control import computer_control
        return computer_control(parameters=parameters, player=None) or "완료."

    elif tool == "generated_code":
        description = parameters.get("description", "")
        if not description:
            raise ValueError("generated_code는 'description' 파라미터가 필요합니다.")
        return _run_generated_code(description, speak=speak)

    elif tool == "flight_finder":
        from ..actions.flight_finder import flight_finder
        return flight_finder(parameters=parameters, player=None, speak=speak) or "완료."

    else:
        print(f"[실행기] ⚠️ 알 수 없는 도구 '{tool}' — generated_code로 폴백")
        return _run_generated_code(f"다음 작업 수행: {parameters}", speak=speak)


class AgentExecutor:

    MAX_REPLAN_ATTEMPTS = 2

    def execute(
        self,
        goal:        str,
        speak:       Callable | None        = None,
        cancel_flag: threading.Event | None = None,
    ) -> str:
        print(f"\n[실행기] 🎯 목표: {goal}")

        replan_attempts = 0
        completed_steps = []
        step_results    = {}
        plan            = create_plan(goal)

        while True:
            steps = plan.get("steps", [])

            if not steps:
                msg = "이 작업에 대한 유효한 계획을 만들 수 없었습니다."
                if speak: speak(msg)
                return msg

            success      = True
            failed_step  = None
            failed_error = ""

            for step in steps:
                if cancel_flag and cancel_flag.is_set():
                    if speak: speak("작업이 취소되었습니다.")
                    return "작업 취소됨."

                step_num = step.get("step", "?")
                tool     = step.get("tool", "generated_code")
                desc     = step.get("description", "")
                params   = step.get("parameters", {})

                params = _inject_context(params, tool, step_results, goal=goal)

                print(f"\n[실행기] ▶️ 단계 {step_num}: [{tool}] {desc}")

                attempt = 1
                step_ok = False

                while attempt <= 3:
                    if cancel_flag and cancel_flag.is_set():
                        break
                    try:
                        result = _call_tool(tool, params, speak)
                        step_results[step_num] = result
                        completed_steps.append(step)
                        print(f"[실행기] ✅ 단계 {step_num} 완료: {str(result)[:100]}")
                        step_ok = True
                        break

                    except Exception as e:
                        error_msg = str(e)
                        print(f"[실행기] ❌ 단계 {step_num} 시도 {attempt} 실패: {error_msg}")

                        recovery = analyze_error(step, error_msg, attempt=attempt)
                        decision = recovery["decision"]
                        user_msg = recovery.get("user_message", "")

                        if speak and user_msg:
                            speak(user_msg)

                        if decision == ErrorDecision.RETRY:
                            attempt += 1
                            import time; time.sleep(2)
                            continue

                        elif decision == ErrorDecision.SKIP:
                            print(f"[실행기] ⏭️ 단계 {step_num} 건너뜀")
                            completed_steps.append(step)
                            step_ok = True
                            break

                        elif decision == ErrorDecision.ABORT:
                            msg = f"작업이 중단되었습니다. {recovery.get('reason', '')}"
                            if speak: speak(msg)
                            return msg

                        else:  # REPLAN
                            fix_suggestion = recovery.get("fix_suggestion", "")
                            if fix_suggestion and tool != "generated_code":
                                try:
                                    fixed_step = generate_fix(step, error_msg, fix_suggestion)
                                    if speak: speak("다른 방법으로 시도해보겠습니다.")
                                    res = _call_tool(
                                        fixed_step["tool"],
                                        fixed_step["parameters"],
                                        speak
                                    )
                                    step_results[step_num] = res
                                    completed_steps.append(step)
                                    step_ok = True
                                    break
                                except Exception as fix_err:
                                    print(f"[실행기] ⚠️ 수정 실패: {fix_err}")

                            failed_step  = step
                            failed_error = error_msg
                            success      = False
                            break

                if not step_ok and not failed_step:
                    failed_step  = step
                    failed_error = "최대 재시도 횟수 초과"
                    success      = False

                if not success:
                    break

            if success:
                return self._summarize(goal, completed_steps, speak)

            if replan_attempts >= self.MAX_REPLAN_ATTEMPTS:
                msg = f"{replan_attempts}번의 재계획 시도 후 작업이 실패했습니다."
                if speak: speak(msg)
                return msg

            if speak: speak("접근 방식을 조정하겠습니다.")

            replan_attempts += 1
            plan = replan(goal, completed_steps, failed_step, failed_error)

    def _summarize(self, goal: str, completed_steps: list, speak: Callable | None) -> str:
        fallback = f"완료되었습니다. '{goal[:60]}'에 대해 {len(completed_steps)}단계를 완료했습니다."

        steps_str = "\n".join(f"- {s.get('description', '')}" for s in completed_steps)
        prompt = (
            f'사용자 목표: "{goal}"\n'
            f"완료된 단계:\n{steps_str}\n\n"
            "무엇이 달성되었는지 자연스러운 한국어 문장으로 요약하세요. "
            "직접적이고 긍정적으로 말하세요."
        )

        try:
            summary = _call_claude(prompt, timeout=30)
            if summary:
                if speak: speak(summary)
                return summary
        except Exception:
            pass

        if speak: speak(fallback)
        return fallback
