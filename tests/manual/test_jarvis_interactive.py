"""
자비스 대화형 테스트 스크립트
실제 음성 입력 대신 텍스트로 질문하고 응답을 테스트합니다.
"""

import sys
import time
from pathlib import Path
from jarvis_ai.main import (
    _fast_route, _call_claude, _load_system_prompt,
    parse_tool_call, execute_tool, speak_text
)

BASE_DIR = Path(__file__).resolve().parent

# 테스트 질문 목록
TEST_QUERIES = [
    "자비스, 현재 시각이 몇 시야?",
    "자비스, 오늘 날짜가 뭐야?",
    "자비스, 서울 날씨 어때?",
    "자비스, 오늘의 뉴스는?",
    "자비스, 내일 날씨는 어떨까?",
]

def test_fast_route():
    """빠른 로컬 라우팅 테스트 (Claude 호출 없음)"""
    print("\n" + "="*60)
    print("【 TEST 1 】빠른 라우팅 테스트 (로컬 처리)")
    print("="*60)

    fast_queries = [
        "몇 시야?",
        "오늘 날짜",
        "서울 날씨 어때?",
    ]

    for query in fast_queries:
        tool_name, params, direct_answer = _fast_route(query)
        print(f"\n질문: {query}")
        if direct_answer:
            print(f"✅ 로컬 응답: {direct_answer}")
        elif tool_name:
            print(f"🔧 도구: {tool_name}, 파라미터: {params}")
        else:
            print(f"📡 Claude에게 위임")

def test_claude_api():
    """Claude API 호출 테스트"""
    print("\n" + "="*60)
    print("【 TEST 2 】Claude API 호출 테스트")
    print("="*60)

    system_prompt = _load_system_prompt()
    print(f"✅ 시스템 프롬프트 로드됨 ({len(system_prompt)} 자)")

    # 간단한 질문 테스트
    test_query = "안녕하세요. 당신은 누구세요?"
    print(f"\n질문: {test_query}")
    print("⏳ Claude에 요청 중...")

    response = _call_claude(test_query, system_prompt)
    print(f"\n응답: {response[:200]}...")

def test_tool_parsing():
    """도구 호출 파싱 테스트"""
    print("\n" + "="*60)
    print("【 TEST 3 】도구 호출 파싱 테스트")
    print("="*60)

    # 도구 호출 형식의 응답 시뮬레이션
    mock_response = """여기 날씨 정보입니다.
<tool>weather_report</tool>
<params>{"city": "서울"}</params>
현재 서울의 날씨는 맑습니다."""

    tool_name, params, clean = parse_tool_call(mock_response)
    print(f"원본: {mock_response[:50]}...")
    print(f"✅ 파싱 결과:")
    print(f"  도구: {tool_name}")
    print(f"  파라미터: {params}")
    print(f"  클린 텍스트: {clean[:50]}...")

def test_interactive_chat():
    """대화형 테스트"""
    print("\n" + "="*60)
    print("【 TEST 4 】대화형 테스트")
    print("="*60)
    print("\n💬 몇 가지 질문을 테스트합니다 (Claude 호출)...")
    print("(Claude API 호출은 시간이 걸릴 수 있습니다)\n")

    system_prompt = _load_system_prompt()

    queries = [
        "현재 시각이 몇 시야?",
        "오늘은 무슨 요일이야?",
    ]

    for idx, query in enumerate(queries, 1):
        print(f"\n[질문 {idx}] {query}")
        print("⏳ 처리 중...", end="", flush=True)

        # 로컬 라우팅 먼저 시도
        tool_name, params, direct_answer = _fast_route(query)

        if direct_answer:
            print(f"\n✅ 응답: {direct_answer}")
        elif tool_name:
            print(f"\n🔧 도구 실행: {tool_name}")
            result = execute_tool(tool_name, params)
            print(f"✅ 결과: {result}")
        else:
            # Claude에 위임
            response = _call_claude(query, system_prompt)
            print(f"\n✅ 응답: {response[:150]}...")

def test_mic_list():
    """마이크 목록 확인"""
    print("\n" + "="*60)
    print("【 BONUS 】마이크 설정 확인")
    print("="*60)

    try:
        import speech_recognition as sr
        with sr.Microphone() as source:
            print(f"✅ 기본 마이크 감지됨")
            print(f"  샘플 레이트: 48000 Hz")
    except Exception as e:
        print(f"⚠️  마이크 접근 오류: {e}")
        print(f"💡 check_mics.py를 실행하여 마이크를 확인하세요")

def main():
    print("\n")
    print("╔" + "="*58 + "╗")
    print("║" + " "*15 + "자비스 (JARVIS) 기능 테스트" + " "*15 + "║")
    print("║" + " "*58 + "║")
    print("║  Claude Code CLI 기반 AI 어시스턴트" + " "*20 + "║")
    print("╚" + "="*58 + "╝")

    try:
        # 순차적 테스트
        test_fast_route()
        test_tool_parsing()
        test_mic_list()

        # Claude API 테스트 (선택)
        response = input("\n\n🔷 Claude API 테스트를 실행하시겠습니까? (y/n): ").strip().lower()
        if response == 'y':
            test_claude_api()

            response2 = input("\n\n🔷 대화형 테스트를 실행하시겠습니까? (y/n): ").strip().lower()
            if response2 == 'y':
                test_interactive_chat()

        print("\n" + "="*60)
        print("✅ 모든 테스트 완료!")
        print("="*60)
        print("\n💡 다음 단계:")
        print("  1. python main.py 를 실행하여 GUI 시작")
        print("  2. '자비스'라고 부르고 질문하기")
        print("  3. F4: 음소거 토글, F11: 전체화면, F1: 채팅")

    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
