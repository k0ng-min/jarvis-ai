import json
import re
import subprocess


PLANNER_PROMPT = """당신은 자비스(JARVIS) AI 어시스턴트의 계획 모듈입니다.
사용자의 목표를 아래 도구들만 사용하는 단계별 계획으로 분해하세요.

절대 규칙:
- generated_code는 절대 사용하지 마세요. 존재하지 않습니다.
- 이전 단계 결과를 파라미터에 참조하지 마세요. 각 단계는 독립적입니다.
- 정보 검색에는 web_search를 사용하세요.
- 파일 저장에는 file_controller를 사용하세요.
- 최대 5단계. 필요한 최소 단계만 사용하세요.

사용 가능한 도구:

open_app: app_name(필수)
web_search: query(필수), mode(선택: search/compare)
game_updater: action(필수), platform(선택), game_name(선택), app_id(선택)
browser_control: action(필수), url/query/text/direction(해당 시)
file_controller: action(필수), path, name, content
cmd_control: task(필수), visible(선택)
computer_settings: action(필수), description, value(선택)
computer_control: action(필수), text/x/y/keys/key/direction/description(해당 시)
screen_process: text(필수), angle(선택: screen/camera)
send_message: receiver(필수), message_text(필수), platform(필수)
reminder: date(필수 YYYY-MM-DD), time(필수 HH:MM), message(필수)
desktop_control: action(필수), path/task(선택)
youtube_video: action(필수), query(play 시)
weather_report: city(필수)
flight_finder: origin(필수), destination(필수), date(필수)
code_helper: action(필수), description(필수), language/output_path/file_path(선택)
dev_agent: description(필수), language(선택)

유효한 JSON만 반환하세요. 마크다운 없이:
{
  "goal": "...",
  "steps": [
    {
      "step": 1,
      "tool": "도구이름",
      "description": "이 단계가 하는 일",
      "parameters": {},
      "critical": true
    }
  ]
}"""


def _call_claude(prompt: str) -> str:
    """Claude CLI를 사용하여 응답을 생성합니다."""
    full_prompt = f"{PLANNER_PROMPT}\n\n{prompt}"
    try:
        result = subprocess.run(
            ["claude", "-p", full_prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=60, encoding="utf-8"
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            return data.get("result", "").strip()
    except Exception as e:
        print(f"[플래너] Claude 오류: {e}")
    return ""


def create_plan(goal: str, context: str = "") -> dict:
    user_input = f"목표: {goal}"
    if context:
        user_input += f"\n\n컨텍스트: {context}"

    try:
        text = _call_claude(user_input)
        if not text:
            return _fallback_plan(goal)

        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()

        # JSON 블록 추출
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            text = json_match.group(0)

        plan = json.loads(text)

        if "steps" not in plan or not isinstance(plan["steps"], list):
            raise ValueError("잘못된 계획 구조")

        # generated_code 사용 금지
        for step in plan["steps"]:
            if step.get("tool") == "generated_code":
                print(f"[플래너] ⚠️ 단계 {step.get('step')}에서 generated_code 감지됨 — web_search로 대체")
                step["tool"] = "web_search"
                step["parameters"] = {"query": step.get("description", goal)[:200]}

        print(f"[플래너] ✅ 계획: {len(plan['steps'])}단계")
        for s in plan["steps"]:
            print(f"  단계 {s['step']}: [{s['tool']}] {s['description']}")

        return plan

    except json.JSONDecodeError as e:
        print(f"[플래너] ⚠️ JSON 파싱 실패: {e}")
        return _fallback_plan(goal)
    except Exception as e:
        print(f"[플래너] ⚠️ 계획 수립 실패: {e}")
        return _fallback_plan(goal)


def _fallback_plan(goal: str) -> dict:
    print("[플래너] 🔄 폴백 계획")
    return {
        "goal": goal,
        "steps": [
            {
                "step": 1,
                "tool": "web_search",
                "description": f"검색: {goal}",
                "parameters": {"query": goal},
                "critical": True
            }
        ]
    }


def replan(goal: str, completed_steps: list, failed_step: dict, error: str) -> dict:
    completed_summary = "\n".join(
        f"  - 단계 {s['step']} ({s['tool']}): 완료" for s in completed_steps
    )

    prompt = f"""목표: {goal}

완료된 단계:
{completed_summary if completed_summary else '  (없음)'}

실패한 단계: [{failed_step.get('tool')}] {failed_step.get('description')}
오류: {error}

완료된 단계는 반복하지 말고 나머지 작업만을 위한 수정된 계획을 만드세요."""

    try:
        text = _call_claude(prompt)
        if not text:
            return _fallback_plan(goal)

        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            text = json_match.group(0)

        plan = json.loads(text)

        for step in plan.get("steps", []):
            if step.get("tool") == "generated_code":
                step["tool"] = "web_search"
                step["parameters"] = {"query": step.get("description", goal)[:200]}

        print(f"[플래너] 🔄 수정된 계획: {len(plan['steps'])}단계")
        return plan
    except Exception as e:
        print(f"[플래너] ⚠️ 재계획 실패: {e}")
        return _fallback_plan(goal)
