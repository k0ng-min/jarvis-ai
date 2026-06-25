import json
import re
import subprocess
from enum import Enum


class ErrorDecision(Enum):
    RETRY   = "retry"
    SKIP    = "skip"
    REPLAN  = "replan"
    ABORT   = "abort"


ERROR_ANALYST_PROMPT = """당신은 자비스(JARVIS) AI 어시스턴트의 오류 복구 모듈입니다.

작업 단계가 실패했습니다. 오류를 분석하고 무엇을 해야 할지 결정하세요.

결정:
- retry   : 일시적 오류 (네트워크 타임아웃, 임시 파일 잠금). 다시 시도하면 성공할 수 있습니다.
- skip    : 이 단계는 중요하지 않으며 없어도 작업이 성공할 수 있습니다.
- replan  : 접근 방식이 잘못되었습니다. 다른 도구나 방법을 시도해야 합니다.
- abort   : 작업이 근본적으로 불가능하거나 계속하기에 안전하지 않습니다.

유효한 JSON만 반환하세요:
{
  "decision": "retry|skip|replan|abort",
  "reason": "실패한 이유 (1문장)",
  "fix_suggestion": "다시 시도할 방법 (replan인 경우)",
  "max_retries": 1,
  "user_message": "사용자에게 할 짧은 메시지 (최대 15단어)"
}"""


def _call_claude(prompt: str) -> str:
    """Claude CLI를 사용하여 오류를 분석합니다."""
    full_prompt = f"{ERROR_ANALYST_PROMPT}\n\n{prompt}"
    try:
        result = subprocess.run(
            ["claude", "-p", full_prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=45, encoding="utf-8"
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            return data.get("result", "").strip()
    except Exception as e:
        print(f"[오류처리기] Claude 오류: {e}")
    return ""


def analyze_error(
    step: dict,
    error: str,
    attempt: int = 1,
    max_attempts: int = 2
) -> dict:
    if attempt >= max_attempts:
        print(f"[오류처리기] ⚠️ 단계 {step.get('step')} 최대 시도 횟수 초과 — 재계획 강제")
        return {
            "decision":       ErrorDecision.REPLAN,
            "reason":         f"{attempt}번 실패: {error[:100]}",
            "fix_suggestion": "완전히 다른 접근 방식이나 도구를 시도해보세요",
            "max_retries":    0,
            "user_message":   "다른 방법으로 시도해보겠습니다."
        }

    prompt = f"""실패한 단계:
도구: {step.get('tool')}
설명: {step.get('description')}
파라미터: {json.dumps(step.get('parameters', {}), indent=2, ensure_ascii=False)}
중요 여부: {step.get('critical', False)}

오류:
{error[:500]}

시도 횟수: {attempt}"""

    try:
        text = _call_claude(prompt)
        if not text:
            raise ValueError("빈 응답")

        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            text = json_match.group(0)

        result = json.loads(text)
        decision_str = result.get("decision", "replan").lower()
        decision_map = {
            "retry":  ErrorDecision.RETRY,
            "skip":   ErrorDecision.SKIP,
            "replan": ErrorDecision.REPLAN,
            "abort":  ErrorDecision.ABORT,
        }
        result["decision"] = decision_map.get(decision_str, ErrorDecision.REPLAN)

        # 중요 단계는 건너뛰지 않음
        if step.get("critical") and result["decision"] == ErrorDecision.SKIP:
            result["decision"]     = ErrorDecision.REPLAN
            result["user_message"] = "중요한 단계입니다 — 대안을 찾고 있습니다."

        print(f"[오류처리기] 결정: {result['decision'].value} — {result.get('reason', '')}")
        return result

    except Exception as e:
        print(f"[오류처리기] ⚠️ 분석 실패: {e} — 재계획으로 기본 설정")
        return {
            "decision":       ErrorDecision.REPLAN,
            "reason":         str(e),
            "fix_suggestion": "대안 접근 방식 시도",
            "max_retries":    1,
            "user_message":   "문제가 발생했습니다. 접근 방식을 조정하겠습니다."
        }


def generate_fix(step: dict, error: str, fix_suggestion: str) -> dict:
    """
    REPLAN 결정 시 수정 단계를 생성합니다.
    """
    prompt = (
        f"작업 단계가 실패했습니다. 대체 단계를 Python 코드로 생성하세요.\n\n"
        f"원래 단계:\n"
        f"도구: {step.get('tool')}\n"
        f"설명: {step.get('description')}\n"
        f"파라미터: {json.dumps(step.get('parameters', {}), ensure_ascii=False)}\n\n"
        f"오류: {error[:300]}\n"
        f"수정 제안: {fix_suggestion}\n\n"
        f"같은 목표를 다르게 달성하는 Python 코드만 출력하세요."
    )

    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=45, encoding="utf-8"
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            code = data.get("result", "").strip()
            code = re.sub(r"```(?:python)?", "", code).strip().rstrip("`").strip()

            return {
                "step":        step.get("step"),
                "tool":        "code_helper",
                "description": f"자동 수정: {step.get('description')}",
                "parameters": {
                    "action":      "run",
                    "description": fix_suggestion,
                    "code":        code,
                    "language":    "python"
                },
                "depends_on": step.get("depends_on", []),
                "critical":   step.get("critical", False)
            }
    except Exception as e:
        print(f"[오류처리기] ⚠️ 수정 생성 실패: {e}")

    return {
        "step":        step.get("step"),
        "tool":        "web_search",
        "description": f"폴백: {step.get('description')}",
        "parameters":  {"query": step.get("description", "")},
        "depends_on":  step.get("depends_on", []),
        "critical":    step.get("critical", False)
    }
