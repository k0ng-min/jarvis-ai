"""
자비스 음성 상호작용 시뮬레이션 테스트
실제 음성 대신 텍스트로 질문하고 응답 확인
"""

import sys
import time
from pathlib import Path
from jarvis_ai.main import (
    _fast_route, _call_claude, _load_system_prompt,
    parse_tool_call, execute_tool
)

BASE_DIR = Path(__file__).resolve().parent

def simulate_voice_interaction(query: str):
    """음성 상호작용 시뮬레이션"""
    print(f"\n🎤 사용자: {query}")
    print("-" * 50)

    system_prompt = _load_system_prompt()

    # 1단계: 로컬 라우팅 시도
    tool_name, params, direct_answer = _fast_route(query)

    if direct_answer:
        print(f"✅ 자비스 (로컬): {direct_answer}")
        return direct_answer

    # 2단계: 도구 실행
    if tool_name:
        print(f"🔧 도구 실행: {tool_name}")
        result = execute_tool(tool_name, params)
        print(f"✅ 자비스: {result}")
        return result

    # 3단계: Claude API 호출
    print(f"📡 Claude에 요청 중...")
    response = _call_claude(query, system_prompt)
    print(f"✅ 자비스: {response}")
    return response


def main():
    print("\n" + "="*60)
    print("   자비스 (JARVIS) - 음성 상호작용 시뮬레이션 테스트")
    print("="*60)

    # 테스트 질문들
    test_queries = [
        ("자비스, 현재 시각이 몇 시야?", "시간"),
        ("자비스, 오늘 날짜가 뭐야?", "날짜"),
        ("자비스, 서울 날씨는?", "날씨"),
        ("자비스, 안녕?", "인사"),
        ("자비스, 오늘의 뉴스는?", "뉴스"),
    ]

    print("\n📋 테스트 질문 시작...\n")

    for idx, (query, label) in enumerate(test_queries, 1):
        print(f"\n【 TEST {idx} 】{label}")
        print("="*60)
        try:
            simulate_voice_interaction(query)
            time.sleep(1)
        except Exception as e:
            print(f"❌ 오류: {e}")

    print("\n" + "="*60)
    print("✅ 모든 상호작용 테스트 완료!")
    print("="*60)
    print("\n💡 다음: python main.py로 GUI를 실행하고")
    print("   '자비스'라고 부른 후 이 질문들을 음성으로 시도하세요!")

if __name__ == "__main__":
    main()
